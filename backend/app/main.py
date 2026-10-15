from __future__ import annotations
import json
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from livekit import api as lk_api

from .config import get_settings
from .database import (
    claim_confirmation, finish_confirmation, init_db, list_pending_confirmations,
    reject_confirmation,
)
from .home_assistant import execute_confirmed_automation
from .api_schemas import ConfirmationDecision, SessionResponse
from .security import current_user

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="JARVIS Cloud API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-Dev-User"],
)


@app.get("/healthz")
async def healthz():
    return {"ok": True, "service": "jarvis-api"}


@app.post("/api/session", response_model=SessionResponse)
async def create_session(user_id: str = Depends(current_user)):
    required = {
        "LIVEKIT_URL": settings.livekit_url,
        "LIVEKIT_API_KEY": settings.livekit_api_key,
        "LIVEKIT_API_SECRET": settings.livekit_api_secret,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise HTTPException(status_code=503, detail=f"Missing server configuration: {', '.join(missing)}")

    room_name = f"jarvis-{uuid4().hex}"
    # Only the backend knows the API secret. The mobile app receives a room-scoped token.
    token = (
        lk_api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(user_id)
        .with_name("JARVIS user")
        .with_metadata(json.dumps({"user_id": user_id}))
        .with_ttl(timedelta(minutes=10))
        .with_grants(lk_api.VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,
            can_subscribe=True,
            can_publish_data=True,
        ))
        .to_jwt()
    )

    # Explicit dispatch carries a verified uid to the worker; agent must not infer ownership from speech.
    try:
        async with lk_api.LiveKitAPI(
            url=settings.livekit_url,
            api_key=settings.livekit_api_key,
            api_secret=settings.livekit_api_secret,
        ) as client:
            await client.agent_dispatch.create_dispatch(
                lk_api.CreateAgentDispatchRequest(
                    agent_name=settings.livekit_agent_name,
                    room=room_name,
                    metadata=json.dumps({"user_id": user_id}),
                )
            )
    except Exception as exc:
        # Do not return secrets/provider exception details to a mobile client.
        raise HTTPException(status_code=502, detail="Could not start the JARVIS voice agent") from exc

    return SessionResponse(url=settings.livekit_url, token=token, room_name=room_name)


@app.get("/api/confirmations/pending")
async def pending_confirmations(user_id: str = Depends(current_user)):
    return {"items": await list_pending_confirmations(user_id)}


@app.post("/api/confirmations/{confirmation_id}")
async def resolve_confirmation(
    confirmation_id: str,
    decision: ConfirmationDecision,
    user_id: str = Depends(current_user),
):
    if not decision.confirm:
        rejected = await reject_confirmation(user_id, confirmation_id)
        if not rejected:
            raise HTTPException(status_code=404, detail="Confirmation expired or not found")
        return {"ok": True, "status": "rejected"}

    action = await claim_confirmation(user_id, confirmation_id)
    if not action:
        raise HTTPException(status_code=404, detail="Confirmation expired, already used, or not found")
    if action["action_type"] != "run_automation":
        await finish_confirmation(confirmation_id, "failed")
        raise HTTPException(status_code=400, detail="Unsupported confirmation action")

    automation_id = action["payload"].get("automation_id", "")
    try:
        result = await execute_confirmed_automation(automation_id)
    except Exception:
        result = {"ok": False, "error": {"code": "internal_error", "message": "Automation execution failed"}}
    await finish_confirmation(confirmation_id, "completed" if result["ok"] else "failed")
    if not result["ok"]:
        return {"ok": False, "status": "failed", "error": result["error"]}
    return {"ok": True, "status": "completed", "result": result["data"]}
