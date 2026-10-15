from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConfirmationDecision(StrictModel):
    confirm: bool


class SessionResponse(BaseModel):
    url: str
    token: str
    room_name: str
    expires_in_seconds: int = 600


class ActionResult(BaseModel):
    ok: bool
    data: dict | list | str | None = None
    error: dict | None = None
