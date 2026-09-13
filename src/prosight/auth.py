"""Supabase Auth verification and request-scoped application identity."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from contextvars import ContextVar
from dataclasses import dataclass

from fastapi import HTTPException
import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError

from .config import get_settings


@dataclass(frozen=True)
class AuthContext:
    """Verified caller identity used by API, repository, and agents."""

    user_id: str
    email: str
    display_name: str
    role: str
    project_codes: tuple[str, ...]
    access_token: str


current_auth: ContextVar[AuthContext | None] = ContextVar("prosight_auth", default=None)


class SupabaseAuthVerifier:
    """Verify a Supabase access token with JWKS and load its RLS-visible profile."""

    def __init__(self) -> None:
        settings = get_settings()
        self.url = settings.supabase_url.rstrip("/")
        self.key = settings.supabase_publishable_key
        if not self.url or not self.key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY are required")
        self.issuer = f"{self.url}/auth/v1"
        self.jwks = PyJWKClient(f"{self.issuer}/.well-known/jwks.json", cache_keys=True)

    def verify(self, authorization: str | None) -> AuthContext:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Authentication required")
        token = authorization.split(" ", 1)[1].strip()
        if not token:
            raise HTTPException(status_code=401, detail="Authentication required")
        claims = self._verify_claims(token)
        user_id = str(claims.get("sub") or "")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid or expired session")
        profiles = self._request(
            f"/rest/v1/profiles?id=eq.{user_id}&select=id,email,display_name,role", token
        )
        if not profiles:
            raise HTTPException(status_code=403, detail="User profile is not provisioned")
        memberships = self._request(
            "/rest/v1/project_memberships?select=project_code&order=project_code", token
        )
        profile = profiles[0]
        return AuthContext(
            user_id=user_id,
            email=str(profile.get("email") or claims.get("email") or ""),
            display_name=str(profile.get("display_name") or ""),
            role=str(profile.get("role") or "employee"),
            project_codes=tuple(str(item["project_code"]) for item in memberships),
            access_token=token,
        )

    def _verify_claims(self, token: str) -> dict:
        """Validate asymmetric project JWTs locally; support legacy HS256 via Auth."""
        try:
            algorithm = str(jwt.get_unverified_header(token).get("alg") or "")
            if algorithm == "HS256":
                user = self._request("/auth/v1/user", token)
                return {"sub": user.get("id"), "email": user.get("email")}
            if algorithm not in {"RS256", "ES256"}:
                raise HTTPException(status_code=401, detail="Unsupported session token")
            signing_key = self.jwks.get_signing_key_from_jwt(token)
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=[algorithm],
                audience="authenticated",
                issuer=self.issuer,
                options={"require": ["exp", "sub", "aud", "iss"]},
            )
        except HTTPException:
            raise
        except (PyJWTError, ValueError) as error:
            raise HTTPException(status_code=401, detail="Invalid or expired session") from error

    def _request(self, path: str, token: str):
        request = urllib.request.Request(
            f"{self.url}{path}",
            headers={"apikey": self.key, "Authorization": f"Bearer {token}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read() or b"null")
        except urllib.error.HTTPError as error:
            if error.code in {401, 403}:
                raise HTTPException(status_code=401, detail="Invalid or expired session") from error
            raise HTTPException(status_code=503, detail="Authentication service unavailable") from error
        except (OSError, ValueError) as error:
            raise HTTPException(status_code=503, detail="Authentication service unavailable") from error


def require_current_auth() -> AuthContext:
    """Return the identity installed by API authentication middleware."""
    context = current_auth.get()
    if not context:
        raise HTTPException(status_code=401, detail="Authentication required")
    return context
