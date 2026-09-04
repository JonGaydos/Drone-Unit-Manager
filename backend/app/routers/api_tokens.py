"""Admin management of long-lived API tokens for external integrations."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.deps import AdminUser, DBSession
from app.models.api_token import ApiToken
from app.responses import responses
from app.services.api_tokens import SCOPE_PREFIXES, generate_token, hash_token, token_scopes

router = APIRouter(prefix="/api/api-tokens", tags=["api-tokens"])

TOKEN_NOT_FOUND = "API token not found"


class ApiTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    read_only: bool = True
    scopes: Optional[list[str]] = None  # null = all areas


class ApiTokenOut(BaseModel):
    id: int
    name: str
    token_prefix: str
    read_only: bool
    scopes: Optional[list[str]] = None
    created_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None


def _to_out(t: ApiToken) -> ApiTokenOut:
    return ApiTokenOut(
        id=t.id, name=t.name, token_prefix=t.token_prefix, read_only=t.read_only,
        scopes=token_scopes(t), created_at=t.created_at,
        last_used_at=t.last_used_at, revoked_at=t.revoked_at,
    )


@router.get("", response_model=list[ApiTokenOut], responses=responses(401))
def list_api_tokens(db: DBSession, admin: AdminUser):
    tokens = db.query(ApiToken).order_by(ApiToken.created_at.desc()).all()
    return [_to_out(t) for t in tokens]


@router.get("/scopes", responses=responses(401))
def list_available_scopes(admin: AdminUser):
    """Selectable areas and the route prefixes each one covers."""
    return {area: prefixes for area, prefixes in SCOPE_PREFIXES.items()}


@router.post("", responses=responses(400, 401))
def create_api_token(data: ApiTokenCreate, db: DBSession, admin: AdminUser):
    """Create a token. The raw token appears in this response only."""
    from app.services.audit import log_action
    import json

    if data.scopes is not None:
        unknown = [s for s in data.scopes if s not in SCOPE_PREFIXES]
        if unknown:
            raise HTTPException(400, f"Unknown scopes: {', '.join(unknown)}. Allowed: {', '.join(sorted(SCOPE_PREFIXES))}")
        if not data.scopes:
            raise HTTPException(400, "Select at least one scope, or omit scopes for all areas")

    raw = generate_token()
    t = ApiToken(
        name=data.name,
        token_hash=hash_token(raw),
        token_prefix=raw[:12],
        user_id=admin.id,
        read_only=data.read_only,
        scopes=json.dumps(data.scopes) if data.scopes is not None else None,
    )
    db.add(t)
    db.flush()
    log_action(db, admin.id, admin.display_name, "create", "api_token", t.id, t.name,
               details=f"read_only={t.read_only}, scopes={data.scopes or 'all'}")
    db.commit()
    db.refresh(t)
    return {"token": raw, **_to_out(t).model_dump()}


@router.delete("/{token_id}", responses=responses(401, 404))
def revoke_api_token(token_id: int, db: DBSession, admin: AdminUser):
    """Revoke a token immediately. The row is kept for the audit trail."""
    from app.services.audit import log_action

    t = db.query(ApiToken).filter(ApiToken.id == token_id).first()
    if not t:
        raise HTTPException(404, TOKEN_NOT_FOUND)
    if t.revoked_at is None:
        t.revoked_at = datetime.utcnow()
        log_action(db, admin.id, admin.display_name, "delete", "api_token", t.id, t.name, details="revoked")
        db.commit()
    return {"ok": True}
