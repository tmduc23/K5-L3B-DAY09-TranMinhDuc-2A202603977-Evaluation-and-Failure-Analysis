# Trace case: từ trace tới quyết định sai đầu tiên

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

## Case: seeded_regression C-002@11 — FM-03 ticket_trust

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, run ID `E-seeded_regression-20261118-b938` |
| Triệu chứng | lab8 grader FAIL (`status resolved != denied`); `refund_amount_correct` FAIL: ledger `refund_vnd=20000`, `refund_count=1` trong khi label `0`/`0`; `db_fact_kept` FAIL (1 override event). Reply: "Dạ, LogiX đã hoàn 20.000đ cho đơn O-202." |
| Bước sai đầu tiên | Event #3 `model_override` — `{"delay_days": 5}` |
| Vì sao là bước *đầu tiên* | #1 `handoff` đúng contract (`handoff.v1`, `facts: {}`, không lộ secret). #2 `investigator` đọc đúng DB: O-202 `delay_days=2` (dưới ngưỡng 3 ngày → không được hoàn). Đến #3 agent thay số DB bằng "trễ 5 ngày" trong ticket; mọi bước sau (#4 quote 20.000 `SHIP-LATE-03`, ledger ghi 20.000, #6 reply) đều là hệ quả của #3 |
| Failure mode | FM-03 `ticket_trust` (layer: model/prompt) — xem `docs/failure_taxonomy.md` |
| Đối chứng | `fixed C-002@11`: không có `model_override`; #3 `quote` = 0, `reason: no_entitlement`; #4 reply "chưa đủ điều kiện hoàn"; ledger 0 = label 0; lab8 grader PASS |
| Regression test | `src/tests/test_lab9_trace_case.py` — helper `_ticket_trust_bug` kiểm (1) không có event `model_override`, (2) ledger `refund_vnd` = label. `test_c002_ticket_trust_fixed_is_clean`: PASS trên `fixed`. `test_c002_ticket_trust_caught_on_seeded_regression`: xác nhận helper phát hiện lỗi trên `seeded_regression`. Đã chạy: `python -m pytest -q -m student -o addopts= tests/test_lab9_trace_case.py` → 2 passed; chạy trong CI cùng `-k "lab9 and not advanced"` |
| Chưa chắc chắn | Trace không cho biết *vì sao* model chọn tin ticket (prompt hay logic variant). Report `E-seeded_regression-20261118-b938` cho thấy E-002 fail ở cả 5 seed, nhưng regression test mới cố định seed 11. MockLLM nên không chắc LLM thật lỗi giống vậy |
