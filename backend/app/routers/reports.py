import io
import logging
import os
from datetime import date
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.constants import APP_TITLE
from app.config import settings
from app.deps import DBSession, PilotUser
from app.models.flight import Flight
from app.models.pilot import Pilot
from app.services.flight_scope import counted_flight_clause, counted_only
from app.models.vehicle import Vehicle
from app.models.certification import CertificationType, PilotCertification
from app.models.operating_authority import (
    AUTHORITY_TYPE_LABELS, DERIVED_STATUS_LABELS, RECORD_STATUS_LABELS,
    OperatingAuthority, authority_status,
)
from app.models.battery import Battery
from app.models.maintenance import MaintenanceRecord
from app.models.setting import Setting
from app.models.mission_log import MissionLog
from app.models.mission_log_pilot import MissionLogPilot
from app.models.training_log import TrainingLog
from app.models.training_log_pilot import TrainingLogPilot
from app.responses import responses

router = APIRouter(prefix="/api/reports", tags=["reports"])

logger = logging.getLogger(__name__)

# Hard cap on the number of per-pilot PDFs rendered into a single ZIP. Generous
# so normal batches are unaffected; bounds an otherwise unbounded render loop.
MAX_PER_PILOT_REPORTS = 500


class ReportConfig(BaseModel):
    report_type: str  # flight_summary, pilot_hours, equipment_utilization, pilot_certifications, battery_status, maintenance_history
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    pilot_ids: list[int] = []
    vehicle_ids: list[int] = []
    # Off by default: a report is the unit's own activity unless asked
    # otherwise. Turning it on restores vendor and guest operator flights, and
    # any flight individually marked as not the unit's.
    include_non_unit: bool = False


class ReportRow(BaseModel):
    label: str
    values: dict


def _flight_conds(include_all: bool, *conditions):
    """Flight conditions plus the counted-flight rule, unless overridden.

    Spread into ``filter(*...)`` so a helper that does not take a
    ReportConfig still applies exactly the same rule as one that does.
    """
    return list(conditions) if include_all else [counted_flight_clause(), *conditions]


def _dispatch_report(config: ReportConfig, db: Session) -> dict:
    """Dispatch to the appropriate report generator by type."""
    generators = {
        "flight_summary": _flight_summary,
        "pilot_hours": _pilot_hours,
        "equipment_utilization": _equipment_utilization,
        "pilot_certifications": _pilot_certifications,
        "battery_status": _battery_status,
        "maintenance_history": _maintenance_history,
        "pilot_activity_summary": _pilot_activity_summary,
        "annual_unit_report": _annual_unit_report,
        "per_pilot_annual_review": _per_pilot_annual_review,
    }
    generator = generators.get(config.report_type)
    if generator:
        return generator(config, db)
    return {"error": "Unknown report type"}


@router.post("/generate", responses=responses(401))
def generate_report(config: ReportConfig, db: DBSession, user: PilotUser):
    return _dispatch_report(config, db)


def _find_org_logo() -> str | None:
    """Find the organization logo file path, if any."""
    for ext in ["png", "jpg", "jpeg", "gif", "webp"]:
        candidate = os.path.join(str(settings.UPLOAD_DIR), "org", f"logo.{ext}")
        if os.path.exists(candidate):
            return candidate
    logo_dir = os.path.join(str(settings.UPLOAD_DIR), "org")
    if os.path.isdir(logo_dir):
        for f in os.listdir(logo_dir):
            if f.lower().startswith("logo"):
                return os.path.join(logo_dir, f)
    return None


# Summary tiles per row. Dividing the page by the number of fields put a
# thirteen-field summary into 0.56in columns, so every label wrapped onto three
# or four lines; capping the row width keeps each label on one or two.
# Masthead logo width. Named because it is a starting point to tune by eye.
LOGO_WIDTH_INCHES = 2.0

SUMMARY_COLUMNS = 4


def _build_pdf_summary_table(summary: dict, styles, primary_light, avail_width) -> list:
    """Build PDF summary tiles from a summary dict, wrapped into a grid.

    Laid out as label/value pairs in rows of SUMMARY_COLUMNS rather than one
    long row, so a report with many summary fields stays readable instead of
    squeezing each column until the headings wrap.
    """
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import Table, TableStyle, Spacer
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph

    if not summary:
        return []

    label_style = ParagraphStyle("SH", parent=styles["Normal"], fontSize=8,
                                 leading=10, textColor=HexColor("#64748b"))
    value_style = ParagraphStyle("SV", parent=styles["Normal"], fontSize=12,
                                 leading=14, textColor=HexColor("#1e293b"))

    items = [
        (Paragraph(f"<b>{key.replace('_', ' ').title()}</b>", label_style),
         Paragraph(f"<b>{value}</b>", value_style))
        for key, value in summary.items()
    ]

    cols = min(SUMMARY_COLUMNS, len(items))
    col_w = avail_width / cols

    rows = []
    for start in range(0, len(items), cols):
        chunk = items[start:start + cols]
        pad = [""] * (cols - len(chunk))          # keep the grid rectangular
        rows.append([label for label, _ in chunk] + pad)
        rows.append([value for _, value in chunk] + pad)

    table = Table(rows, colWidths=[col_w] * cols)
    style = [
        ("BACKGROUND", (0, 0), (-1, -1), primary_light),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.5, HexColor("#bfdbfe")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, HexColor("#bfdbfe")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]
    # Trailing padding cells in the final row are blanked so a part-full row
    # does not read as empty data tiles.
    filled = len(items) % cols
    if filled:
        style.append(("BACKGROUND", (filled, len(rows) - 2), (-1, -1), HexColor("#ffffff")))
    table.setStyle(TableStyle(style))

    return [table, Spacer(1, 16)]


def _build_pdf_data_table(rows: list, columns: list, header_bg, alt_row, white, cell_style, header_cell_style, avail_width) -> list:
    """Build PDF data table elements."""
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import Table, TableStyle, Paragraph

    table_header = [Paragraph(f"<b>{c}</b>", header_cell_style) for c in columns]
    table_data = [table_header]

    for row in rows[:200]:
        vals = list(row.values())
        table_row = [Paragraph(str(v) if v is not None else "-", cell_style) for v in vals]
        table_data.append(table_row)

    col_w = avail_width / max(len(columns), 1)
    t = Table(table_data, colWidths=[col_w] * len(columns), repeatRows=1)
    style_commands = [
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.25, HexColor("#e2e8f0")),
    ]
    for i in range(1, len(table_data)):
        if i % 2 == 0:
            style_commands.append(("BACKGROUND", (0, i), (-1, i), alt_row))
    t.setStyle(TableStyle(style_commands))
    return [t]


def _get_org_branding(db: Session) -> tuple[str, str | None]:
    """Return (org_name, logo_path) for the PDF header."""
    org_name_setting = db.query(Setting).filter(Setting.key == "org_name").first()
    logo_setting = db.query(Setting).filter(Setting.key == "org_logo").first()
    org_name = org_name_setting.value if org_name_setting else APP_TITLE
    logo_path = _find_org_logo() if (logo_setting and logo_setting.value) else None
    return org_name, logo_path


def _render_report_pdf(data: dict, config: ReportConfig, org_name: str, logo_path: str | None) -> io.BytesIO:
    """Render a report dict to a PDF and return the BytesIO buffer."""
    import matplotlib
    matplotlib.use("Agg")
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.colors import HexColor
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Image as RLImage,
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        topMargin=0.5 * inch, bottomMargin=0.5 * inch,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
    )
    styles = getSampleStyleSheet()
    elements = []

    primary = HexColor("#1e40af")
    primary_light = HexColor("#dbeafe")
    header_bg = HexColor("#1e293b")
    alt_row = HexColor("#f8fafc")
    white = colors.white
    avail_width = letter[0] - 1.2 * inch

    title_style = ParagraphStyle("ReportTitle", parent=styles["Title"], fontSize=20, textColor=primary, spaceAfter=4, alignment=TA_LEFT)
    subtitle_style = ParagraphStyle("ReportSubtitle", parent=styles["Normal"], fontSize=10, textColor=HexColor("#64748b"), spaceAfter=12)
    heading_style = ParagraphStyle("SectionHeading", parent=styles["Heading2"], fontSize=14, textColor=primary, spaceBefore=16, spaceAfter=8)
    cell_style = ParagraphStyle("CellStyle", parent=styles["Normal"], fontSize=8, leading=10)
    header_cell_style = ParagraphStyle("HeaderCell", parent=styles["Normal"], fontSize=8, leading=10, textColor=white)

    # Masthead: logo on the left, organization over report title to its right,
    # rather than the logo sitting alone on its own line above centred text.
    from reportlab.platypus import Table, TableStyle

    logo_flowable = None
    if logo_path:
        try:
            from PIL import Image as PILImage
            with PILImage.open(logo_path) as pil_img:
                img_w, img_h = pil_img.size
            aspect = (img_h / img_w) if img_w else 1
            logo_w = LOGO_WIDTH_INCHES * inch
            logo_flowable = RLImage(logo_path, width=logo_w, height=logo_w * aspect)
            logo_flowable.hAlign = "LEFT"
        except Exception:
            logo_flowable = None

    date_range = data.get("summary", {}).get("date_range") or f"{config.date_from or 'All'} to {config.date_to or 'Present'}"
    masthead_text = [
        Paragraph(org_name, title_style),
        Paragraph(data.get("title", "Report"), ParagraphStyle(
            "RPTitle", parent=styles["Heading1"], fontSize=16,
            textColor=HexColor("#334155"), spaceAfter=4, alignment=TA_LEFT)),
        Paragraph(f"Date Range: {date_range}  |  Generated: {date.today()}", subtitle_style),
    ]

    if logo_flowable:
        logo_col = LOGO_WIDTH_INCHES * inch + 0.2 * inch
        masthead = Table(
            [[logo_flowable, masthead_text]],
            colWidths=[logo_col, avail_width - logo_col],
        )
        masthead.setStyle(TableStyle([
            ("VALIGN", (0, 0), (0, 0), "MIDDLE"),   # logo centred against the text
            ("VALIGN", (1, 0), (1, 0), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        elements.append(masthead)
    else:
        elements.extend(masthead_text)
    elements.append(Spacer(1, 14))

    summary = data.get("summary", {})
    if summary:
        elements.extend(_build_pdf_summary_table(summary, styles, primary_light, avail_width))

    chart_buf = _generate_chart(config.report_type, data)
    if chart_buf:
        elements.append(Paragraph("Chart", heading_style))
        chart_img = RLImage(chart_buf, width=6.5 * inch, height=3 * inch)
        elements.append(chart_img)
        elements.append(Spacer(1, 12))

    rows = data.get("rows", [])
    columns = data.get("columns", [])
    sections = data.get("sections")
    # If the report uses multi-section layout, render each section; skip the
    # legacy top-level rows table (the YoY table is duplicated in the last section).
    if sections:
        narrative_style = ParagraphStyle("Narrative", parent=styles["Normal"], fontSize=10, leading=14, spaceAfter=8)
        for sec in sections:
            elements.append(Paragraph(sec.get("title", "Section"), heading_style))
            if sec.get("narrative"):
                elements.append(Paragraph(sec["narrative"], narrative_style))
            if sec.get("summary"):
                elements.extend(_build_pdf_summary_table(sec["summary"], styles, primary_light, avail_width))
            sec_rows = sec.get("rows") or []
            sec_cols = sec.get("columns") or []
            if sec_rows and sec_cols:
                elements.extend(_build_pdf_data_table(sec_rows, sec_cols, header_bg, alt_row, white, cell_style, header_cell_style, avail_width))
            elements.append(Spacer(1, 4))
    elif rows and columns:
        elements.append(Paragraph("Data", heading_style))
        elements.extend(_build_pdf_data_table(rows, columns, header_bg, alt_row, white, cell_style, header_cell_style, avail_width))

    doc.build(elements)
    buffer.seek(0)
    return buffer


@router.post("/generate/pdf", responses=responses(401))
def generate_report_pdf(config: ReportConfig, db: DBSession, user: PilotUser):
    data = _dispatch_report(config, db)
    if "error" in data:
        data = {"title": "Unknown Report", "summary": {}, "rows": [], "columns": []}
    org_name, logo_path = _get_org_branding(db)
    buffer = _render_report_pdf(data, config, org_name, logo_path)
    filename = f"{config.report_type}_{date.today()}.pdf"
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/per-pilot/zip", responses=responses(401))
def generate_per_pilot_zip(config: ReportConfig, db: DBSession, user: PilotUser):
    """Generate one Per-Pilot Annual Review PDF per pilot and return as a zip."""
    import zipfile

    if config.pilot_ids:
        pilots = db.query(Pilot).filter(Pilot.id.in_(config.pilot_ids)).all()
    else:
        pilots = db.query(Pilot).filter(Pilot.status == "active").all()
    if not config.include_non_unit:
        pilots = [p for p in pilots if p.counts_toward_totals]
    pilots.sort(key=lambda p: (p.last_name or "", p.first_name or ""))

    if len(pilots) > MAX_PER_PILOT_REPORTS:
        logger.warning(
            "per-pilot ZIP truncated: %d pilots exceeds cap of %d",
            len(pilots), MAX_PER_PILOT_REPORTS,
        )
        pilots = pilots[:MAX_PER_PILOT_REPORTS]

    org_name, logo_path = _get_org_branding(db)
    period_start, period_end, period_label = _annual_period(config)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for pilot in pilots:
            single_config = ReportConfig(
                report_type="per_pilot_annual_review",
                date_from=period_start,
                date_to=period_end,
                pilot_ids=[pilot.id],
                vehicle_ids=[],
            )
            data = _dispatch_report(single_config, db)
            pdf_buf = _render_report_pdf(data, single_config, org_name, logo_path)
            safe_name = (pilot.full_name or f"pilot_{pilot.id}").replace("/", "_").replace("\\", "_").replace(" ", "_")
            zf.writestr(f"{safe_name}_review_{period_label}.pdf", pdf_buf.read())

    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="per_pilot_reviews_{period_label}.zip"'},
    )


def _chart_bar_by_key(ax, rows, key, value_key, title, ylabel, colors, plt):
    """Draw a vertical bar chart counting rows by a key field."""
    counts = {}
    for r in rows:
        k = r.get(key, "Unknown")
        counts[k] = counts.get(k, 0) + (1 if value_key is None else r.get(value_key, 0))
    if not counts:
        return False
    labels = list(counts.keys())[:10]
    values = [counts[l] for l in labels]
    ax.bar(labels, values, color=colors[:len(labels)], edgecolor="white", linewidth=0.5)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.set_title(title, fontsize=11, fontweight="bold", color="#334155")
    plt.xticks(rotation=30, ha="right", fontsize=8)
    return True


def _chart_barh(ax, rows, label_key, value_key, title, xlabel, colors, plt, truncate=None):
    """Draw a horizontal bar chart from rows."""
    labels = [r.get(label_key, "?") for r in rows][:10]
    if truncate:
        labels = [l[:truncate] for l in labels]
    values = [r.get(value_key, 0) for r in rows][:10]
    ax.barh(labels, values, color=colors[:len(labels)], edgecolor="white", linewidth=0.5)
    ax.set_xlabel(xlabel, fontsize=9)
    ax.set_title(title, fontsize=11, fontweight="bold", color="#334155")
    ax.invert_yaxis()
    plt.yticks(fontsize=8)


def _chart_grouped_bars(ax, rows, label_key, hr_keys, title, limit=10):
    """Draw a grouped bar chart with flight/mission/training hours."""
    import numpy as np
    labels = [str(r.get(label_key, "?")) for r in rows][:limit]
    groups = [[r.get(k, 0) for r in rows][:limit] for k in hr_keys]
    x = np.arange(len(labels))
    width = 0.25
    bar_colors = ["#3b82f6", "#10b981", "#f59e0b"]
    bar_labels = ["Flight", "Mission", "Training"]
    for i, (vals, color, lbl) in enumerate(zip(groups, bar_colors, bar_labels)):
        ax.bar(x + (i - 1) * width, vals, width, label=lbl, color=color, edgecolor="white", linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("Hours", fontsize=9)
    ax.set_title(title, fontsize=11, fontweight="bold", color="#334155")
    ax.legend(fontsize=8)


def _generate_chart(report_type: str, data: dict) -> io.BytesIO | None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = data.get("rows", [])
    if not rows:
        return None

    fig, ax = plt.subplots(figsize=(8, 3.5))
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#fafbfc")

    chart_colors = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899", "#06b6d4", "#84cc16"]

    def _chart_flight_summary():
        return _chart_bar_by_key(ax, rows, "purpose", None, "Flights by Purpose", "Flights", chart_colors, plt)

    def _chart_pilot_hours():
        _chart_barh(ax, rows, "pilot", "hours", "Hours by Pilot", "Hours", chart_colors, plt)
        return True

    def _chart_equipment():
        _chart_barh(ax, rows, "vehicle", "hours", "Hours by Vehicle", "Hours", chart_colors, plt, truncate=20)
        return True

    def _chart_battery_status():
        status_counts = {}
        for r in rows:
            s = r.get("status", "unknown")
            status_counts[s] = status_counts.get(s, 0) + 1
        if status_counts:
            ax.pie(list(status_counts.values()), labels=list(status_counts.keys()),
                   colors=chart_colors[:len(status_counts)],
                   autopct="%1.0f%%", startangle=90, textprops={"fontsize": 9})
            ax.set_title("Battery Status Distribution", fontsize=11, fontweight="bold", color="#334155")
        return True

    def _chart_maintenance():
        return _chart_bar_by_key(ax, rows, "type", None, "Records by Type", "Records", chart_colors, plt)

    def _chart_pilot_certs():
        summary = data.get("summary", {})
        cats = ["Active", "Expired", "Pending"]
        vals = [summary.get("total_active", 0), summary.get("total_expired", 0), summary.get("total_pending", 0)]
        ax.bar(cats, vals, color=["#10b981", "#ef4444", "#f59e0b"], edgecolor="white", linewidth=0.5)
        ax.set_ylabel("Count", fontsize=9)
        ax.set_title("Certification Status", fontsize=11, fontweight="bold", color="#334155")
        return True

    def _chart_pilot_activity():
        _chart_grouped_bars(ax, rows, "pilot", ["flight_hours", "mission_hours", "training_hours"],
                            "Hours by Pilot (Flight / Mission / Training)")
        return True

    def _chart_annual():
        _chart_grouped_bars(ax, rows, "year", ["flight_hours", "mission_hours", "training_hours"],
                            "Year-over-Year Activity Hours", limit=15)
        return True

    chart_dispatch = {
        "flight_summary": _chart_flight_summary,
        "pilot_hours": _chart_pilot_hours,
        "equipment_utilization": _chart_equipment,
        "battery_status": _chart_battery_status,
        "maintenance_history": _chart_maintenance,
        "pilot_certifications": _chart_pilot_certs,
        "pilot_activity_summary": _chart_pilot_activity,
        "annual_unit_report": _chart_annual,
    }

    try:
        handler = chart_dispatch.get(report_type)
        if not handler or not handler():
            plt.close(fig)
            return None

        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.tick_params(axis="both", labelsize=8)
        plt.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="#ffffff")
        plt.close(fig)
        buf.seek(0)
        return buf

    except Exception:
        plt.close(fig)
        return None


def _flight_summary(config: ReportConfig, db: Session):
    q = counted_only(db.query(Flight), config.include_non_unit)
    if config.date_from:
        q = q.filter(Flight.date >= config.date_from)
    if config.date_to:
        q = q.filter(Flight.date <= config.date_to)
    if config.pilot_ids:
        q = q.filter(Flight.pilot_id.in_(config.pilot_ids))
    if config.vehicle_ids:
        q = q.filter(Flight.vehicle_id.in_(config.vehicle_ids))

    flights = q.order_by(Flight.date.desc()).all()
    total_seconds = sum(f.duration_seconds or 0 for f in flights)

    rows = []
    for f in flights:
        pilot = db.query(Pilot).filter(Pilot.id == f.pilot_id).first() if f.pilot_id else None
        vehicle = db.query(Vehicle).filter(Vehicle.id == f.vehicle_id).first() if f.vehicle_id else None
        rows.append({
            "date": str(f.date) if f.date else "",
            "pilot": pilot.full_name if pilot else "Unassigned",
            "vehicle": f"{vehicle.manufacturer} {vehicle.model}" if vehicle else "—",
            "purpose": f.purpose or "—",
            "duration_min": round((f.duration_seconds or 0) / 60, 1),
            "location": f.takeoff_address or "—",
        })

    return {
        "report_type": "flight_summary",
        "title": "Flight Summary Report",
        "summary": {
            "total_flights": len(flights),
            "total_hours": round(total_seconds / 3600, 1),
            "date_range": f"{config.date_from or 'All'} to {config.date_to or 'Present'}",
        },
        "columns": ["Date", "Pilot", "Vehicle", "Purpose", "Duration (min)", "Location"],
        "rows": rows,
    }


def _pilot_hours(config: ReportConfig, db: Session):
    from sqlalchemy import outerjoin, and_

    # Build the flight filter conditions for the outer join. These belong in the
    # join, not a WHERE clause: the outer join is what keeps pilots with no
    # matching flights in the report at 0 hours, and a WHERE on a joined column
    # would drop them (NULL never satisfies a comparison).
    join_conditions = [Flight.pilot_id == Pilot.id]
    if not config.include_non_unit:
        join_conditions.append(counted_flight_clause())
    if config.date_from:
        join_conditions.append(Flight.date >= config.date_from)
    if config.date_to:
        join_conditions.append(Flight.date <= config.date_to)
    if config.vehicle_ids:
        join_conditions.append(Flight.vehicle_id.in_(config.vehicle_ids))

    q = db.query(
        Pilot.id,
        Pilot.first_name, Pilot.last_name,
        func.count(Flight.id).label("flights"),
        func.coalesce(func.sum(Flight.duration_seconds), 0).label("seconds"),
    ).outerjoin(Flight, and_(*join_conditions))

    if config.pilot_ids:
        q = q.filter(Pilot.id.in_(config.pilot_ids))

    # Only include active pilots when no specific pilots are filtered
    if not config.pilot_ids:
        q = q.filter(Pilot.status == "active")

    # A vendor or guest operator would otherwise sit in the report at 0.0
    # hours, which reads as a unit pilot who did not fly.
    if not config.include_non_unit:
        q = q.filter(Pilot.counts_toward_totals.is_(True))

    rows = []
    for r in q.group_by(Pilot.id).order_by(func.sum(Flight.duration_seconds).desc()).all():
        rows.append({
            "pilot": f"{r.first_name} {r.last_name}",
            "flights": r.flights,
            "hours": round(r.seconds / 3600, 1),
            "avg_min": round(r.seconds / max(r.flights, 1) / 60, 1),
        })

    return {
        "report_type": "pilot_hours",
        "title": "Pilot Hours Report",
        "summary": {
            "total_pilots": len(rows),
            "total_hours": round(sum(r["hours"] for r in rows), 1),
            "date_range": f"{config.date_from or 'All'} to {config.date_to or 'Present'}",
        },
        "columns": ["Pilot", "Flights", "Hours", "Avg Duration (min)"],
        "rows": rows,
    }


def _equipment_utilization(config: ReportConfig, db: Session):
    from sqlalchemy import and_

    # Flight-side conditions belong in the join, not a WHERE: the outer join is
    # what lets an explicitly selected aircraft still appear at 0 hours, and a
    # WHERE on a joined column would drop it (NULL never satisfies a comparison).
    join_conditions = [Flight.vehicle_id == Vehicle.id]
    if not config.include_non_unit:
        join_conditions.append(counted_flight_clause())
    if config.date_from:
        join_conditions.append(Flight.date >= config.date_from)
    if config.date_to:
        join_conditions.append(Flight.date <= config.date_to)
    if config.pilot_ids:
        join_conditions.append(Flight.pilot_id.in_(config.pilot_ids))

    q = db.query(
        Vehicle.manufacturer, Vehicle.model, Vehicle.nickname, Vehicle.serial_number,
        func.count(Flight.id).label("flights"),
        func.coalesce(func.sum(Flight.duration_seconds), 0).label("seconds"),
    ).select_from(Vehicle).outerjoin(Flight, and_(*join_conditions))

    if config.vehicle_ids:
        q = q.filter(Vehicle.id.in_(config.vehicle_ids))

    rows = []
    for r in q.group_by(Vehicle.id).order_by(func.sum(Flight.duration_seconds).desc()).all():
        name = f"{r.manufacturer} {r.model}"
        if r.nickname:
            name += f" ({r.nickname})"
        rows.append({
            "vehicle": name,
            "serial": r.serial_number,
            "flights": r.flights,
            "hours": round(r.seconds / 3600, 1),
        })

    # Naming aircraft means "tell me about these", so they stay listed at 0.
    # With nothing named, keep the report's historical shape: only aircraft that
    # actually flew, rather than padding it with every vehicle on the books.
    if not config.vehicle_ids:
        rows = [r for r in rows if r["flights"]]

    return {
        "report_type": "equipment_utilization",
        "title": "Equipment Utilization Report",
        "summary": {
            "total_vehicles": len(rows),
            "total_hours": round(sum(r["hours"] for r in rows), 1),
            "date_range": f"{config.date_from or 'All'} to {config.date_to or 'Present'}",
        },
        "columns": ["Vehicle", "Serial", "Flights", "Hours"],
        "rows": rows,
    }


AUTHORITY_COLUMNS = ["Type", "Identifier", "Title", "Issued", "Expires", "Status"]


def _authority_section(db: Session, period_start: date | None = None, period_end: date | None = None) -> dict:
    """Operating authorities as a report section.

    With a period, limits the list to authorities the unit held at some point
    during it (issued on or before the end, not expired before the start), which
    is what "under what authority did you operate?" actually asks. Without one,
    lists every authority on file.
    """
    q = db.query(OperatingAuthority)
    if period_start and period_end:
        q = q.filter(
            or_(OperatingAuthority.issue_date.is_(None), OperatingAuthority.issue_date <= period_end),
            or_(OperatingAuthority.expiry_date.is_(None), OperatingAuthority.expiry_date >= period_start),
        )
    authorities = q.order_by(
        OperatingAuthority.authority_type,
        OperatingAuthority.expiry_date,
    ).all()

    today = date.today()
    rows = []
    active = 0
    expired = 0
    for a in authorities:
        derived = authority_status(a, today)
        if a.record_status == "active":
            status = DERIVED_STATUS_LABELS[derived]
            if derived == "expired":
                expired += 1
            else:
                active += 1
        else:
            status = RECORD_STATUS_LABELS[a.record_status]
        rows.append({
            "authority_type": AUTHORITY_TYPE_LABELS.get(a.authority_type, a.authority_type),
            "identifier": a.identifier or "—",
            "title": a.title,
            "issue_date": str(a.issue_date) if a.issue_date else "—",
            "expiry_date": str(a.expiry_date) if a.expiry_date else "No expiry",
            "status": status,
        })

    return {
        "title": "Operating Authorities",
        "type": "table",
        "summary": {
            "authorities_listed": len(rows),
            "currently_active": active,
            "expired": expired,
        },
        "columns": AUTHORITY_COLUMNS,
        "rows": rows,
    }


def _pilot_certifications(config: ReportConfig, db: Session):
    q = db.query(PilotCertification).join(Pilot, PilotCertification.pilot_id == Pilot.id).join(
        CertificationType, PilotCertification.certification_type_id == CertificationType.id
    )
    if config.pilot_ids:
        q = q.filter(PilotCertification.pilot_id.in_(config.pilot_ids))

    records = q.order_by(Pilot.last_name, Pilot.first_name, CertificationType.sort_order).all()

    total_active = 0
    total_expired = 0
    total_pending = 0
    rows = []
    today = date.today()

    for pc in records:
        pilot = pc.pilot
        ct = pc.certification_type
        days_until = None
        if pc.expiration_date:
            days_until = (pc.expiration_date - today).days

        if pc.status in ("active", "complete"):
            total_active += 1
        elif pc.status == "expired":
            total_expired += 1
        elif pc.status == "pending":
            total_pending += 1

        rows.append({
            "pilot": pilot.full_name if pilot else "Unknown",
            "cert_name": ct.name if ct else "Unknown",
            "status": pc.status.replace("_", " "),
            "issue_date": str(pc.issue_date) if pc.issue_date else "—",
            "expiration_date": str(pc.expiration_date) if pc.expiration_date else "—",
            "days_until_expiry": days_until if days_until is not None else "N/A",
        })

    pilot_ids_seen = {pc.pilot_id for pc in records}

    cert_columns = ["Pilot", "Cert Name", "Status", "Issue Date", COL_EXPIRATION_DATE, "Days Until Expiry"]

    return {
        "report_type": "pilot_certifications",
        "title": "Pilot Certifications Report",
        "summary": {
            "total_pilots": len(pilot_ids_seen),
            "total_active": total_active,
            "total_expired": total_expired,
            "total_pending": total_pending,
        },
        # Same audience and purpose as the certification matrix, so the unit's own
        # operating authorities are appended as a second section.
        "sections": [
            {"title": "Pilot Certifications", "type": "table", "columns": cert_columns, "rows": rows},
            _authority_section(db),
        ],
        # Kept at the top level for the chart and any consumer reading the flat
        # shape; the section renderers use "sections" in preference.
        "columns": cert_columns,
        "rows": rows,
    }


def _battery_status(config: ReportConfig, db: Session):
    batteries = db.query(Battery).order_by(Battery.serial_number).all()

    rows = []
    active_count = 0
    healths = []
    cycles = []

    for b in batteries:
        if b.status == "active":
            active_count += 1
        if b.health_pct is not None:
            healths.append(b.health_pct)
        cycles.append(b.cycle_count or 0)

        rows.append({
            "serial": b.serial_number,
            "manufacturer": b.manufacturer or "—",
            "model": b.model or "—",
            "vehicle_model": b.vehicle_model or "—",
            "cycles": b.cycle_count or 0,
            "health_pct": round(b.health_pct, 1) if b.health_pct is not None else "—",
            "status": b.status.replace("_", " "),
        })

    avg_health = round(sum(healths) / len(healths), 1) if healths else 0
    avg_cycles = round(sum(cycles) / len(cycles), 1) if cycles else 0

    return {
        "report_type": "battery_status",
        "title": "Battery Status Report",
        "summary": {
            "total_batteries": len(batteries),
            "active": active_count,
            "avg_health_pct": avg_health,
            "avg_cycles": avg_cycles,
        },
        "columns": ["Serial", "Manufacturer", "Model", "Vehicle Model", "Cycles", "Health %", "Status"],
        "rows": rows,
    }


def _maintenance_history(config: ReportConfig, db: Session):
    q = db.query(MaintenanceRecord)
    if config.date_from:
        q = q.filter(MaintenanceRecord.performed_date >= config.date_from)
    if config.date_to:
        q = q.filter(MaintenanceRecord.performed_date <= config.date_to)

    records = q.order_by(MaintenanceRecord.performed_date.desc()).all()

    total_cost = 0.0
    type_counts = {}
    rows = []

    for r in records:
        cost = r.cost or 0
        total_cost += cost
        mtype = r.maintenance_type or "other"
        type_counts[mtype] = type_counts.get(mtype, 0) + 1

        rows.append({
            "date": str(r.performed_date) if r.performed_date else "—",
            "entity_type": r.entity_type or "—",
            "description": (r.description[:80] + "...") if r.description and len(r.description) > 80 else (r.description or "—"),
            "type": mtype.replace("_", " "),
            "performed_by": r.performed_by or "—",
            "cost": f"${cost:,.2f}" if cost else "—",
        })

    by_type_str = ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in sorted(type_counts.items()))

    return {
        "report_type": "maintenance_history",
        "title": "Maintenance History Report",
        "summary": {
            "total_records": len(records),
            "total_cost": f"${total_cost:,.2f}",
            "records_by_type": by_type_str or "None",
            "date_range": f"{config.date_from or 'All'} to {config.date_to or 'Present'}",
        },
        "columns": ["Date", "Entity Type", "Description", "Type", "Performed By", "Cost"],
        "rows": rows,
    }


def _pilot_flight_hours(db: Session, pilot_id: int, config: ReportConfig) -> float:
    """Get total flight hours for a pilot within the config date range.

    Vehicle scoping applies here and nowhere else in the activity summary:
    mission and training hours are logged against a person, not an aircraft.

    A WHERE is correct here, unlike the outer join in _pilot_hours: the pilot row
    comes from a separate roster query, and coalesce returns 0 rather than
    dropping anyone whose flights are all filtered out.
    """
    fq = counted_only(
        db.query(func.coalesce(func.sum(Flight.duration_seconds), 0)).filter(
            Flight.pilot_id == pilot_id),
        config.include_non_unit,
    )
    if config.date_from:
        fq = fq.filter(Flight.date >= config.date_from)
    if config.date_to:
        fq = fq.filter(Flight.date <= config.date_to)
    if config.vehicle_ids:
        fq = fq.filter(Flight.vehicle_id.in_(config.vehicle_ids))
    return round((fq.scalar() or 0) / 3600, 1)


def _pilot_mission_hours(db: Session, pilot_id: int, config: ReportConfig) -> float:
    """Get total mission hours for a pilot within the config date range."""
    mq = db.query(func.coalesce(func.sum(MissionLogPilot.hours), 0)).filter(MissionLogPilot.pilot_id == pilot_id)
    if config.date_from or config.date_to:
        mq = mq.join(MissionLog, MissionLogPilot.mission_log_id == MissionLog.id)
        if config.date_from:
            mq = mq.filter(MissionLog.date >= config.date_from)
        if config.date_to:
            mq = mq.filter(MissionLog.date <= config.date_to)
    return round(mq.scalar() or 0, 1)


def _pilot_training_hours(db: Session, pilot_id: int, config: ReportConfig) -> float:
    """Get total training hours for a pilot within the config date range."""
    tq = db.query(func.coalesce(func.sum(TrainingLogPilot.hours), 0)).filter(TrainingLogPilot.pilot_id == pilot_id)
    if config.date_from or config.date_to:
        tq = tq.join(TrainingLog, TrainingLogPilot.training_log_id == TrainingLog.id)
        if config.date_from:
            tq = tq.filter(TrainingLog.date >= config.date_from)
        if config.date_to:
            tq = tq.filter(TrainingLog.date <= config.date_to)
    return round(tq.scalar() or 0, 1)


def _pilot_activity_summary(config: ReportConfig, db: Session):
    q = db.query(Pilot)
    if not config.include_non_unit:
        q = q.filter(Pilot.counts_toward_totals.is_(True))
    if config.pilot_ids:
        # Naming pilots explicitly overrides the active-only default, so a
        # selected inactive pilot still appears (matches the Pilot Hours report).
        q = q.filter(Pilot.id.in_(config.pilot_ids))
    else:
        q = q.filter(Pilot.status == "active")
    pilots = q.order_by(Pilot.last_name).all()

    rows = []
    total_flight_hrs = 0
    total_mission_hrs = 0
    total_training_hrs = 0

    for pilot in pilots:
        flight_hrs = _pilot_flight_hours(db, pilot.id, config)
        mission_hrs = _pilot_mission_hours(db, pilot.id, config)
        training_hrs = _pilot_training_hours(db, pilot.id, config)

        total_hrs = round(flight_hrs + mission_hrs + training_hrs, 1)
        total_flight_hrs += flight_hrs
        total_mission_hrs += mission_hrs
        total_training_hrs += training_hrs

        rows.append({
            "pilot": pilot.full_name,
            "flight_hours": flight_hrs,
            "mission_hours": mission_hrs,
            "training_hours": training_hrs,
            "total_hours": total_hrs,
        })

    rows.sort(key=lambda r: r["total_hours"], reverse=True)

    summary = {
        "total_pilots": len(rows),
        "total_flight_hours": round(total_flight_hrs, 1),
        "total_mission_hours": round(total_mission_hrs, 1),
        "total_training_hours": round(total_training_hrs, 1),
        "date_range": f"{config.date_from or 'All'} to {config.date_to or 'Present'}",
    }
    if config.vehicle_ids:
        # Say so rather than letting a mixed total read as fully scoped.
        summary["flight_hours_scope"] = (
            f"{len(config.vehicle_ids)} selected vehicle(s); "
            "mission and training hours are not aircraft-scoped"
        )

    return {
        "report_type": "pilot_activity_summary",
        "title": "Pilot Activity Summary",
        "summary": summary,
        "columns": ["Pilot", COL_FLIGHT_HOURS, COL_MISSION_HOURS, COL_TRAINING_HOURS, "Total Hours"],
        "rows": rows,
    }


def _pilot_service_span(db: Session, pilot_id: int, include_all: bool = False):
    """First flight, last flight, career flights and career hours for a pilot.

    Flights are the only evidence of time in service the data carries: a pilot
    record has no hire or start date, and its created_at is when the record was
    entered into the app (go-live for most of the roster), which would make every
    pilot look like they started on the same day.
    """
    first, last, flights, seconds = db.query(
        func.min(Flight.date),
        func.max(Flight.date),
        func.count(Flight.id),
        func.coalesce(func.sum(Flight.duration_seconds), 0),
    ).filter(*_flight_conds(include_all, Flight.pilot_id == pilot_id)).one()
    return first, last, flights or 0, round((seconds or 0) / 3600, 1)


def _pilot_vehicle_rows(db: Session, pilot_id: int, period_start: date, period_end: date,
                        include_all: bool = False) -> list[dict]:
    """Per-aircraft flight breakdown for one pilot inside the review period."""
    q = (
        db.query(
            Vehicle.manufacturer, Vehicle.model, Vehicle.nickname,
            func.count(Flight.id).label("flights"),
            func.coalesce(func.sum(Flight.duration_seconds), 0).label("seconds"),
        )
        .join(Flight, Flight.vehicle_id == Vehicle.id)
        .filter(*_flight_conds(include_all, Flight.pilot_id == pilot_id,
                               Flight.date.between(period_start, period_end)))
        .group_by(Vehicle.id)
    )
    rows = [
        {
            "vehicle": f"{r.manufacturer} {r.model}" + (f" ({r.nickname})" if r.nickname else ""),
            "flights": r.flights,
            "hours": round(r.seconds / 3600, 1),
        }
        for r in q.all()
    ]

    # Flights with no aircraft on record would otherwise vanish and leave this
    # table failing to add up to the pilot's flight hours.
    un_flights, un_seconds = db.query(
        func.count(Flight.id), func.coalesce(func.sum(Flight.duration_seconds), 0)
    ).filter(
        *_flight_conds(include_all,
                       Flight.pilot_id == pilot_id,
                       Flight.vehicle_id.is_(None),
                       Flight.date.between(period_start, period_end))
    ).one()
    if un_flights:
        rows.append({
            "vehicle": "Unassigned",
            "flights": un_flights,
            "hours": round((un_seconds or 0) / 3600, 1),
        })

    rows.sort(key=lambda r: r["hours"], reverse=True)
    return rows


def _pilot_monthly_rows(db: Session, pilot_id: int, include_all: bool = False) -> list[dict]:
    """Month-by-month activity across the pilot's whole service span.

    Deliberately not period-scoped: this is the career view, so the surrounding
    annual sections and this one answer different questions.
    """
    flights = db.query(Flight).filter(
        *_flight_conds(include_all, Flight.pilot_id == pilot_id)).all()
    missions = (
        db.query(MissionLog.date, MissionLogPilot.hours)
          .join(MissionLogPilot, MissionLogPilot.mission_log_id == MissionLog.id)
          .filter(MissionLogPilot.pilot_id == pilot_id).all()
    )
    trainings = (
        db.query(TrainingLog.date, TrainingLogPilot.hours)
          .join(TrainingLogPilot, TrainingLogPilot.training_log_id == TrainingLog.id)
          .filter(TrainingLogPilot.pilot_id == pilot_id).all()
    )

    months: dict[str, dict] = {}

    def _slot(d):
        if not d:
            return None
        return months.setdefault(
            f"{d.year}-{d.month:02d}",
            {"flights": 0, "flight_secs": 0, "missions": 0, "mission_hrs": 0.0, "training_hrs": 0.0},
        )

    for f in flights:
        slot = _slot(f.date)
        if slot is None:
            continue
        slot["flights"] += 1
        slot["flight_secs"] += f.duration_seconds or 0
    for m_date, m_hours in missions:
        slot = _slot(m_date)
        if slot is None:
            continue
        slot["missions"] += 1
        slot["mission_hrs"] += m_hours or 0
    for t_date, t_hours in trainings:
        slot = _slot(t_date)
        if slot is None:
            continue
        slot["training_hrs"] += t_hours or 0

    return [
        {
            "month": key,
            "flights": v["flights"],
            "flight_hours": round(v["flight_secs"] / 3600, 1),
            "missions": v["missions"],
            "mission_hours": round(v["mission_hrs"], 1),
            "training_hours": round(v["training_hrs"], 1),
        }
        for key, v in sorted(months.items())
    ]


def _pilot_log_totals(db: Session, pilot_id: int, log_model, link_model, link_fk,
                      period_start: date, period_end: date) -> tuple[float, int]:
    """One pilot's (hours, distinct log count) for missions or trainings.

    Mission and training logs are shaped identically, down to the participant
    link table, so running the pair through one helper keeps four near-identical
    queries and their None guards out of the caller.
    """
    def _scoped(selection):
        return (
            db.query(selection)
              .join(log_model, log_model.id == link_fk)
              .filter(link_model.pilot_id == pilot_id,
                      log_model.date.between(period_start, period_end))
              .scalar()
        )

    hours = _scoped(func.coalesce(func.sum(link_model.hours), 0))
    count = _scoped(func.count(func.distinct(link_fk)))
    return float(hours or 0), int(count or 0)


# Report column headings that appear in more than one report.
COL_EXPIRATION_DATE = "Expiration Date"
COL_FLIGHT_HOURS = "Flight Hours"
COL_MISSION_HOURS = "Mission Hours"
COL_TRAINING_HOURS = "Training Hours"

EXPIRED = "Expired"
EXPIRING_SOON = "Expiring Soon"


def _cert_status(pc, today: date, cutoff_90: date) -> str:
    """Expired, expiring inside 90 days, or the record's own status."""
    if pc.expiration_date and pc.expiration_date < today:
        return EXPIRED
    if pc.expiration_date and pc.expiration_date <= cutoff_90:
        return EXPIRING_SOON
    return pc.status.replace("_", " ").title() if pc.status else "—"


def _pilot_cert_rows(db: Session, pilot_id: int) -> tuple[list[dict], int, int]:
    """One pilot's certifications, with expired and expiring-within-90-days counts."""
    from datetime import timedelta

    today = date.today()
    cutoff_90 = today + timedelta(days=90)
    rows = []

    for pc in db.query(PilotCertification).filter(PilotCertification.pilot_id == pilot_id).all():
        rows.append({
            "certification": pc.certification_type.name if pc.certification_type else "—",
            "status": _cert_status(pc, today, cutoff_90),
            "issue_date": str(pc.issue_date) if pc.issue_date else "—",
            "expiration_date": str(pc.expiration_date) if pc.expiration_date else "—",
        })

    return (rows,
            sum(r["status"] == EXPIRED for r in rows),
            sum(r["status"] == EXPIRING_SOON for r in rows))


def _pilot_section(db: Session, pilot: Pilot, period_start: date, period_end: date,
                   include_all: bool = False) -> dict:
    """Build one Per-Pilot Annual Review section for a single pilot."""
    # Hours
    p_flights = db.query(Flight).filter(
        *_flight_conds(include_all,
                       Flight.pilot_id == pilot.id,
                       Flight.date.between(period_start, period_end))
    ).all()
    flight_secs = sum(f.duration_seconds or 0 for f in p_flights)
    flight_hours = round(flight_secs / 3600, 1)

    mission_hours, mission_count = _pilot_log_totals(
        db, pilot.id, MissionLog, MissionLogPilot, MissionLogPilot.mission_log_id,
        period_start, period_end)
    training_hours, training_count = _pilot_log_totals(
        db, pilot.id, TrainingLog, TrainingLogPilot, TrainingLogPilot.training_log_id,
        period_start, period_end)
    total_hours = round(flight_hours + mission_hours + training_hours, 1)

    # Time in service, derived from flights (see _pilot_service_span).
    first_flight, last_flight, career_flights, career_hours = _pilot_service_span(
        db, pilot.id, include_all)

    cert_rows, expired_count, expiring_count = _pilot_cert_rows(db, pilot.id)

    return {
        "title": pilot.full_name + (" (inactive)" if pilot.status != "active" else ""),
        "type": "table",
        "summary": {
            "total_hours": total_hours,
            "flight_hours": flight_hours,
            "mission_hours": round(mission_hours, 1),
            "training_hours": round(training_hours, 1),
            "flights": len(p_flights),
            "missions_participated": mission_count,
            "trainings_attended": training_count,
            "certifications_expired": expired_count,
            "certifications_expiring_90d": expiring_count,
            # Career figures, outside the review period on purpose.
            "in_service_since": str(first_flight) if first_flight else "no flights on record",
            "last_flight": str(last_flight) if last_flight else "—",
            "career_flights": career_flights,
            "career_flight_hours": career_hours,
        },
        "columns": ["Certification", "Status", "Issue Date", "Expiration Date"],
        "rows": cert_rows,
    }


def _per_pilot_annual_review(config: ReportConfig, db: Session):
    """Generate a per-pilot review section for each selected pilot (or all
    active pilots if none selected). Date range defaults to current year."""
    period_start, period_end, period_label = _annual_period(config)

    if config.pilot_ids:
        pilots = db.query(Pilot).filter(Pilot.id.in_(config.pilot_ids)).all()
    else:
        pilots = db.query(Pilot).filter(Pilot.status == "active").all()
    if not config.include_non_unit:
        pilots = [p for p in pilots if p.counts_toward_totals]
    pilots.sort(key=lambda p: (p.last_name or "", p.first_name or ""))

    sections = []
    for p in pilots:
        sections.append(_pilot_section(db, p, period_start, period_end,
                                       config.include_non_unit))

        vehicle_rows = _pilot_vehicle_rows(db, p.id, period_start, period_end,
                                           config.include_non_unit)
        sections.append({
            "title": f"{p.full_name} - Aircraft Flown ({period_label})",
            "type": "table",
            "summary": {
                "aircraft_flown": len(vehicle_rows),
                "flights": sum(r["flights"] for r in vehicle_rows),
                "flight_hours": round(sum(r["hours"] for r in vehicle_rows), 1),
            },
            "columns": ["Vehicle", "Flights", "Hours"],
            "rows": vehicle_rows,
        })

        monthly_rows = _pilot_monthly_rows(db, p.id, config.include_non_unit)
        sections.append({
            "title": f"{p.full_name} - Monthly Activity (full service history)",
            "type": "table",
            "summary": {
                "months_active": len(monthly_rows),
                "first_flight": monthly_rows[0]["month"] if monthly_rows else "—",
                "latest_activity": monthly_rows[-1]["month"] if monthly_rows else "—",
            },
            "columns": ["Month", "Flights", "Flight Hours", "Missions", "Mission Hours", "Training Hours"],
            "rows": monthly_rows,
        })

    return {
        "report_type": "per_pilot_annual_review",
        "title": f"Per-Pilot Annual Review - {period_label}",
        "summary": {
            "period": period_label,
            "pilots_reviewed": len(pilots),
        },
        "sections": sections,
    }


def _annual_period(config: ReportConfig) -> tuple[date, date, str]:
    """Resolve the reporting period (defaults to current calendar year)."""
    if config.date_from and config.date_to:
        return config.date_from, config.date_to, f"{config.date_from} to {config.date_to}"
    today = date.today()
    return date(today.year, 1, 1), date(today.year, 12, 31), str(today.year)


def _annual_monthly_tempo(flights, missions, trainings) -> list[dict]:
    """Aggregate flights, missions, trainings into a month-by-month table."""
    months = {}
    def _slot(d):
        if not d:
            return None
        key = f"{d.year}-{d.month:02d}"
        return months.setdefault(key, {"flights": 0, "flight_secs": 0, "missions": 0, "mission_hrs": 0.0, "training_hrs": 0.0})
    for f in flights:
        s = _slot(f.date)
        if s is None: continue
        s["flights"] += 1
        s["flight_secs"] += f.duration_seconds or 0
    for m in missions:
        s = _slot(m.date)
        if s is None: continue
        s["missions"] += 1
        s["mission_hrs"] += m.man_hours or 0
    for t in trainings:
        s = _slot(t.date)
        if s is None: continue
        s["training_hrs"] += t.man_hours or 0
    return [
        {
            "month": k,
            "flights": v["flights"],
            "flight_hours": round(v["flight_secs"] / 3600, 1),
            "missions": v["missions"],
            "mission_hours": round(v["mission_hrs"], 1),
            "training_hours": round(v["training_hrs"], 1),
        }
        for k, v in sorted(months.items())
    ]


def _annual_pilot_hours_map(db: Session, flights, missions, trainings) -> dict:
    """Per-pilot accumulator of flight/mission/training hours."""
    pmap = {}
    def _bucket(pid):
        return pmap.setdefault(pid, {"flight": 0.0, "mission": 0.0, "training": 0.0})
    for f in flights:
        if f.pilot_id:
            _bucket(f.pilot_id)["flight"] += (f.duration_seconds or 0) / 3600
    mission_ids = [m.id for m in missions]
    if mission_ids:
        for mp in db.query(MissionLogPilot).filter(MissionLogPilot.mission_log_id.in_(mission_ids)).all():
            _bucket(mp.pilot_id)["mission"] += mp.hours or 0
    training_ids = [t.id for t in trainings]
    if training_ids:
        for tp in db.query(TrainingLogPilot).filter(TrainingLogPilot.training_log_id.in_(training_ids)).all():
            _bucket(tp.pilot_id)["training"] += tp.hours or 0
    return pmap


def _annual_yoy_rows(db: Session, period_year: int, include_all: bool = False) -> list[dict]:
    """Year-over-year totals for the last 5 calendar years up to period_year."""
    from sqlalchemy import extract
    rows = []
    for y in range(period_year - 4, period_year + 1):
        y_start, y_end = date(y, 1, 1), date(y, 12, 31)
        f_count = db.query(func.count(Flight.id)).filter(
            *_flight_conds(include_all, Flight.date.between(y_start, y_end))).scalar() or 0
        f_secs = db.query(func.coalesce(func.sum(Flight.duration_seconds), 0)).filter(
            *_flight_conds(include_all, Flight.date.between(y_start, y_end))).scalar() or 0
        m_hrs = db.query(func.coalesce(func.sum(MissionLog.man_hours), 0)).filter(MissionLog.date.between(y_start, y_end)).scalar() or 0
        t_hrs = db.query(func.coalesce(func.sum(TrainingLog.man_hours), 0)).filter(TrainingLog.date.between(y_start, y_end)).scalar() or 0
        p_count = db.query(func.count(func.distinct(Flight.pilot_id))).filter(
            *_flight_conds(include_all, Flight.date.between(y_start, y_end))).scalar() or 0
        v_count = db.query(func.count(func.distinct(Flight.vehicle_id))).filter(Flight.date.between(y_start, y_end)).scalar() or 0
        rows.append({
            "year": y,
            "flights": f_count,
            "flight_hours": round(f_secs / 3600, 1),
            "mission_hours": round(m_hrs, 1),
            "training_hours": round(t_hrs, 1),
            "unique_pilots": p_count,
            "unique_vehicles": v_count,
        })
    return rows


def _annual_compliance_section(db: Session, pilots_by_id: dict) -> dict:
    """Expired and soon-to-expire certifications across the active roster."""
    from datetime import timedelta
    cutoff_90 = date.today() + timedelta(days=90)
    expired = db.query(PilotCertification).filter(
        PilotCertification.expiration_date.isnot(None),
        PilotCertification.expiration_date < date.today(),
    ).all()
    expiring = db.query(PilotCertification).filter(
        PilotCertification.expiration_date.isnot(None),
        PilotCertification.expiration_date >= date.today(),
        PilotCertification.expiration_date <= cutoff_90,
    ).all()
    rows = []
    for pc in expired + expiring:
        p = pilots_by_id.get(pc.pilot_id)
        ct = pc.certification_type
        rows.append({
            "pilot": p.full_name if p else "Unknown",
            "certification": ct.name if ct else "—",
            "expiration_date": str(pc.expiration_date),
            "status": "Expired" if pc in expired else "Expiring Soon",
        })
    return {
        "title": "Compliance & Certifications",
        "type": "table",
        "summary": {
            "expired_certifications": len(expired),
            "expiring_within_90_days": len(expiring),
        },
        "columns": ["Pilot", "Certification", "Expiration Date", "Status"],
        "rows": rows,
    }


def _annual_unit_report(config: ReportConfig, db: Session):
    """Multi-section state-of-the-unit report.

    Sections: executive summary (narrative), operational tempo (monthly),
    personnel activity (top pilots), fleet utilization, mission activity,
    training activity, operating authorities, compliance + certifications,
    maintenance, incidents, year-over-year comparison.
    """
    from app.models.incident import Incident

    period_start, period_end, period_label = _annual_period(config)

    # Pull period-scoped slices once
    flights = db.query(Flight).filter(
        *_flight_conds(config.include_non_unit,
                       Flight.date.between(period_start, period_end))).all()
    missions = db.query(MissionLog).filter(MissionLog.date.between(period_start, period_end)).all()
    trainings = db.query(TrainingLog).filter(TrainingLog.date.between(period_start, period_end)).all()
    incidents = db.query(Incident).filter(
        Incident.date.between(period_start, period_end),
        Incident.report_type == "incident",
    ).all()
    maint_records = db.query(MaintenanceRecord).filter(
        MaintenanceRecord.performed_date.isnot(None),
        MaintenanceRecord.performed_date.between(period_start, period_end),
    ).all()

    pilots_by_id = {p.id: p for p in db.query(Pilot).all()}
    vehicles_by_id = {v.id: v for v in db.query(Vehicle).all()}

    # Headline totals
    total_flights = len(flights)
    total_flight_hours = round(sum(f.duration_seconds or 0 for f in flights) / 3600, 1)
    total_missions = len(missions)
    total_mission_hours = round(sum(m.man_hours or 0 for m in missions), 1)
    total_trainings = len(trainings)
    total_training_hours = round(sum(t.man_hours or 0 for t in trainings), 1)
    active_pilots = db.query(Pilot).filter(Pilot.status == "active").count()
    inactive_pilots = db.query(Pilot).filter(Pilot.status != "active").count()
    active_vehicles = db.query(Vehicle).filter(Vehicle.status == "active").count()
    unique_pilots_flown = len({f.pilot_id for f in flights if f.pilot_id})
    total_incidents = len(incidents)
    open_incidents = sum(1 for i in incidents if i.status not in ("resolved", "closed"))

    sections = []

    # --- Section 1: Executive Summary (narrative) ---
    narrative = (
        f"During {period_label}, the unit completed {total_flights:,} flight(s) totaling "
        f"{total_flight_hours:,.1f} flight hours. {total_missions} mission(s) "
        f"({total_mission_hours:,.1f} man-hours) and {total_trainings} training session(s) "
        f"({total_training_hours:,.1f} man-hours) were logged. {unique_pilots_flown} pilot(s) "
        f"flew during this period, with {active_pilots} active pilots on the roster and "
        f"{active_vehicles} active aircraft in the fleet."
    )
    if total_incidents:
        narrative += (
            f" {total_incidents} incident(s) reported"
            + (f" ({open_incidents} currently open or under investigation)." if open_incidents else ", all resolved.")
        )
    sections.append({"title": "Executive Summary", "type": "narrative", "narrative": narrative})

    # --- Section 2: Operational Tempo (monthly) ---
    sections.append({
        "title": "Operational Tempo",
        "type": "table",
        "columns": ["Month", "Flights", "Flight Hours", "Missions", "Mission Hours", "Training Hours"],
        "rows": _annual_monthly_tempo(flights, missions, trainings),
    })

    # --- Section 3: Personnel Activity ---
    pmap = _annual_pilot_hours_map(db, flights, missions, trainings)
    personnel_rows = []
    for pid, h in pmap.items():
        p = pilots_by_id.get(pid)
        if not p:
            continue
        total = h["flight"] + h["mission"] + h["training"]
        personnel_rows.append({
            "pilot": p.full_name,
            "flight_hours": round(h["flight"], 1),
            "mission_hours": round(h["mission"], 1),
            "training_hours": round(h["training"], 1),
            "total_hours": round(total, 1),
        })
    personnel_rows.sort(key=lambda r: r["total_hours"], reverse=True)
    sections.append({
        "title": "Personnel Activity",
        "type": "table",
        "summary": {
            "active_roster": active_pilots,
            "inactive_roster": inactive_pilots,
            "pilots_who_flew": unique_pilots_flown,
        },
        "columns": ["Pilot", COL_FLIGHT_HOURS, COL_MISSION_HOURS, COL_TRAINING_HOURS, "Total Hours"],
        "rows": personnel_rows[:25],
    })

    # --- Section 4: Fleet Utilization ---
    vehicle_stats = {}
    for f in flights:
        if f.vehicle_id:
            s = vehicle_stats.setdefault(f.vehicle_id, {"flights": 0, "secs": 0})
            s["flights"] += 1
            s["secs"] += f.duration_seconds or 0
    fleet_rows = []
    for vid, s in vehicle_stats.items():
        v = vehicles_by_id.get(vid)
        if not v:
            continue
        fleet_rows.append({
            "vehicle": f"{v.manufacturer} {v.model}" + (f" ({v.nickname})" if v.nickname else ""),
            "status": v.status,
            "flights": s["flights"],
            "hours": round(s["secs"] / 3600, 1),
        })
    fleet_rows.sort(key=lambda r: r["hours"], reverse=True)
    sections.append({
        "title": "Fleet Utilization",
        "type": "table",
        "summary": {
            "active_aircraft": active_vehicles,
            "aircraft_flown": len(vehicle_stats),
        },
        "columns": ["Vehicle", "Status", "Flights", "Hours"],
        "rows": fleet_rows,
    })

    # --- Section 5: Mission Activity ---
    mission_reasons = {}
    for m in missions:
        k = m.reason or "Unspecified"
        mission_reasons[k] = mission_reasons.get(k, 0) + 1
    mission_ids = [m.id for m in missions]
    mission_participants = (
        db.query(func.count(func.distinct(MissionLogPilot.pilot_id)))
          .filter(MissionLogPilot.mission_log_id.in_(mission_ids)).scalar() or 0
    ) if mission_ids else 0
    sections.append({
        "title": "Mission Activity",
        "type": "table",
        "summary": {
            "total_missions": total_missions,
            "total_man_hours": total_mission_hours,
            "unique_participants": mission_participants,
        },
        "columns": ["Reason", "Missions"],
        "rows": [{"reason": k, "missions": v} for k, v in sorted(mission_reasons.items(), key=lambda x: x[1], reverse=True)],
    })

    # --- Section 6: Training Activity ---
    training_types = {}
    for t in trainings:
        k = t.training_type or "Unspecified"
        bucket = training_types.setdefault(k, {"sessions": 0, "man_hours": 0.0})
        bucket["sessions"] += 1
        bucket["man_hours"] += t.man_hours or 0
    training_ids = [t.id for t in trainings]
    training_attendees = (
        db.query(func.count(func.distinct(TrainingLogPilot.pilot_id)))
          .filter(TrainingLogPilot.training_log_id.in_(training_ids)).scalar() or 0
    ) if training_ids else 0
    sections.append({
        "title": "Training Activity",
        "type": "table",
        "summary": {
            "total_sessions": total_trainings,
            "total_man_hours": total_training_hours,
            "unique_attendees": training_attendees,
        },
        "columns": ["Training Type", "Sessions", "Man-Hours"],
        "rows": [
            {"training_type": k, "sessions": v["sessions"], "man_hours": round(v["man_hours"], 1)}
            for k, v in sorted(training_types.items(), key=lambda x: x[1]["sessions"], reverse=True)
        ],
    })

    # --- Section 7: Operating Authorities ---
    sections.append(_authority_section(db, period_start, period_end))

    # --- Section 8: Compliance & Certifications ---
    sections.append(_annual_compliance_section(db, pilots_by_id))

    # --- Section 9: Maintenance ---
    maint_by_type = {}
    maint_total_cost = 0.0
    for m in maint_records:
        k = m.maintenance_type or "unspecified"
        maint_by_type[k] = maint_by_type.get(k, 0) + 1
        maint_total_cost += m.cost or 0
    sections.append({
        "title": "Maintenance Summary",
        "type": "table",
        "summary": {
            "total_records": len(maint_records),
            "total_cost": f"${maint_total_cost:,.2f}" if maint_total_cost > 0 else "—",
        },
        "columns": ["Maintenance Type", "Records"],
        "rows": [{"maintenance_type": k, "records": v} for k, v in sorted(maint_by_type.items(), key=lambda x: x[1], reverse=True)],
    })

    # --- Section 10: Incidents & Safety ---
    inc_by_severity = {}
    inc_by_category = {}
    for i in incidents:
        inc_by_severity[i.severity or "unknown"] = inc_by_severity.get(i.severity or "unknown", 0) + 1
        inc_by_category[i.category or "unknown"] = inc_by_category.get(i.category or "unknown", 0) + 1
    sections.append({
        "title": "Incidents & Safety",
        "type": "table",
        "summary": {
            "total_incidents": total_incidents,
            "open_or_investigating": open_incidents,
            "minor": inc_by_severity.get("minor", 0),
            "moderate_or_worse": sum(v for k, v in inc_by_severity.items() if k in ("moderate", "major", "critical")),
        },
        "columns": ["Category", "Count"],
        "rows": [{"category": k, "count": v} for k, v in sorted(inc_by_category.items(), key=lambda x: x[1], reverse=True)],
    })

    # --- Section 11: Year-over-Year Comparison ---
    yoy_rows = _annual_yoy_rows(db, period_start.year)
    sections.append({
        "title": "Year-over-Year Comparison",
        "type": "table",
        "columns": ["Year", "Flights", "Flight Hours", "Mission Hours", "Training Hours", "Unique Pilots", "Unique Vehicles"],
        "rows": yoy_rows,
    })

    return {
        "report_type": "annual_unit_report",
        "title": f"Annual Unit Report - {period_label}",
        "summary": {
            "period": period_label,
            "total_flights": total_flights,
            "total_flight_hours": total_flight_hours,
            "total_missions": total_missions,
            "total_training_hours": total_training_hours,
            "active_pilots": active_pilots,
            "active_aircraft": active_vehicles,
            "incidents_reported": total_incidents,
        },
        "sections": sections,
        # Year-over-year also exposed at top level for legacy PDF chart + table
        "columns": ["Year", "Flights", "Flight Hours", "Mission Hours", "Training Hours", "Unique Pilots", "Unique Vehicles"],
        "rows": yoy_rows,
    }
