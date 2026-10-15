from functools import lru_cache
import json

from fastapi import Header, HTTPException
from .config import get_settings

settings = get_settings()


@lru_cache(maxsize=1)
def _firebase_auth_module():
    import firebase_admin
    from firebase_admin import auth, credentials

    if not firebase_admin._apps:
        if settings.firebase_service_account_json:
            service_account = json.loads(settings.firebase_service_account_json)
            firebase_admin.initialize_app(credentials.Certificate(service_account), {
                "projectId": settings.firebase_project_id or service_account.get("project_id")
            })
        else:
            # On managed Google infrastructure, Application Default Credentials may be available.
            options = {"projectId": settings.firebase_project_id} if settings.firebase_project_id else None
            firebase_admin.initialize_app(options=options)
    return auth


async def current_user(authorization: str | None = Header(default=None), x_dev_user: str | None = Header(default=None)) -> str:
    if settings.app_env.lower() == "production" and settings.auth_mode.lower() != "firebase":
        raise HTTPException(status_code=500, detail="Production requires AUTH_MODE=firebase")

    if settings.auth_mode.lower() == "development":
        # Never use this mode on a public deployment.
        return (x_dev_user or "local-dev-user")[:128]

    if settings.auth_mode.lower() != "firebase":
        raise HTTPException(status_code=500, detail="Invalid authentication configuration")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing Firebase ID token")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing Firebase ID token")
    try:
        auth = _firebase_auth_module()
        decoded = auth.verify_id_token(token, check_revoked=True)
        uid = decoded.get("uid")
        if not isinstance(uid, str) or not uid:
            raise ValueError("Missing user id")
        return uid[:128]
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired Firebase ID token") from exc
