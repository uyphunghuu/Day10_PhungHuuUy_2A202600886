# Data contract — Lab Day 10

---

## 1. Nguồn dữ liệu (source map)

| Nguồn | Phương thức ingest | Failure mode chính | Metric / alert |
|-------|-------------------|-------------------|----------------|
| `policy_export_dirty.csv` (5 hệ thống gộp) | `load_raw_csv()` — DictReader | duplicate chunk, date sai format, doc_id lạ, "Nội dung không rõ ràng:" | quarantine_records, cleaned_records, E8 no_ambiguous_prefix |
| `policy_refund_v4` | allowlist → clean → embed | stale "14 ngày làm việc" → refund rule | E3 refund_no_stale_14d_window (halt) |
| `hr_leave_policy` | allowlist → clean → embed | version conflict: "10 ngày" (2025) vs "12 ngày" (2026) | E6 hr_leave_no_stale_10d_annual (halt) |
| `sla_p1_2026` | allowlist → clean → embed | missing effective_date, whitespace chunk | E1 min_one_row, E9 doc_coverage |
| `it_helpdesk_faq` | allowlist → clean → embed | duplicate content, whitespace chunk | E5 effective_date_iso, E7 exported_at_iso |
| `access_control_sop` | **[SV thêm]** allowlist → clean → embed | bị quarantine nhầm do thiếu trong ALLOWED_DOC_IDS | E9 doc_coverage (warn → mất source) |

---

## 2. Schema cleaned

| Cột | Kiểu | Bắt buộc | Ghi chú |
|-----|------|----------|---------|
| chunk_id | string | Có | `sha256(doc_id\|chunk_text\|seq)[:16]` — ổn định khi rerun |
| doc_id | string | Có | Mã tài liệu nguồn, phải trong ALLOWED_DOC_IDS |
| chunk_text | string | Có | cleaned text: "!!!" prefix removed, refund window fixed |
| effective_date | date | Có | Format ISO `YYYY-MM-DD`, normalize từ DD/MM/YYYY |
| exported_at | datetime | Có | Format ISO `YYYY-MM-DDThh:mm:ss`, normalize từ "YYYY/MM/DD" |

---

## 3. Quy tắc quarantine vs drop

- **Quarantine (giữ lại CSV để debug):** record vi phạm → ghi vào `artifacts/quarantine/quarantine_*.csv` kèm `reason`.
- **Drop (xoá hẳn):** không có — quarantine là cơ chế duy nhất.
- **Merge lại:** chỉ khi sửa được cleaning rule và rerun pipeline.

---

## 4. Phiên bản & canonical

- Source of truth cho **policy refund**: `data/docs/policy_refund_v4.txt` (v4, cửa sổ 7 ngày).
- Source of truth cho **HR leave**: `data/docs/hr_leave_policy.txt` (2026, 12 ngày phép năm cho <3 năm).
- Stale version **HR 2025** (10 ngày) bị quarantine bởi content-based rule.
- Pipeline luôn dùng **bản mới nhất** theo doc_id + content analysis, không hard-code effective_date.
