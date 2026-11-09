from datetime import datetime
from typing import Annotated, Optional

from pydantic import BaseModel, StringConstraints

# A folder name or document title: trimmed, and never blank.
NameText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class DocumentOut(BaseModel):
    id: int
    pilot_id: Optional[int] = None
    vehicle_id: Optional[int] = None
    certification_id: Optional[int] = None
    certification_pilot_id: Optional[int] = None
    uploaded_by_id: Optional[int] = None
    entity_type: str
    entity_id: Optional[int] = None
    document_type: str
    title: str
    filename: str
    mime_type: str
    file_size_bytes: int
    uploaded_at: datetime
    notes: Optional[str] = None
    folder_id: Optional[int] = None
    legal_hold: bool = False
    sha256: Optional[str] = None
    view_url: Optional[str] = None

    model_config = {"from_attributes": True}
