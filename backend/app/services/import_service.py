"""CSV / XLSX import helpers shared by the mission, training, and maintenance
mapping importers. Handles file parsing, column mapping auto-suggestion,
pilot-name canonicalization, and vehicle resolution.
"""
import csv
import io
import json
import re
from datetime import date, datetime
from typing import Optional

import openpyxl
from sqlalchemy.orm import Session

from app.models.pilot import Pilot
from app.models.vehicle import Vehicle


def _xlsx_cell_to_str(cell) -> str:
    """Stringify one XLSX cell value. Dates/datetimes get formatted; None becomes ''."""
    if isinstance(cell, datetime):
        return cell.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(cell, date):
        return cell.strftime("%Y-%m-%d")
    return "" if cell is None else str(cell)


def _xlsx_row_to_dict(row, headers: list[str]) -> dict:
    """Map one XLSX row's cells onto the header keys, stringifying values."""
    d = {}
    for i, cell in enumerate(row):
        if i >= len(headers) or not headers[i]:
            continue
        d[headers[i]] = _xlsx_cell_to_str(cell)
    return d


def _parse_xlsx(content: bytes) -> tuple[list[str], list[dict]]:
    """Parse XLSX bytes into (headers, rows)."""
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    raw = list(wb.active.iter_rows(values_only=True))
    if not raw:
        return [], []
    headers = [str(h) if h is not None else "" for h in raw[0]]
    rows = [
        _xlsx_row_to_dict(row, headers)
        for row in raw[1:5001]
        if any(cell is not None and str(cell) != "" for cell in row)
    ]
    return headers, rows


def _parse_csv(content: bytes) -> tuple[list[str], list[dict]]:
    """Parse CSV bytes into (headers, rows)."""
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig", errors="replace")))
    headers = list(reader.fieldnames or [])
    rows = []
    for r in reader:
        rows.append({k: ("" if v is None else v) for k, v in r.items() if k})
        if len(rows) >= 5000:
            break
    return headers, rows


def parse_file(content: bytes, filename: str) -> tuple[list[str], list[dict]]:
    """Parse the uploaded CSV or XLSX into (headers, rows). Rows are dicts keyed
    by header. Caps at ~5000 rows for safety."""
    is_xlsx = (filename or "").lower().endswith((".xlsx", ".xls"))
    return _parse_xlsx(content) if is_xlsx else _parse_csv(content)


def _normalize_header(s: str) -> str:
    """Normalize a header or alias for fuzzy matching."""
    return (s or "").lower().strip().replace("_", " ").replace("-", " ")


def _candidates_for(field: dict) -> list[str]:
    """All normalized aliases a target field accepts: its declared aliases plus
    its key and label."""
    return [
        c for c in (
            _normalize_header(a)
            for a in field.get("aliases", []) + [field["key"], field.get("label", "")]
        )
        if c
    ]


def _best_header(candidates: list[str], norm_headers: list[tuple[str, str]]) -> str | None:
    """Pick the source header that best matches the candidates: exact first,
    then bidirectional substring. Returns the original (un-normalized) header
    or None."""
    for orig, hl in norm_headers:
        if hl in candidates:
            return orig
    for orig, hl in norm_headers:
        if any(c and (c in hl or hl in c) for c in candidates):
            return orig
    return None


def suggest_mapping(target_schema: list[dict], headers: list[str]) -> dict:
    """Best-effort target-field -> source-header mapping by alias / substring match."""
    norm_headers = [(h, _normalize_header(h)) for h in headers if h]
    suggested = {}
    for field in target_schema:
        chosen = _best_header(_candidates_for(field), norm_headers)
        if chosen:
            suggested[field["key"]] = chosen
    return suggested


_DATE_FORMATS = ("%m/%d/%Y", "%m-%d-%Y", "%Y-%m-%d", "%m/%d/%y", "%Y-%m-%d %H:%M:%S")


def parse_date_value(val) -> Optional[date]:
    if val is None or val == "":
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    s = str(val).strip()
    if not s or s.upper() == "N/A":
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_float_safe(val) -> Optional[float]:
    """Pull the first number out of a free-text cell. Handles entries like
    'Smith (13), Jones (13)' or '4 except Baker has 2' (returns 4)."""
    if val is None or val == "":
        return None
    s = str(val).strip()
    if not s:
        return None
    m = re.search(r"-?\d+\.?\d*", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def canonical_name(name: str) -> str:
    if not name:
        return ""
    return str(name).strip()


def split_members(val) -> list[str]:
    if not val:
        return []
    parts = re.split(r"[;\n]", str(val))
    out = []
    for p in parts:
        c = canonical_name(p)
        if c:
            out.append(c)
    return out


def parse_drone_list(val) -> list[str]:
    """Parse a 'Drone' column: JSON array like '[\"SkydioX10-bk7n\"]' or a
    semicolon-separated list, or a single value."""
    if not val:
        return []
    s = str(val).strip()
    if not s:
        return []
    try:
        arr = json.loads(s)
        if isinstance(arr, list):
            return [str(d).strip() for d in arr if str(d).strip()]
    except (ValueError, TypeError):
        pass
    return [d.strip() for d in re.split(r"[;\n]", s) if d.strip()]


def find_unknown_pilot(db: Session) -> Optional[int]:
    """Return the id of the 'Unknown' placeholder pilot, or None if none exists."""
    p = db.query(Pilot).filter(
        (Pilot.first_name.ilike("Unknown")) | (Pilot.last_name.ilike("Unknown"))
    ).first()
    return p.id if p else None


def resolve_pilot(db: Session, name: str, unknown_id: Optional[int]) -> tuple[Optional[int], bool]:
    """Resolve a member name to a pilot id. Returns (pilot_id, matched).
    Falls back to the Unknown pilot when no match is found."""
    if not name:
        return unknown_id, False
    canon = canonical_name(name)
    norm = canon.lower().strip()
    if not norm:
        return unknown_id, False
    for p in db.query(Pilot).all():
        full = f"{p.first_name or ''} {p.last_name or ''}".strip().lower()
        if full == norm or (p.email and p.email.lower() == norm):
            return p.id, True
    return unknown_id, False


def _strip_paren(s: str) -> str:
    return re.sub(r"\([^)]*\)", "", s or "").strip()


def resolve_vehicle(db: Session, drone_name: str) -> Optional[int]:
    """Match a drone name (e.g. 'SkydioX10-bk7n (Drone 3)') to a Vehicle by
    serial number. 'Brinc Lemur 2' falls back to manufacturer match."""
    if not drone_name:
        return None
    serial = _strip_paren(drone_name)
    if not serial:
        return None
    v = db.query(Vehicle).filter(Vehicle.serial_number.ilike(serial)).first()
    if v:
        return v.id
    if re.search(r"brinc|lemur", drone_name, re.IGNORECASE):
        v = db.query(Vehicle).filter(Vehicle.manufacturer.ilike("%brinc%")).first()
        if v:
            return v.id
    return None
