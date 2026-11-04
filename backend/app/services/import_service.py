"""CSV / XLSX import helpers shared by the mission, training, and maintenance
mapping importers. Handles file parsing, column mapping auto-suggestion,
pilot-name canonicalization, and vehicle resolution.
"""
import csv
import io
import json
import re
import zipfile
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
    """Map one XLSX row's cells onto the header keys, stringifying values. A
    read-only sheet's row stops at its last cell, so the rest read as blank."""
    return {
        header: _xlsx_cell_to_str(row[i] if i < len(row) else None)
        for i, header in enumerate(headers)
        if header
    }


# Rows read from one file. Each parser reads one past the cap, so the caller
# can tell the file was cut short and say so instead of importing part of it
# silently.
MAX_IMPORT_ROWS = 5000

# What a workbook may unpack to. An upload is capped at 50 MB, but a zip can
# hold far more than it weighs. This leaves room for 5 KB of cell markup on each
# of 100,000 rows, more than any export this app has been fed.
MAX_UNPACKED_BYTES = 512 * 1024 * 1024


class ImportTooLarge(ValueError):
    """A file over an import limit. The message says which, for the person importing."""


def _check_unpacked_size(content: bytes) -> None:
    """Refuse a workbook on the sizes its zip declares. Reading an entry stops at
    its declared size, so understating one does not get more past this."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            unpacked = sum(entry.file_size for entry in archive.infolist())
    except zipfile.BadZipFile:
        return  # Not a workbook at all; the parser says so in its own words.
    if unpacked > MAX_UNPACKED_BYTES:
        raise ImportTooLarge(
            f"This workbook unpacks to more than {MAX_UNPACKED_BYTES // (1024 * 1024)} MB, "
            "so it was not read and nothing was imported."
        )


def open_workbook(content: bytes):
    """Open a workbook to read row by row, after checking its unpacked size. The
    caller closes it, and reads sheets through open_sheet."""
    _check_unpacked_size(content)
    return openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)


def open_sheet(ws):
    """A read-only sheet ready to read. Read-only mode otherwise trusts the size
    the file declares, and some tools declare a single cell whatever it holds."""
    ws.reset_dimensions()
    return ws


def is_blank_row(row) -> bool:
    return all(cell is None or str(cell) == "" for cell in row)


def _parse_xlsx(content: bytes) -> tuple[list[str], list[dict]]:
    """Parse XLSX bytes into (headers, rows), reading no further than one row
    past the cap."""
    wb = open_workbook(content)
    try:
        raw = open_sheet(wb.active).iter_rows(values_only=True)
        first = next(raw, None)
        if first is None:
            return [], []
        headers = [str(h) if h is not None else "" for h in first]
        rows = []
        for row in raw:
            if not is_blank_row(row):
                rows.append(_xlsx_row_to_dict(row, headers))
                if len(rows) > MAX_IMPORT_ROWS:
                    break
        return headers, rows
    finally:
        wb.close()


def _parse_csv(content: bytes) -> tuple[list[str], list[dict]]:
    """Parse CSV bytes into (headers, rows)."""
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig", errors="replace")))
    headers = list(reader.fieldnames or [])
    rows = []
    for r in reader:
        rows.append({k: ("" if v is None else v) for k, v in r.items() if k})
        if len(rows) > MAX_IMPORT_ROWS:
            break
    return headers, rows


def parse_file(content: bytes, filename: str) -> tuple[list[str], list[dict], bool]:
    """Parse the uploaded CSV or XLSX into (headers, rows, truncated). Rows are
    dicts keyed by header, at most MAX_IMPORT_ROWS of them; truncated is True
    when the file had more."""
    is_xlsx = (filename or "").lower().endswith((".xlsx", ".xls"))
    headers, rows = _parse_xlsx(content) if is_xlsx else _parse_csv(content)
    return headers, rows[:MAX_IMPORT_ROWS], len(rows) > MAX_IMPORT_ROWS


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
