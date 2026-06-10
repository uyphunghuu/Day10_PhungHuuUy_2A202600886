# Báo Cáo Nhóm — Lab Day 10: Data Pipeline & Data Observability

**Tên nhóm:** Nhóm SV - AI in Action  
**Thành viên:**
| Tên | Vai trò (Day 10) | Email |
|-----|------------------|-------|
| [Tên 1] | Ingestion / Raw Owner | [email] |
| [Tên 2] | Cleaning & Quality Owner | [email] |
| [Tên 3] | Embed & Idempotency Owner | [email] |
| [Tên 4] | Monitoring / Docs Owner | [email] |

**Ngày nộp:** 2026-04-13  
**Repo:** [link repo]  

---

## 1. Pipeline tổng quan

Nguồn raw là file `data/raw/policy_export_dirty.csv` (247 rows) chứa export từ 5 hệ thống nguồn: policy_refund_v4, sla_p1_2026, it_helpdesk_faq, hr_leave_policy, access_control_sop — cùng với dữ liệu lỗi từ các hệ thống cũ (invalid_doc_*, legacy_catalog_*, data_privacy_guideline, security_policy).

**Tóm tắt luồng:**
```
raw CSV (247 rows) → clean (quarantine unknown doc_id, date sai, HR stale, whitespace, ambiguous prefix, duplicate) → validate (9 expectations) → embed Chroma (upsert chunk_id, prune stale) → manifest + freshness check
```

**Lệnh chạy một dòng:**
```bash
python etl_pipeline.py run
python grading_run.py --out artifacts/eval/grading_run.jsonl
python eval_retrieval.py --out artifacts/eval/after_fix_eval.csv
```

`run_id` format: `2026-04-13T17-00Z` (UTC timestamp), ghi trong log, manifest, cleaned CSV.

---

## 2. Cleaning & expectation

### 2a. Bảng metric_impact

| Rule / Expectation mới | Trước (số liệu) | Sau / khi inject (số liệu) | Chứng cứ |
|------------------------|------------------|---------------------------|-----------|
| **access_control_sop** trong ALLOWED_DOC_IDS | `access_control_sop` bị quarantine (unknown_doc_id) | `access_control_sop` có 7 rows trong cleaned | `artifacts/quarantine/` trước fix không có access_control_sop |
| **HR content-based** (thay date-based) | HR stale quarantine sai dòng 65 (content 2026, date 2025) | Chỉ quarantine dòng "10 ngày phép năm" / "bản HR 2025" | diff `cleaning_rules.py` dòng 103-113 |
| **Whitespace rule** | Chunk "    " (row 118, 163) pass qua clean → expectation fail E4 | Quarantine: `whitespace_only_chunk` | `artifacts/quarantine/` có reason=whitespace_only_chunk |
| **Ambiguous prefix rule** | "Nội dung không rõ ràng:" lọt vào cleaned | Quarantine: `ambiguous_content_prefix` | `artifacts/quarantine/` có reason=ambiguous_content_prefix |
| **E7 exported_at format** | exported_at "2026/04/11" được embed | Halt → fix normalize → pass | `quality/expectations.py` E7 |
| **E8 no ambiguous prefix** | Đảm bảo không còn "Nội dung không rõ ràng:" trong cleaned | Halt nếu còn | `quality/expectations.py` E8 |
| **E9 doc_coverage** | access_control_sop missing → không biết | Warn: missing_docs | `quality/expectations.py` E9 |

**Rule chính (baseline + mở rộng):**

| # | Rule | Loại | Impact |
|---|------|------|--------|
| 1 | allowlist doc_id (thêm access_control_sop) | Quarantine | Fix gq_d10_10 — access_control_sop không còn bị quarantine |
| 2 | effective_date normalize | Quarantine | Parse DD/MM/YYYY → YYYY-MM-DD |
| 3 | HR stale — content-based | Quarantine | "10 ngày phép năm" → stale; "12 ngày" → keep |
| 4 | whitespace-only chunk_text | Quarantine | Chunk rỗng/spaces → quarantine |
| 5 | ambiguous prefix "Nội dung không rõ ràng:" | Quarantine | Corrupted export → quarantine |
| 6 | dedup chunk_text | Quarantine | Giữ bản đầu, loại trùng |
| 7 | refund window fix (14→7) | Clean | Sửa content + tag [cleaned: stale_refund_window] |
| 8 | noise "!!!" prefix | Clean | Strip prefix + tag [cleaned: noise_prefix_removed] |
| 9 | exported_at format normalize | Clean | "2026/04/11" → "2026-04-11" |

**Ví dụ expectation fail:** Chạy pipeline baseline → `E6 hr_leave_no_stale_10d_annual FAIL` vì "10 ngày phép năm" còn trong cleaned (do HR date-based rule không bắt được dòng có date 2026 nhưng content 2025). Sửa thành content-based → pass.

---

## 3. Before / after ảnh hưởng retrieval hoặc agent

**Kịch bản inject (Sprint 3):**
```
python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate
```
Không áp dụng refund fix (14→7), skip validate → embed dữ liệu "bẩn" (refund window 14 ngày).

**Trước inject (clean pipeline):**
- `q_refund_window`: `contains_expected=yes` (không chứa "14 ngày"), `hits_forbidden=no`
- `q_hr_annual_leave_under3`: `contains_expected=yes` (chứa "12 ngày")

**Sau inject (no fix):**
- `q_refund_window`: `hits_forbidden=yes` (chunk "14 ngày làm việc" vẫn xuất hiện trong top-k)
- `q_hr_annual_leave_under3`: `hits_forbidden=yes` (chunk "10 ngày phép năm" vẫn còn)

**Sau fix (rerun clean):**
- Tất cả pass: `contains_expected=yes`, `hits_forbidden=no`, `top1_doc_matches=true`

File so sánh: `artifacts/eval/before_after_eval.csv`

---

## 4. Freshness & monitoring

SLA chọn: **24 giờ** (phù hợp với tần suất export dữ liệu mẫu 1 lần/ngày).

- `freshness_check=PASS`: dữ liệu mới hơn SLA (exported_at trong vòng 24h so với thời điểm chạy).
- `freshness_check=FAIL`: dữ liệu quá cũ → cần rerun pipeline với raw mới.
- `freshness_check=WARN`: manifest thiếu timestamp → cần kiểm tra pipeline.

Trên dataset mẫu, `exported_at` có giá trị từ 2026-04-01 đến 2026-04-11 → nếu chạy vào 2026-04-13, `freshness_check` trả về `FAIL` do age > 24h. Đây là expected behavior (SLA đo "data snapshot", không phải "pipeline run").

---

## 5. Liên hệ Day 09

Day 10 pipeline embed cleaned chunks vào Chroma collection `day10_kb` — đây có thể là nguồn retrieval cho multi-agent Day 09. Cùng corpus `data/docs/` 5 tài liệu gốc (thêm access_control_sop so với Day 08/09). Agent Day 09 sẽ đọc vector từ collection này thay vì collection cũ, đảm bảo dữ liệu sạch và đúng version.

---

## 6. Rủi ro còn lại & việc chưa làm

- `data_privacy_guideline` và `security_policy` không nằm trong allowlist — không phải bug vì đây là data không thuộc phạm vi CS + IT Helpdesk.
- Freshness `FAIL` trên data mẫu — cần cập nhật `FRESHNESS_SLA_HOURS` hoặc timestamp nếu muốn PASS.
- Chưa tích hợp Great Expectations thật (dùng custom expectation suite đơn giản).
- Chưa có alert channel thật (Slack webhook).
