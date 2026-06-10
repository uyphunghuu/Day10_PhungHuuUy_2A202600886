# Kiến trúc pipeline — Lab Day 10

**Nhóm:** Nhóm SV - AI in Action  
**Cập nhật:** 2026-04-13

---

## 1. Sơ đồ luồng

```
data/raw/policy_export_dirty.csv
        │
        ▼
  ┌─────────────┐
  │   Ingest    │  load_raw_csv() → 247 rows
  │  (etl_      │  Ghi log: raw_records
  │   pipeline) │
  └──────┬──────┘
         │
         ▼
  ┌──────────────────────┐
  │   Transform / Clean   │  cleaning_rules.py
  │  ───────────────────  │
  │  • allowlist doc_id   │  → quarantine: unknown_doc_id
  │  • normalize eff_date │  → quarantine: invalid/missing date
  │  • HR content-based   │  → quarantine: "10 ngày phép năm"
  │  • whitespace check   │  → quarantine: whitespace_only_chunk
  │  • ambiguous prefix   │  → quarantine: "Nội dung không rõ ràng:"
  │  • dedup chunk_text   │  → quarantine: duplicate
  │  • noise cleanup      │  → clean: "!!!" prefix → stripped
  │  • refund window fix  │  → clean: "14 ngày" → "7 ngày"
  │  • normalize exported │  → clean: "2026/04/11" → "2026-04-11"
  └──────┬──────────┬────┘
         │          │
         ▼          ▼
  ┌─────────┐  ┌──────────────┐
  │ cleaned │  │  quarantine  │
  │ .csv    │  │  .csv        │
  └────┬────┘  └──────────────┘
       │
       ▼
  ┌──────────────────┐
  │  Validate        │  expectations.py
  │  (expectations)  │  ── E1..E9
  │  ─────────────── │  • halt nếu E1/E2/E3/E5/E6/E7/E8 fail
  │  E1: min_one_row │  • warn nếu E4/E9 fail
  │  E2-E9: ...      │
  └──────┬───────────┘
         │ exit 0?
         ▼
  ┌──────────────────┐
  │  Embed → Chroma  │  cmd_embed_internal()
  │  (day10_kb)      │  • upsert chunk_id (idempotent)
  │                  │  • prune vector cũ không trong cleaned
  └──────┬───────────┘
         │
         ▼
  ┌──────────────────┐
  │  Manifest +      │  manifest_{run_id}.json
  │  Freshness check │  • latest_exported_at vs SLA (24h)
  └──────────────────┘
         │
         ▼
  ┌──────────────────┐
  │  Eval Retrieval  │  grading_run.py / eval_retrieval.py
  │  (before/after)  │  • 21 test_questions + 10 grading_questions
  └──────────────────┘
```

> **Điểm đo freshness:** pipeline publish manifest → `monitoring/freshness_check.py` đọc `latest_exported_at` so với SLA 24h.  
> **run_id:** ghi trong mọi artifact (log, manifest, cleaned CSV).  
> **Quarantine:** CSV riêng kèm lý do (reason column).

---

## 2. Ranh giới trách nhiệm

| Thành phần | Input | Output | Owner |
|------------|-------|--------|-------|
| Ingest | `data/raw/policy_export_dirty.csv` | list[dict] + log raw_records | Ingestion Owner |
| Transform | list[dict] | cleaned list + quarantine list | Cleaning Owner |
| Quality | cleaned list | ExpectationResult[] + halt flag | Quality Owner |
| Embed | cleaned CSV | Chroma collection `day10_kb` | Embed Owner |
| Monitor | manifest JSON | `PASS/WARN/FAIL` + detail | Monitor Owner |

---

## 3. Idempotency & rerun

- Upsert theo `chunk_id` = `sha256(doc_id|chunk_text|seq)[:16]` → cùng nội dung ghi đè, không nhân đôi.
- Trước khi upsert, pipeline xoá (`delete`) các id có trong collection cũ nhưng **không** trong cleaned run hiện tại → đảm bảo snapshot = đúng cleaned hiện tại.
- Rerun 2 lần cùng raw → cleaned giống hệt → collection không phình.

---

## 4. Liên hệ Day 09

- Cùng corpus `data/docs/` 5 tài liệu gốc (policy_refund_v4, sla_p1_2026, it_helpdesk_faq, hr_leave_policy, access_control_sop).
- Pipeline Day 10 **làm mới** vector store cho Day 09: embed cleaned chunks vào `day10_kb`, Day 09 có thể đọc từ collection này.
- Phát hiện data stale / sai → pipeline halt trước khi embed → agent không bao giờ đọc dữ liệu sai.

---

## 5. Rủi ro đã biết

- Raw CSV có exported_at cũ (2026-04-01) → freshness `FAIL` là bình thường, ghi nhận trong runbook.
- Một số chunk có effective_date rỗng nhưng content quan trọng → quarantine có thể mất context.
- `data_privacy_guideline` và `security_policy` là nguồn không có trong allowlist (cố ý) → không phải bug.
