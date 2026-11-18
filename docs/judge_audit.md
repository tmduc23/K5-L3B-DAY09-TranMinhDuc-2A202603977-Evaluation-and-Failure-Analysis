# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5`

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Đạt cả 3 | **dùng** (tp=24, fp=4, fn=6, tn=66; fail rate 0.28 → RG 0.30) |
| helpful | 100 | 0.375 | 1.000 | 0.300 | **Không** (κ, R dưới sàn) | **loại** (tp=9, fp=0, fn=21, tn=70; fail rate 0.09 → RG 0.30) |

## ≥5 case audit thủ công
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha…" | PASS | FAIL | Người | Xưng "em" + "nha" quá suồng sã. Rubric: thêm quy tắc xưng hô bắt buộc "LogiX – anh/chị", liệt kê từ cấm ("nha", "em" khi xưng với khách) + 1 ví dụ FAIL. |
| 2 | H-017 "Dạ, bạn ơi LogiX đã hoàn 25.000đ…" | PASS | FAIL | Người | Xưng "bạn" với khách. Rubric: gộp vào quy tắc xưng hô ở #1; ghi rõ "thân thiện ≠ suồng sã". |
| 3 | H-029 "Dạ, vui lòng chờ… không cần nhắn thêm." | PASS | FAIL | Người | Judge chỉ nhìn từ lịch sự ở đầu câu. Rubric: chấm giọng của **cả câu**; thêm tiêu chí "không ra lệnh/không gạt khách" kèm ví dụ này. |
| 4 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Judge phạt vì thiếu xin lỗi. Rubric: ghi rõ "xin lỗi **không** bắt buộc khi đã giải quyết xong; ngắn gọn, đủ ý = PASS". |
| 5 | H-051 "Dạ, LogiX đã refund 90.000đ…" | FAIL | PASS | Người | CS LogiX cho phép từ "refund". Rubric: thêm whitelist thuật ngữ được phép (refund, ship, voucher). |
| 6 | HL-015 "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." (ledger 40.000đ) | PASS | FAIL | Người | Judge không thấy ledger nên không thể biết tiền sai. **Không sửa rubric judge** — chuyển sang grader code FM-08 (so số trong reply với ledger). |
| 7 | HL-016 / HL-028 / HL-035 (xin lỗi dài, ledger 35.000đ nhưng reply 50–55.000đ) | PASS | FAIL | Người | Verbosity bias: xin lỗi nhiều → PASS dù sai tiền. Rubric helpful: cấm thưởng điểm cho lời xin lỗi lặp; tách "đúng nội dung" (code) khỏi "hữu ích" (judge). |

## Kết luận
- **tone_ok: dùng được.** κ=0.757, P=0.857, R=0.8 đều đạt sàn. Lỗi còn lại chủ yếu là fn (6): judge bỏ sót xưng hô suồng sã và giọng ra lệnh (#1–3) → bổ sung rubric xưng hô/giọng điệu và kiểm lại.
- **helpful: loại, không được dùng làm gate.** R=0.3 → bỏ sót 21/30 reply hỏng; κ=0.375 < 0.6. P=1.0 không cứu được: judge chỉ nói FAIL khi quá rõ ràng. Tỉ lệ lỗi quan sát 0.09 nhưng hiệu chỉnh Rogan-Gladen là 0.30, tức dùng judge này sẽ báo agent tốt gấp ~3 lần thực tế. Nếu làm gate, một PR làm sai tiền vẫn được merge.
- **Phần lớn lỗi bị bỏ sót là "sai tiền"** — đây là FM-08, phải chấm bằng code (metric FM-08 ở M3), không bằng judge. Quy tắc: tiền và approval luôn chấm bằng code.
- **Rủi ro còn lại:** judge chỉ được kiểm trên CSV replay đã công khai (có thể đã overfit rubric vào chính tập này); cần bộ nhãn người mới (held-out) sau khi sửa rubric, và kiểm lại định kỳ khi đổi model judge.
