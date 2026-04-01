"""Shared string constants used across multiple modules.

Centralises commonly repeated literals to reduce duplication (SonarQube S1192)
and make future changes easier.
"""

# ── HTTP error detail messages ────────────────────────────────────────────────
PILOT_NOT_FOUND = "Pilot not found"
VEHICLE_NOT_FOUND = "Vehicle not found"
FLIGHT_NOT_FOUND = "Flight not found"
DOCUMENT_NOT_FOUND = "Document not found"
INCIDENT_NOT_FOUND = "Incident not found"
RECORD_NOT_FOUND = "Record not found"
BATTERY_NOT_FOUND = "Battery not found"
CONTROLLER_NOT_FOUND = "Controller not found"
TEMPLATE_NOT_FOUND = "Template not found"
TRAINING_LOG_NOT_FOUND = "Training log not found"
MISSION_LOG_NOT_FOUND = "Mission log not found"
FLIGHT_PLAN_NOT_FOUND = "Flight plan not found"
ALERT_NOT_FOUND = "Alert not found"
USER_NOT_FOUND = "User not found"
GEOFENCE_NOT_FOUND = "Geofence not found"
PHOTO_NOT_FOUND = "Photo not found"
CERTIFICATION_TYPE_NOT_FOUND = "Certification type not found"
PILOT_CERTIFICATION_NOT_FOUND = "Pilot certification not found"
EQUIPMENT_QUAL_NOT_FOUND = "Equipment qualification not found"
COMPONENT_NOT_FOUND = "Component not found"
SENSOR_NOT_FOUND = "Sensor not found"
ATTACHMENT_NOT_FOUND = "Attachment not found"
DOCK_NOT_FOUND = "Dock not found"
CHECKOUT_NOT_FOUND = "Checkout record not found"

ACCESS_DENIED = "Access denied"

# ── Media types ───────────────────────────────────────────────────────────────
MIME_JPEG = "image/jpeg"
FILE_TYPE_NOT_ALLOWED = "File type '{}' not allowed."
FILE_TOO_LARGE = "File too large. Maximum size is {}MB"

# ── Status / role strings ─────────────────────────────────────────────────────
STATUS_ACTIVE = "active"
STATUS_INACTIVE = "inactive"
STATUS_RETIRED = "retired"

ROLE_ADMIN = "admin"
ROLE_SUPERVISOR = "supervisor"
ROLE_PILOT = "pilot"

REVIEW_NEEDS_REVIEW = "needs_review"
REVIEW_REVIEWED = "reviewed"

# ── API provider strings ──────────────────────────────────────────────────────
PROVIDER_SKYDIO = "skydio"
API_PROVIDER_SKYDIO = "skydio"

# ── UTC / timezone ───────────────────────────────────────────────────────────
UTC_OFFSET = "+00:00"

# ── Application metadata ────────────────────────────────────────────────────
APP_TITLE = "Drone Unit Manager"

# ── Folder / geofence messages ───────────────────────────────────────────────
FOLDER_NOT_FOUND = "Folder not found"
