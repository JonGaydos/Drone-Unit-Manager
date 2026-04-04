import io
import os
from datetime import date
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.constants import APP_TITLE
from app.config import settings
from app.deps import DBSession, PilotUser
from app.models.flight import Flight
from app.models.pilot import Pilot
from app.models.vehicle import Vehicle
from app.models.certification import CertificationType, PilotCertification
from app.models.battery import Battery
from app.models.maintenance import MaintenanceRecord
from app.models.setting import Setting
from app.models.mission_log import MissionLog
from app.models.mission_log_pilot import MissionLogPilot
from app.models.training_log import TrainingLog
from app.models.training_log_pilot import TrainingLogPilot
from app.responses import responses

router = APIRouter(prefix="/api/reports", tags=["reports"])


class ReportConfig(BaseModel):
    report_type: str  # flight_summary, pilot_hours, equipment_utilization, pilot_certifications, battery_status, maintenance_history
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    pilot_ids: list[int] = []
    vehicle_ids: list[int] = []


class ReportRow(BaseModel):
    label: str
    values: dict


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


def _build_pdf_summary_table(summary: dict, styles, primary_light, avail_width) -> list:
    """Build PDF summary table elements from summary dict."""
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import Table, TableStyle, Spacer
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph

    elements = []
    summary_headers = []
    summary_data = []
    for key, value in summary.items():
        label = key.replace("_", " ").title()
        summary_headers.append(Paragraph(f"<b>{label}</b>", ParagraphStyle("SH", parent=styles["Normal"], fontSize=8, textColor=HexColor("#64748b"))))
        summary_data.append(Paragraph(f"<b>{value}</b>", ParagraphStyle("SV", parent=styles["Normal"], fontSize=12, textColor=HexColor("#1e293b"))))

    if summary_headers:
        col_w = avail_width / max(len(summary_headers), 1)
        summary_table = Table([summary_headers, summary_data], colWidths=[col_w] * len(summary_headers))
        summary_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), primary_light),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOX", (0, 0), (-1, -1), 0.5, HexColor("#bfdbfe")),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, HexColor("#bfdbfe")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 16))

    return elements


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


@router.post("/generate/pdf", responses=responses(401))
def generate_report_pdf(config: ReportConfig, db: DBSession, user: PilotUser):
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

    data = _dispatch_report(config, db)
    if "error" in data:
        data = {"title": "Unknown Report", "summary": {}, "rows": [], "columns": []}

    org_name_setting = db.query(Setting).filter(Setting.key == "org_name").first()
    logo_setting = db.query(Setting).filter(Setting.key == "org_logo").first()
    org_name = org_name_setting.value if org_name_setting else APP_TITLE

    logo_path = _find_org_logo() if (logo_setting and logo_setting.value) else None

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

    title_style = ParagraphStyle("ReportTitle", parent=styles["Title"], fontSize=20, textColor=primary, spaceAfter=4)
    subtitle_style = ParagraphStyle("ReportSubtitle", parent=styles["Normal"], fontSize=10, textColor=HexColor("#64748b"), spaceAfter=12)
    heading_style = ParagraphStyle("SectionHeading", parent=styles["Heading2"], fontSize=14, textColor=primary, spaceBefore=16, spaceAfter=8)
    cell_style = ParagraphStyle("CellStyle", parent=styles["Normal"], fontSize=8, leading=10)
    header_cell_style = ParagraphStyle("HeaderCell", parent=styles["Normal"], fontSize=8, leading=10, textColor=white)

    if logo_path:
        try:
            from PIL import Image as PILImage
            with PILImage.open(logo_path) as pil_img:
                img_w, img_h = pil_img.size
            aspect = img_h / img_w if img_w else 1
            logo_w = 0.6 * inch
            logo_img = RLImage(logo_path, width=logo_w, height=logo_w * aspect)
            logo_img.hAlign = "LEFT"
            elements.append(logo_img)
        except Exception:
            pass

    elements.append(Paragraph(org_name, title_style))
    elements.append(Paragraph(data.get("title", "Report"), ParagraphStyle("RPTitle", parent=styles["Heading1"], fontSize=16, textColor=HexColor("#334155"), spaceAfter=4)))

    date_range = data.get("summary", {}).get("date_range") or f"{config.date_from or 'All'} to {config.date_to or 'Present'}"
    elements.append(Paragraph(f"Date Range: {date_range}  |  Generated: {date.today()}", subtitle_style))
    elements.append(Spacer(1, 8))

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
    if rows and columns:
        elements.append(Paragraph("Data", heading_style))
        elements.extend(_build_pdf_data_table(rows, columns, header_bg, alt_row, white, cell_style, header_cell_style, avail_width))

    doc.build(elements)
    buffer.seek(0)

    filename = f"{config.report_type}_{date.today()}.pdf"
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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


def _chart_grouped_bars(ax, rows, label_key, hr_keys, title, plt, limit=10):
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
                            "Hours by Pilot (Flight / Mission / Training)", plt)
        return True

    def _chart_annual():
        _chart_grouped_bars(ax, rows, "year", ["flight_hours", "mission_hours", "training_hours"],
                            "Year-over-Year Activity Hours", plt, limit=15)
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
    q = db.query(Flight)
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

    # Build date filter conditions for the outer join
    join_conditions = [Flight.pilot_id == Pilot.id]
    if config.date_from:
        join_conditions.append(Flight.date >= config.date_from)
    if config.date_to:
        join_conditions.append(Flight.date <= config.date_to)

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
    q = db.query(
        Vehicle.manufacturer, Vehicle.model, Vehicle.nickname, Vehicle.serial_number,
        func.count(Flight.id).label("flights"),
        func.coalesce(func.sum(Flight.duration_seconds), 0).label("seconds"),
    ).join(Vehicle, Flight.vehicle_id == Vehicle.id)
    if config.date_from:
        q = q.filter(Flight.date >= config.date_from)
    if config.date_to:
        q = q.filter(Flight.date <= config.date_to)

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

    pilot_ids_seen = set(pc.pilot_id for pc in records)

    return {
        "report_type": "pilot_certifications",
        "title": "Pilot Certifications Report",
        "summary": {
            "total_pilots": len(pilot_ids_seen),
            "total_active": total_active,
            "total_expired": total_expired,
            "total_pending": total_pending,
        },
        "columns": ["Pilot", "Cert Name", "Status", "Issue Date", "Expiration Date", "Days Until Expiry"],
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
    """Get total flight hours for a pilot within the config date range."""
    fq = db.query(func.coalesce(func.sum(Flight.duration_seconds), 0)).filter(Flight.pilot_id == pilot_id)
    if config.date_from:
        fq = fq.filter(Flight.date >= config.date_from)
    if config.date_to:
        fq = fq.filter(Flight.date <= config.date_to)
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
    pilots = db.query(Pilot).filter(Pilot.status == "active").order_by(Pilot.last_name).all()

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

    return {
        "report_type": "pilot_activity_summary",
        "title": "Pilot Activity Summary",
        "summary": {
            "total_pilots": len(rows),
            "total_flight_hours": round(total_flight_hrs, 1),
            "total_mission_hours": round(total_mission_hrs, 1),
            "total_training_hours": round(total_training_hrs, 1),
            "date_range": f"{config.date_from or 'All'} to {config.date_to or 'Present'}",
        },
        "columns": ["Pilot", "Flight Hours", "Mission Hours", "Training Hours", "Total Hours"],
        "rows": rows,
    }


def _annual_unit_report(config: ReportConfig, db: Session):
    from sqlalchemy import extract

    # Get year range from flights
    min_year_q = db.query(func.min(extract("year", Flight.date))).scalar()
    max_year_q = db.query(func.max(extract("year", Flight.date))).scalar()
    if not min_year_q or not max_year_q:
        return {
            "report_type": "annual_unit_report",
            "title": "Annual Unit Report",
            "summary": {},
            "columns": [],
            "rows": [],
        }

    min_year = int(min_year_q)
    max_year = int(max_year_q)

    rows = []
    for year in range(min_year, max_year + 1):
        # Flights
        flight_q = db.query(
            func.count(Flight.id),
            func.coalesce(func.sum(Flight.duration_seconds), 0),
        ).filter(extract("year", Flight.date) == year)
        flight_count, flight_secs = flight_q.one()

        # Mission hours
        mission_hrs = db.query(func.coalesce(func.sum(MissionLog.man_hours), 0)).filter(
            extract("year", MissionLog.date) == year
        ).scalar() or 0

        # Training hours
        training_hrs = db.query(func.coalesce(func.sum(TrainingLog.man_hours), 0)).filter(
            extract("year", TrainingLog.date) == year
        ).scalar() or 0

        # Unique pilots
        unique_pilots = db.query(func.count(func.distinct(Flight.pilot_id))).filter(
            extract("year", Flight.date) == year
        ).scalar() or 0

        # Unique vehicles
        unique_vehicles = db.query(func.count(func.distinct(Flight.vehicle_id))).filter(
            extract("year", Flight.date) == year
        ).scalar() or 0

        rows.append({
            "year": year,
            "flights": flight_count or 0,
            "flight_hours": round((flight_secs or 0) / 3600, 1),
            "mission_hours": round(mission_hrs, 1),
            "training_hours": round(training_hrs, 1),
            "unique_pilots": unique_pilots,
            "unique_vehicles": unique_vehicles,
        })

    total_flights = sum(r["flights"] for r in rows)
    total_flight_hrs = sum(r["flight_hours"] for r in rows)

    return {
        "report_type": "annual_unit_report",
        "title": "Annual Unit Report",
        "summary": {
            "years_covered": f"{min_year} - {max_year}",
            "total_flights": total_flights,
            "total_flight_hours": round(total_flight_hrs, 1),
        },
        "columns": ["Year", "Flights", "Flight Hours", "Mission Hours", "Training Hours", "Unique Pilots", "Unique Vehicles"],
        "rows": rows,
    }
