"""Validate Supabase access tokens online; never trust browser-supplied roles."""

import httpx
from fastapi import HTTPException

from .config import Settings

APP_ROLES = frozenset({"admin", "project_manager", "planning_engineer"})


async def get_supabase_user(authorization: str, settings: Settings) -> dict | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(401, "Invalid authorization header")
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise HTTPException(503, "Supabase authentication is not configured")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{settings.supabase_url}/auth/v1/user",
                headers={"apikey": settings.supabase_publishable_key,
                         "Authorization": f"Bearer {token.strip()}"},
            )
    except httpx.RequestError as error:
        raise HTTPException(503, "Authentication service unavailable") from error
    if response.status_code in {401, 403}:
        raise HTTPException(401, "Session expired or invalid")
    if response.status_code != 200:
        raise HTTPException(503, "Authentication service unavailable")
    try:
        user = response.json()
        role = user.get("app_metadata", {}).get("prosight_role")
        if not user.get("id") or user.get("is_anonymous"):
            raise HTTPException(401, "A verified account is required")
        if not isinstance(role, str) or role not in APP_ROLES:
            raise HTTPException(403, "Your account is awaiting ProSight access. Contact your administrator.")
        return {"id": user["id"], "username": user.get("email", ""),
                "display_name": user.get("email", ""), "role": role}
    except (ValueError, AttributeError, TypeError) as error:
        raise HTTPException(503, "Invalid authentication service response") from error
