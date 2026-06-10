"""
Cleaning rules — raw export → cleaned rows + quarantine.

SINH VIÊN SỬA — Baseline mở rộng:
- Thêm access_control_sop vào ALLOWED_DOC_IDS (thiếu → gq_d10_10 fail).
- Thay HR stale date-based → content-based (bắt "10 ngày phép năm", "bản HR 2025").
- Thêm ≥3 rule mới: "Nội dung không rõ ràng:", whitespace-only, noisy "!!!" prefix.
"""

from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

# [SV SỬA] Thêm access_control_sop — thiếu source này làm gq_d10_10 fail vì bị quarantine nhầm.
ALLOWED_DOC_IDS = frozenset(
    {
        "policy_refund_v4",
        "sla_p1_2026",
        "it_helpdesk_faq",
        "hr_leave_policy",
        "access_control_sop",
    }
)

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DMY_SLASH = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")


def _norm_text(s: str) -> str:
    return " ".join((s or "").strip().split()).lower()


def _stable_chunk_id(doc_id: str, chunk_text: str, seq: int) -> str:
    h = hashlib.sha256(f"{doc_id}|{chunk_text}|{seq}".encode("utf-8")).hexdigest()[:16]
    return f"{doc_id}_{seq}_{h}"


def _normalize_effective_date(raw: str) -> Tuple[str, str]:
    """
    Trả về (iso_date, error_reason).
    iso_date rỗng nếu không parse được.
    """
    s = (raw or "").strip()
    if not s:
        return "", "empty_effective_date"
    if _ISO_DATE.match(s):
        return s, ""
    m = _DMY_SLASH.match(s)
    if m:
        dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
        return f"{yyyy}-{mm}-{dd}", ""
    return "", "invalid_effective_date_format"


def load_raw_csv(path: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({k: (v or "").strip() for k, v in r.items()})
    return rows


def clean_rows(
    rows: List[Dict[str, str]],
    *,
    apply_refund_window_fix: bool = True,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Trả về (cleaned, quarantine).

    Baseline:
    1) Quarantine: doc_id không thuộc allowlist.
    2) Chuẩn hoá effective_date; quarantine nếu không parse được.
    3) [SV SỬA] HR stale: dùng content-based thay vì date-based.
    4) Quarantine: chunk_text rỗng hoặc effective_date rỗng.
    5) Loại trùng chunk_text (giữ bản đầu).
    6) Fix stale refund: 14→7 ngày.

    [SV THÊM] Rule mới:
    7) Quarantine chunk_text chỉ chứa whitespace (tránh expectation fail).
    8) Quarantine chunk_text chứa "Nội dung không rõ ràng:" (corrupted export).
    9) Clean noisy "!!!" prefix khỏi chunk_text.
    10) Normalize exported_at format (2026/04/11 → 2026-04-11).
    """
    quarantine: List[Dict[str, Any]] = []
    seen_text: set[str] = set()
    seen_keys: set[str] = set()  # (doc_id, norm_text) để tránh trùng có chủ đích
    cleaned: List[Dict[str, Any]] = []
    seq = 0

    for raw in rows:
        doc_id = raw.get("doc_id", "")
        text = raw.get("chunk_text", "")
        eff_raw = raw.get("effective_date", "")
        exported_at = raw.get("exported_at", "")

        # ── Rule 1: unknown doc_id ──
        if doc_id not in ALLOWED_DOC_IDS:
            quarantine.append({**raw, "reason": "unknown_doc_id"})
            continue

        # ── Rule 2: normalize effective_date ──
        eff_norm, eff_err = _normalize_effective_date(eff_raw)
        if eff_err == "empty_effective_date":
            quarantine.append({**raw, "reason": "missing_effective_date"})
            continue
        if eff_err == "invalid_effective_date_format":
            quarantine.append({**raw, "reason": eff_err, "effective_date_raw": eff_raw})
            continue

        # ── [SV SỬA] Rule 3: HR stale — content-based ──
        # Thay vì quarantine theo effective_date < 2026-01-01,
        # dùng nội dung để phát hiện bản HR 2025 (10 ngày) vs 2026 (12 ngày).
        # Tránh quarantine nhầm dòng 2026 content có date cũ (VD: dòng 65).
        if doc_id == "hr_leave_policy":
            text_lower = (text or "").lower()
            if "10 ngày phép năm" in text_lower or "bản hr 2025" in text_lower:
                quarantine.append(
                    {
                        **raw,
                        "reason": "stale_hr_content_10d_annual",
                        "effective_date_normalized": eff_norm,
                    }
                )
                continue

        # ── [SV THÊM] Rule 7: whitespace-only chunk ──
        if not (text or "").strip():
            quarantine.append({**raw, "reason": "whitespace_only_chunk"})
            continue

        # ── [SV THÊM] Rule 8: "Nội dung không rõ ràng:" ──
        if "Nội dung không rõ ràng:" in text:
            quarantine.append({**raw, "reason": "ambiguous_content_prefix"})
            continue

        # ── Rule 4 (gián tiếp): chunk_text rỗng ──
        # (đã bắt bởi whitespace-only rule ở trên)

        # ── Rule 5: dedup chính xác ──
        key = _norm_text(text)
        if key in seen_text:
            quarantine.append({**raw, "reason": "duplicate_chunk_text"})
            continue
        seen_text.add(key)

        # ── [SV THÊM] Rule 9: clean noisy "!!!" prefix ──
        fixed_text = text
        if fixed_text.startswith("!!!"):
            fixed_text = fixed_text.replace("!!!", "").strip()
            if not fixed_text:
                quarantine.append({**raw, "reason": "noise_only_after_strip"})
                continue
            fixed_text += " [cleaned: noise_prefix_removed]"

        # ── Rule 6: fix stale refund ──
        if apply_refund_window_fix and doc_id == "policy_refund_v4":
            if "14 ngày làm việc" in fixed_text:
                fixed_text = fixed_text.replace(
                    "14 ngày làm việc",
                    "7 ngày làm việc",
                )
                fixed_text += " [cleaned: stale_refund_window]"

        # ── [SV THÊM] Rule 10: normalize exported_at ──
        # Định dạng "2026/04/11T00:00:00" → "2026-04-11T00:00:00"
        exported_at = re.sub(r"^(\d{4})/(\d{2})/(\d{2})", r"\1-\2-\3", exported_at.strip())

        seq += 1
        cleaned.append(
            {
                "chunk_id": _stable_chunk_id(doc_id, fixed_text, seq),
                "doc_id": doc_id,
                "chunk_text": fixed_text,
                "effective_date": eff_norm,
                "exported_at": exported_at or "",
            }
        )

    return cleaned, quarantine


def write_cleaned_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("chunk_id,doc_id,chunk_text,effective_date,exported_at\n", encoding="utf-8")
        return
    fieldnames = ["chunk_id", "doc_id", "chunk_text", "effective_date", "exported_at"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def write_quarantine_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("chunk_id,doc_id,chunk_text,effective_date,exported_at,reason\n", encoding="utf-8")
        return
    keys: List[str] = []
    seen_k: set[str] = set()
    for r in rows:
        for k in r.keys():
            if k not in seen_k:
                seen_k.add(k)
                keys.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore", restval="")
        w.writeheader()
        for r in rows:
            w.writerow(r)
