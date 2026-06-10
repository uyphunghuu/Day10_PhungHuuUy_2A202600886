# Quality report — Lab Day 10 (nhóm)

**run_id:** 2026-04-13T17-00Z  
**Ngày:** 2026-04-13

---

## 1. Tóm tắt số liệu

| Chỉ số | Trước (baseline) | Sau (sửa) | Ghi chú |
|--------|-------|-----|---------|
| raw_records | 247 | 247 | Không đổi |
| cleaned_records | ~140 (baseline) | ~120-130 | Tăng quarantine nhờ rule mới |
| quarantine_records | ~107 (baseline) | ~117-127 | quarantine thêm whitespace + ambiguous + HR stale content |
| Expectation halt? | Có (E6 fail) | Không (exit 0) | Content-based HR rule fix |

---

## 2. Before / after retrieval

**Câu hỏi then chốt:** refund window (`q_refund_window`)  
**Trước (baseline):** `contains_expected=yes, hits_forbidden=yes` (còn chunk "14 ngày" trong top-k)  
**Sau (sửa):** `contains_expected=yes, hits_forbidden=no` (chỉ còn "7 ngày")

**Merit:** versioning HR — `q_hr_annual_leave_under3`  
**Trước (date-based):** `contains_expected=yes, hits_forbidden=yes` (chunk "10 ngày" với date 2026-03-30 không bị quarantine)  
**Sau (content-based):** `contains_expected=yes, hits_forbidden=no` (mọi "10 ngày phép năm" bị quarantine)

---

## 3. Freshness & monitor

`freshness_check=FAIL` do CSV mẫu có `exported_at` cũ nhất là 2026-04-01 (age > 24h so với thời gian chạy).  
SLA chọn 24h — phù hợp với tần suất export 1 lần/ngày. Nếu cần PASS, update `FRESHNESS_SLA_HOURS=72` trong .env vì data mẫu có độ trễ cố ý.

---

## 4. Corruption inject (Sprint 3)

Inject bằng lệnh:
```
python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate
```
Cố ý: (1) không fix refund window → chunk "14 ngày làm việc" vẫn được embed; (2) skip validate → E3 không halt.  
Kết quả eval: `q_refund_window` có `hits_forbidden=yes` do vector còn chứa "14 ngày". Sau rerun clean pipeline → pass.

---

## 5. Hạn chế & việc chưa làm

- Chưa dùng Great Expectations thật (custom expectation suite đơn giản).
- Chưa có Slack alert tự động.
- Freshness check chỉ dùng 1 boundary (publish), chưa đo ingest riêng.
- Có thể thêm rule phát hiện "làm việc làm việc" (repeated word) nếu cần.
