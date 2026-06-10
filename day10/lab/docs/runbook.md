# Runbook — Lab Day 10 (incident tối giản)

---

## Symptom

> Agent / trả lời "14 ngày làm việc" thay vì "7 ngày làm việc" cho chính sách hoàn tiền.  
> Hoặc: trả lời "10 ngày phép năm" thay vì "12 ngày phép năm".  
> Hoặc: không tìm thấy thông tin về `access_control_sop`.

---

## Detection

- `etl_pipeline.py run` → **exit code 2** (PIPELINE_HALT do expectation fail).
- Log chứa `expectation[E3] FAIL` (refund) / `expectation[E6] FAIL` (HR stale) / `expectation[E9] WARN` (missing source).
- `eval_retrieval.py` → `hits_forbidden=yes` (chunk cũ "14 ngày" vẫn trong vector).
- `grading_run.py` → `contains_expected=false` hoặc `hits_forbidden=true`.

---

## Diagnosis

| Bước | Việc làm | Kết quả mong đợi |
|------|----------|------------------|
| 1 | Kiểm tra `artifacts/manifests/*.json` | run_id, raw_count, cleaned_count, quarantine_count |
| 2 | Mở `artifacts/quarantine/*.csv` | Xem record nào bị quarantine, reason gì |
| 3 | Mở `artifacts/logs/run_*.log` | Xem expectation nào FAIL, detail |
| 4 | Chạy `python grading_run.py --out tmp.jsonl` | Câu nào không pass? Xem top1_doc_id |
| 5 | Kiểm tra `ALLOWED_DOC_IDS` trong `cleaning_rules.py` | Có thiếu source không? |
| 6 | Chạy `python eval_retrieval.py` | Before/after comparison |

---

## Mitigation

- **Trường hợp expectation fail:** sửa cleaning rule (thêm allowlist, thêm rule) → rerun pipeline.
- **Trường hợp vector cũ:** pipeline tự động prune (xoá vector id không trong cleaned run hiện tại).
- **Trường hợp freshness FAIL:** SLA > 24h là bình thường với CSV mẫu (exported_at cũ). Nếu cần PASS, update `FRESHNESS_SLA_HOURS` trong .env hoặc cập nhật timestamp trong CSV (phải có lý do chính đáng).
- **Tạm thời:** có thể dùng `--skip-validate` (chỉ Sprint 3 inject, không dùng cho production).

---

## Prevention

- Add expectation mới (E7 exported_at format, E8 no ambiguous prefix, E9 doc coverage).
- Content-based HR stale rule thay vì date-based → quarantine chính xác, không miss version conflict.
- `access_control_sop` nằm trong allowlist → không còn quarantine nhầm.
- Alert channel Slack #data-pipeline khi `freshness_check=FAIL` hoặc pipeline exit ≠ 0.
