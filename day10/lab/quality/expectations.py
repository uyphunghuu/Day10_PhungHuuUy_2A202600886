"""
Expectation suite — baseline + [SV THÊM] E7, E8, E9.

[SV THÊM]
  E7 — exported_at format ISO (halt): phát hiện ngày export sai format lọt qua clean.
  E8 — no_ambiguous_prefix (halt): "Nội dung không rõ ràng:" không còn trong cleaned.
  E9 — doc_coverage (warn): đảm bảo mỗi source có ≥1 dòng cleaned (phát hiện mất source).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass
class ExpectationResult:
    name: str
    passed: bool
    severity: str  # "warn" | "halt"
    detail: str


def run_expectations(cleaned_rows: List[Dict[str, Any]]) -> Tuple[List[ExpectationResult], bool]:
    """
    Trả về (results, should_halt).

    should_halt = True nếu có bất kỳ expectation severity halt nào fail.
    """
    results: List[ExpectationResult] = []

    # E1: có ít nhất 1 dòng sau clean
    ok = len(cleaned_rows) >= 1
    results.append(
        ExpectationResult(
            "min_one_row",
            ok,
            "halt",
            f"cleaned_rows={len(cleaned_rows)}",
        )
    )

    # E2: không doc_id rỗng
    bad_doc = [r for r in cleaned_rows if not (r.get("doc_id") or "").strip()]
    ok2 = len(bad_doc) == 0
    results.append(
        ExpectationResult(
            "no_empty_doc_id",
            ok2,
            "halt",
            f"empty_doc_id_count={len(bad_doc)}",
        )
    )

    # E3: policy refund không được chứa cửa sổ sai 14 ngày (sau khi đã fix)
    bad_refund = [
        r
        for r in cleaned_rows
        if r.get("doc_id") == "policy_refund_v4"
        and "14 ngày làm việc" in (r.get("chunk_text") or "")
    ]
    ok3 = len(bad_refund) == 0
    results.append(
        ExpectationResult(
            "refund_no_stale_14d_window",
            ok3,
            "halt",
            f"violations={len(bad_refund)}",
        )
    )

    # E4: chunk_text đủ dài
    short = [r for r in cleaned_rows if len((r.get("chunk_text") or "")) < 8]
    ok4 = len(short) == 0
    results.append(
        ExpectationResult(
            "chunk_min_length_8",
            ok4,
            "warn",
            f"short_chunks={len(short)}",
        )
    )

    # E5: effective_date đúng định dạng ISO sau clean (phát hiện parser lỏng)
    iso_bad = [
        r
        for r in cleaned_rows
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", (r.get("effective_date") or "").strip())
    ]
    ok5 = len(iso_bad) == 0
    results.append(
        ExpectationResult(
            "effective_date_iso_yyyy_mm_dd",
            ok5,
            "halt",
            f"non_iso_rows={len(iso_bad)}",
        )
    )

    # E6: không còn marker phép năm cũ 10 ngày trên doc HR (conflict version sau clean)
    bad_hr_annual = [
        r
        for r in cleaned_rows
        if r.get("doc_id") == "hr_leave_policy"
        and "10 ngày phép năm" in (r.get("chunk_text") or "")
    ]
    ok6 = len(bad_hr_annual) == 0
    results.append(
        ExpectationResult(
            "hr_leave_no_stale_10d_annual",
            ok6,
            "halt",
            f"violations={len(bad_hr_annual)}",
        )
    )

    # ═══════════════════════════════════════════════════════════
    # [SV THÊM] E7: exported_at format ISO (halt)
    # ───────────────────────────────────────────────────────────
    # Phát hiện exported_at còn định dạng "2026/04/11" thay vì "2026-04-11".
    bad_exported = [
        r
        for r in cleaned_rows
        if not re.match(
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$",
            (r.get("exported_at") or "").strip(),
        )
    ]
    ok7 = len(bad_exported) == 0
    results.append(
        ExpectationResult(
            "exported_at_iso_format",
            ok7,
            "halt",
            f"bad_format_rows={len(bad_exported)}",
        )
    )

    # [SV THÊM] E8: no ambiguous prefix in cleaned
    # ───────────────────────────────────────────────────────────
    # "Nội dung không rõ ràng:" là corrupted export — không được lọt vào cleaned.
    bad_ambig = [
        r
        for r in cleaned_rows
        if "Nội dung không rõ ràng:" in (r.get("chunk_text") or "")
    ]
    ok8 = len(bad_ambig) == 0
    results.append(
        ExpectationResult(
            "no_ambiguous_content_prefix",
            ok8,
            "halt",
            f"ambiguous_rows={len(bad_ambig)}",
        )
    )

    # [SV THÊM] E9: doc_coverage (warn)
    # ───────────────────────────────────────────────────────────
    # Mỗi source trong ALLOWED_DOC_IDS phải có ≥1 dòng cleaned.
    expected_docs = {
        "policy_refund_v4",
        "sla_p1_2026",
        "it_helpdesk_faq",
        "hr_leave_policy",
        "access_control_sop",
    }
    present_docs = {r.get("doc_id") for r in cleaned_rows}
    missing = expected_docs - present_docs
    ok9 = len(missing) == 0
    results.append(
        ExpectationResult(
            "doc_coverage_all_sources",
            ok9,
            "warn",
            f"missing_docs={sorted(missing)}",
        )
    )

    halt = any(not r.passed and r.severity == "halt" for r in results)
    return results, halt
