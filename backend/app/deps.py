"""Shared FastAPI dependency type aliases using Annotated.

Centralizes common dependency injection patterns so routers can use
clean type hints instead of repeating Depends() calls.
"""

from dataclasses import dataclass
from typing import Annotated, TypeVar

from fastapi import Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session
from starlette.datastructures import FormData, UploadFile

from app.database import get_db, get_telemetry_db
from app.models.user import User
from app.routers.auth import get_current_user, require_admin, require_permission

FieldsT = TypeVar("FieldsT", bound=BaseModel)
FILE_FIELD = "file"

DBSession = Annotated[Session, Depends(get_db)]
TelemetryDBSession = Annotated[Session, Depends(get_telemetry_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]


@dataclass
class UploadForm:
    """A multipart form, parsed only after `user` passed the route's check."""

    user: User
    form: FormData

    @property
    def file(self) -> UploadFile:
        """The uploaded file. A form without one is refused the way a declared File() field is."""
        file = self.form.get(FILE_FIELD)
        if not isinstance(file, UploadFile):
            raise RequestValidationError([
                {"type": "missing", "loc": ("body", FILE_FIELD), "msg": "Field required"}])
        return file

    def fields(self, model: type[FieldsT]) -> FieldsT:
        """The text fields, validated the way declared Form() fields are: blank
        counts as not sent."""
        sent = {name: value for name, value in self.form.items() if name != FILE_FIELD and value != ""}
        try:
            return model.model_validate(sent)
        except ValidationError as e:
            raise RequestValidationError([
                {**error, "loc": ("body", *error["loc"])}
                for error in e.errors(include_url=False, include_context=False, include_input=False)
            ]) from e


async def _parse_form(request: Request) -> FormData:
    try:
        return await request.form()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, "There was an error parsing the body") from e


def require_form_user(key: str | None = None):
    """Build a dependency for a route taking a file. It checks sign-in and the
    permission key (no key means admin only) and only then reads the body.

    A declared File() or Form() parameter makes FastAPI read the whole body before
    it runs any dependency, so such a route spools the upload of anyone who asks.
    The check stays in the dependency tree, where the permission coverage walk
    sees it.
    """
    guard = require_admin if key is None else require_permission(key)

    async def read_form(request: Request, user: Annotated[User, Depends(guard)]):
        form = await _parse_form(request)
        try:
            yield UploadForm(user, form)
        finally:
            await form.close()

    read_form.reads_form = True
    return read_form


AdminForm = Annotated[UploadForm, Depends(require_form_user())]
