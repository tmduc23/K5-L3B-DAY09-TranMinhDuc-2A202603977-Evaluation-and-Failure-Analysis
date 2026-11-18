"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, aggregate, load_spec, per_item


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    graded = _graded_metrics(spec)

    # 1. Metric values must be real numbers: NaN/inf compare False against every threshold.
    for mid, v in (pr.get("metrics") or {}).items():
        if _non_finite(v):
            problems.append(f"metric {mid} is {v!r} (NaN/inf): a crashed grader cannot pass a gate")

    # 2. Evaluator failures, or a graded value that is missing / not a boolean.
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s): {pr['evaluator_failures'][0]}")
    rows = pr.get("rows") or []
    for mid in graded:
        missing = [f"{r.get('item_id')}@{r.get('seed')}" for r in rows if not isinstance(r.get(mid), bool)]
        if missing:
            problems.append(f"{len(missing)} row(s) with no boolean value for graded metric {mid} "
                            f"(first {missing[0]}): a None silently drops out of the mean")

    # 3. Row coverage: count, duplicates, and the exact (item, seed) set of the baseline.
    man, bman = pr.get("manifest") or {}, base.get("manifest") or {}
    try:
        want = int(man["items"]) * len(man["seeds"])
    except (KeyError, TypeError, ValueError):
        want = None
        problems.append("manifest lacks items/seeds: row coverage cannot be checked")
    if want is not None and len(rows) != want:
        problems.append(f"{len(rows)} rows, manifest says {man['items']} items x {len(man['seeds'])} seeds = {want}")
    if man.get("items") != bman.get("items") or sorted(man.get("seeds") or []) != sorted(bman.get("seeds") or []):
        problems.append(f"manifest items/seeds {man.get('items')}/{man.get('seeds')} differ from the baseline's "
                        f"{bman.get('items')}/{bman.get('seeds')}")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    dups = sorted({k for k in keys if keys.count(k) > 1}, key=str)
    if dups:
        problems.append(f"{len(dups)} duplicated (item, seed) row(s), first {dups[0]}")
    base_keys = {(r.get("item_id"), r.get("seed")) for r in base.get("rows") or []}
    if set(keys) != base_keys:
        extra, gone = set(keys) - base_keys, base_keys - set(keys)
        problems.append(f"(item, seed) set differs from the baseline: {len(gone)} missing, {len(extra)} extra"
                        + (f", e.g. missing {sorted(gone, key=str)[0]}" if gone else ""))

    # 4. Reported metrics must be what the rows say (a hand-edited number is not evidence).
    if rows and not problems:
        ids = [m for m in graded if all(m in r for r in rows)]
        recomputed = aggregate([{**r, "cost": r.get("cost", 0.0)} for r in rows], ids,
                               k_values=spec.get("pass_k", []))
        for mid, v in (pr.get("metrics") or {}).items():
            r = recomputed.get(mid)
            if isinstance(v, (int, float)) and isinstance(r, (int, float)) and abs(float(v) - float(r)) > 1e-6:
                problems.append(f"metric {mid} reported {v} but the rows give {r}")

    # 5. Slice tags come from the label, so they must match the baseline item by item.
    pr_tags, base_tags = _slice_tags(rows), _slice_tags(base.get("rows") or [])
    for item, tags in sorted(pr_tags.items()):
        if len(tags) > 1:
            problems.append(f"{item}: slice tags differ between seeds {sorted(map(list, tags))}")
        elif item in base_tags and tags != base_tags[item]:
            problems.append(f"{item}: slice tags {sorted(map(list, tags))} differ from the baseline's "
                            f"{sorted(map(list, base_tags[item]))}")

    # 6. Ratchet: on the same eval set, thresholds may only get stricter.
    if base_spec is not None and (spec.get("eval_set_version") == base_spec.get("eval_set_version")
                                  or spec.get("eval_set") == base_spec.get("eval_set")):
        problems += _ratchet(spec, base_spec)
    return problems


def _graded_metrics(spec: dict) -> list[str]:
    """Spec metrics scored row by row by a grader (the ones a crash can silently drop)."""
    from lab9.graders import GRADERS
    return [m["id"] for m in spec.get("metrics") or [] if m["id"] in GRADERS]


def _non_finite(v) -> bool:
    if isinstance(v, bool) or v is None:
        return False
    if isinstance(v, (int, float)):
        return not math.isfinite(float(v))
    if isinstance(v, dict):
        return any(_non_finite(x) for x in v.values())
    if isinstance(v, (list, tuple)):
        return any(_non_finite(x) for x in v)
    return not isinstance(v, str)          # anything else is not a metric value


def _slice_tags(rows: list[dict]) -> dict[str, set[tuple[str, ...]]]:
    out: dict[str, set[tuple[str, ...]]] = {}
    for r in rows:
        out.setdefault(r.get("item_id"), set()).add(tuple(sorted(r.get("slices") or [])))
    return out


_RULES = (("max", "max may not rise", lambda new, old: new > old),
          ("max_increase", "max_increase may not rise", lambda new, old: new > old),
          ("min", "min may not fall", lambda new, old: new < old))


def _looser(where: str, new: dict, old: dict, new_blocking, old_blocking) -> list[str]:
    out = []
    if old_blocking and not new_blocking:
        out.append(f"RATCHET {where}: blocking -> non-blocking")
    for key, rule, looser in _RULES:
        if key in old and (key not in new or looser(new[key], old[key])):
            out.append(f"RATCHET {where}: {rule} ({old[key]} -> {new.get(key, 'removed')})")
    if old.get("no_significant_drop") and not new.get("no_significant_drop"):
        out.append(f"RATCHET {where}: no_significant_drop removed")
    return out


def _ratchet(spec: dict, base_spec: dict) -> list[str]:
    out = []
    new_m = {m["id"]: m for m in spec.get("metrics") or []}
    for m in base_spec.get("metrics") or []:
        n = new_m.get(m["id"])
        if n is None:
            out.append(f"RATCHET metric {m['id']}: removed")
            continue
        out += _looser(f"metric {m['id']}", n.get("threshold") or {}, m.get("threshold") or {},
                       n.get("blocking"), m.get("blocking"))
    new_s = {(s.get("name"), s.get("metric")): s for s in spec.get("slices") or []}
    for s in base_spec.get("slices") or []:
        n = new_s.get((s.get("name"), s.get("metric")))
        where = f"slice {s.get('name')}/{s.get('metric')}"
        if n is None:
            out.append(f"RATCHET {where}: removed")
            continue
        out += _looser(where, n, s, n.get("blocking"), s.get("blocking"))
    return out


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for s in spec.get("slices") or []:
        name, metric = s["name"], s["metric"]
        sid = f"slice:{name}/{metric}"
        a, b = per_item(pr, metric, slice_name=name), per_item(base, metric, slice_name=name)
        verdict, note, val = "ok", "", None
        if not a:
            verdict, note = "fail", "no items in slice"
        else:
            val = round(sum(a.values()) / len(a), 4)
            if "min" in s and val < s["min"]:
                verdict = "fail"
            if "max" in s and val > s["max"]:
                verdict = "fail"
            if s.get("no_significant_drop"):
                keys = sorted(set(a) & set(b))
                if keys:
                    d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                       n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
                    note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                    if hi < 0:
                        verdict = "fail"
                else:
                    verdict, note = "fail", "no items shared with the baseline"
        if verdict != "ok" and s.get("blocking"):
            blocked.append(sid)
        label = "ok" if verdict == "ok" else ("BLOCK" if s.get("blocking") else "warn")
        th = {k: s[k] for k in ("min", "max", "no_significant_drop") if k in s}
        lines.append(f"  {sid:<34} {val!s:<8} n={len(a):<3} {json.dumps(th):<40} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
