import io
import os
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.flight import Flight
from app.models.pilot import Pilot
from app.models.vehicle import Vehicle
from app.models.user import User
from app.models.certification import CertificationType, PilotCertification
from app.models.battery import Battery
from app.models.maintenance import MaintenanceRecord
from app.models.setting import Setting
from app.routers.auth import get_current_user, require_pilot

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


@router.post("/generate")
def generate_report(config: ReportConfig, db: Session = Depends(get_db), user: User = Depends(require_pilot)):
    if config.report_type == "flight_summary":
        return _flight_summary(config, db)
    elif config.report_type == "pilot_hours":
        return _pilot_hours(config, db)
    elif config.report_type == "equipment_utilization":
        return _equipment_utilization(config, db)
    elif config.report_type == "pilot_certifications":
        return _pilot_certifications(config, db)
    elif config.report_type == "battery_status":
        return _battery_status(config, db)
    elif config.report_type == "maintenance_history":
        return _maintenance_history(config, db)
    return {"error": "Unknown report type"}


@router.post("/generate/pdf")
def generate_report_pdf(config: ReportConfig, db: Session = Depends(get_db), user: User = Depends(require_pilot)):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.colors import HexColor
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, PageBreak
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    if config.report_type == "flight_summary":
        data = _flight_summary(config, db)
    elif config.report_type == "pilot_hours":
        data = _pilot_hours(config, db)
    elif config.report_type == "equipment_utilization":
        data = _equipment_utilization(config, db)
    elif config.report_type == "pilot_certifications":
        data = _pilot_certifications(config, db)
    elif config.report_type == "battery_status":
        data = _battery_status(config, db)
    elif config.report_type == "maintenance_history":
        data = _maintenance_history(config, db)
    else:
        data = {"title": "Unknown Report", "summary": {}, "rows": [], "columns": []}

    org_name_setting = db.query(Setting).filter(Setting.key == "org_name").first()
    logo_setting = db.query(Setting).filter(Setting.key == "org_logo").first()
    org_name = org_name_setting.value if org_name_setting else "Drone Unit Manager"

    logo_path = None
    if logo_setting and logo_setting.value:
        for ext in ["png", "jpg", "jpeg", "gif", "webp"]:
            candidate = os.path.join("data", "uploads", "org", f"logo.{ext}")
            if os.path.exists(candidate):
                logo_path = candidate
                break

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

    title_style = ParagraphStyle("ReportTitle", parent=styles["Title"], fontSize=20, textColor=primary, spaceAfter=4)
    subtitle_style = ParagraphStyle("ReportSubtitle", parent=styles["Normal"], fontSize=10, textColor=HexColor("#64748b"), spaceAfter=12)
    heading_style = ParagraphStyle("SectionHeading", parent=styles["Heading2"], fontSize=14, textColor=primary, spaceBefore=16, spaceAfter=8)
    cell_style = ParagraphStyle("CellStyle", parent=styles["Normal"], fontSize=8, leading=10)
    header_cell_style = ParagraphStyle("HeaderCell", parent=styles["Normal"], fontSize=8, leading=10, textColor=white)

    header_items = []
    if logo_path:
        try:
            logo_img = RLImage(logo_path, width=0.6 * inch, height=0.6 * inch)
            logo_img.hAlign = "LEFT"
            header_items.append(logo_img)
        except Exception:
            pass

    elements.append(Paragraph(org_name, title_style))
    elements.append(Paragraph(data.get("title", "Report"), ParagraphStyle("RPTitle", parent=styles["Heading1"], fontSize=16, textColor=HexColor("#334155"), spaceAfter=4)))

    date_range = ""
    if data.get("summary", {}).get("date_range"):
        date_range = data["summary"]["date_range"]
    else:
        date_range = f"{config.date_from or 'All'} to {config.date_to or 'Present'}"
    elements.append(Paragraph(f"Date Range: {date_range}  |  Generated: {date.today()}", subtitle_style))
    elements.append(Spacer(1, 8))

    summary = data.get("summary", {})
    if summary:
        summary_data = []
        summary_headers = []
        for key, value in summary.items():
            label = key.replace("_", " ").title()
            summary_headers.append(Paragraph(f"<b>{label}</b>", ParagraphStyle("SH", parent=styles["Normal"], fontSize=8, textColor=HexColor("#64748b"))))
            summary_data.append(Paragraph(f"<b>{value}</b>", ParagraphStyle("SV", parent=styles["Normal"], fontSize=12, textColor=HexColor("#1e293b"))))

        if summary_headers:
            avail_width = letter[0] - 1.2 * inch
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

        if rows:
            row_keys = list(rows[0].keys())
        else:
            row_keys = []

        table_header = [Paragraph(f"<b>{c}</b>", header_cell_style) for c in columns]
        table_data = [table_header]

        for row in rows[:200]:  # Limit to 200 rows
            vals = list(row.values())
            table_row = [Paragraph(str(v) if v is not None else "-", cell_style) for v in vals]
            table_data.append(table_row)

        avail_width = letter[0] - 1.2 * inch
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
        elements.append(t)

    doc.build(elements)
    buffer.seek(0)

    filename = f"{config.report_type}_{date.today()}.pdf"
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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

    try:
        if report_type == "flight_summary":
            purposes = {}
            for r in rows:
                p = r.get("purpose", "Unknown")
                purposes[p] = purposes.get(p, 0) + 1
            if purposes:
                labels = list(purposes.keys())[:10]
                values = [purposes[l] for l in labels]
                bars = ax.bar(labels, values, color=chart_colors[:len(labels)], edgecolor="white", linewidth=0.5)
                ax.set_ylabel("Flights", fontsize=9)
                ax.set_title("Flights by Purpose", fontsize=11, fontweight="bold", color="#334155")
                plt.xticks(rotation=30, ha="right", fontsize=8)

        elif report_type == "pilot_hours":
            labels = [r.get("pilot", "?") for r in rows][:10]
            values = [r.get("hours", 0) for r in rows][:10]
            bars = ax.barh(labels, values, color=chart_colors[:len(labels)], edgecolor="white", linewidth=0.5)
            ax.set_xlabel("Hours", fontsize=9)
            ax.set_title("Hours by Pilot", fontsize=11, fontweight="bold", color="#334155")
            ax.invert_yaxis()
            plt.yticks(fontsize=8)

        elif report_type == "equipment_utilization":
            labels = [r.get("vehicle", "?")[:20] for r in rows][:10]
            values = [r.get("hours", 0) for r in rows][:10]
            bars = ax.barh(labels, values, color=chart_colors[:len(labels)], edgecolor="white", linewidth=0.5)
            ax.set_xlabel("Hours", fontsize=9)
            ax.set_title("Hours by Vehicle", fontsize=11, fontweight="bold", color="#334155")
            ax.invert_yaxis()
            plt.yticks(fontsize=8)

        elif report_type == "battery_status":
            status_counts = {}
            for r in rows:
                s = r.get("status", "unknown")
                status_counts[s] = status_counts.get(s, 0) + 1
            if status_counts:
                labels = list(status_counts.keys())
                values = list(status_counts.values())
                ax.pie(values, labels=labels, colors=chart_colors[:len(labels)],
                       autopct="%1.0f%%", startangle=90, textprops={"fontsize": 9})
                ax.set_title("Battery Status Distribution", fontsize=11, fontweight="bold", color="#334155")

        elif report_type == "maintenance_history":
            type_counts = {}
            for r in rows:
                t = r.get("type", "other")
                type_counts[t] = type_counts.get(t, 0) + 1
            if type_counts:
                labels = list(type_counts.keys())[:10]
                values = [type_counts[l] for l in labels]
                bars = ax.bar(labels, values, color=chart_colors[:len(labels)], edgecolor="white", linewidth=0.5)
                ax.set_ylabel("Records", fontsize=9)
                ax.set_title("Records by Type", fontsize=11, fontweight="bold", color="#334155")
                plt.xticks(rotation=30, ha="right", fontsize=8)

        elif report_type == "pilot_certifications":
            summary = data.get("summary", {})
            cats = ["Active", "Expired", "Pending"]
            vals = [summary.get("total_active", 0), summary.get("total_expired", 0), summary.get("total_pending", 0)]
            bars = ax.bar(cats, vals, color=["#10b981", "#ef4444", "#f59e0b"], edgecolor="white", linewidth=0.5)
            ax.set_ylabel("Count", fontsize=9)
            ax.set_title("Certification Status", fontsize=11, fontweight="bold", color="#334155")

        else:
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
    q = db.query(
        Pilot.first_name, Pilot.last_name,
        func.count(Flight.id).label("flights"),
        func.coalesce(func.sum(Flight.duration_seconds), 0).label("seconds"),
    ).join(Pilot, Flight.pilot_id == Pilot.id)
    if config.date_from:
        q = q.filter(Flight.date >= config.date_from)
    if config.date_to:
        q = q.filter(Flight.date <= config.date_to)
    if config.pilot_ids:
        q = q.filter(Flight.pilot_id.in_(config.pilot_ids))

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
