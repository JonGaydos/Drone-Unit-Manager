from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: int
    pilot_id: Optional[int]
    vehicle_id: Optional[int]
    certification_id: Optional[int]
    entity_type: str
    entity_id: Optional[int]
    document_type: str
    title: str
    filename: str
    mime_type: str
    file_size_bytes: int
    uploaded_at: datetime
    notes: Optional[str]
    view_url: Optional[str] = None

    model_config = {"from_attributes": True}
