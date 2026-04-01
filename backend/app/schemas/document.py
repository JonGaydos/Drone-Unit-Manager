from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: int
    pilot_id: Optional[int] = None
    vehicle_id: Optional[int] = None
    certification_id: Optional[int] = None
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
    view_url: Optional[str] = None

    model_config = {"from_attributes": True}
