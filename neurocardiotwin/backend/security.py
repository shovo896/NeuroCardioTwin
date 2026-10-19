"""Server-side identity, Supabase persistence, and MCP authorization helpers.

No browser code receives the Supabase server key.  Auth0 access tokens are
verified against the tenant JWKS before a protected API or MCP operation runs.
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi import HTTPException, Request


MCP_SCOPES = ("mcp:read", "knowledge:query", "twin:read", "admin:read")
DEFAULT_USER_PERMISSION_CLAIM = "https://neurocardiotwin.app/permissions"
_JWKS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _b64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _json_part(value: str) -> dict[str, Any]:
    try:
        decoded = json.loads(_b64url(value))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed JWT.") from exc
    if not isinstance(decoded, dict):
        raise ValueError("Malformed JWT.")
    return decoded


def _auth0_domain() -> str:
    return os.getenv("AUTH0_DOMAIN", "").strip().removeprefix("https://").rstrip("/")


def auth0_ready() -> bool:
    return bool(_auth0_domain() and os.getenv("AUTH0_AUDIENCE", "").strip())


def mcp_resource() -> str:
    """Auth0 audience is deliberately the canonical MCP protected resource."""
    return os.getenv("AUTH0_AUDIENCE", "").strip().rstrip("/")


def _issuer() -> str:
    return f"https://{_auth0_domain()}/"


def _jwks(domain: str) -> dict[str, Any]:
    cached = _JWKS_CACHE.get(domain)
    now = time.time()
    if cached and cached[0] > now:
        return cached[1]
    request = urllib.request.Request(
        f"https://{domain}/.well-known/jwks.json", headers={"Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            keys = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise ValueError("Unable to retrieve Auth0 signing keys.") from exc
    if not isinstance(keys, dict) or not isinstance(keys.get("keys"), list):
        raise ValueError("Invalid Auth0 signing-key response.")
    _JWKS_CACHE[domain] = (now + 300, keys)
    return keys


def _verify_rs256(token: str) -> dict[str, Any]:
    pieces = token.split(".")
    if len(pieces) != 3:
        raise ValueError("Malformed JWT.")
    header, claims = _json_part(pieces[0]), _json_part(pieces[1])
    if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
        raise ValueError("Unsupported access-token signature.")
    key = next((item for item in _jwks(_auth0_domain())["keys"] if item.get("kid") == header["kid"]), None)
    if not key or key.get("kty") != "RSA" or not key.get("n") or not key.get("e"):
        raise ValueError("Unknown token signing key.")
    try:
        public_key = rsa.RSAPublicNumbers(
            int.from_bytes(_b64url(key["e"]), "big"), int.from_bytes(_b64url(key["n"]), "big")
        ).public_key()
        public_key.verify(_b64url(pieces[2]), f"{pieces[0]}.{pieces[1]}".encode(), padding.PKCS1v15(), hashes.SHA256())
    except Exception as exc:  # cryptography intentionally hides signature details
        raise ValueError("Invalid access-token signature.") from exc
    return claims


@dataclass(frozen=True)
class Identity:
    subject: str
    email: str | None
    name: str | None
    permissions: frozenset[str]


def verify_bearer(request: Request, required_scope: str = "mcp:read") -> Identity:
    if not auth0_ready():
        raise HTTPException(503, "Authentication is not configured.")
    authorization = request.headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Bearer access token required.")
    try:
        claims = _verify_rs256(authorization.split(" ", 1)[1].strip())
        now = time.time()
        audience = claims.get("aud")
        audiences = {audience} if isinstance(audience, str) else set(audience or [])
        if claims.get("iss") != _issuer() or mcp_resource() not in audiences:
            raise ValueError("Token issuer or audience is invalid.")
        if not isinstance(claims.get("exp"), (int, float)) or claims["exp"] <= now:
            raise ValueError("Access token has expired.")
        permissions = frozenset(claims.get("permissions", []))
        scope_claim = claims.get("scope", "")
        if isinstance(scope_claim, str):
            permissions = permissions.union(scope_claim.split())
        # A Post-Login Action issues this namespaced claim for the public
        # standard-user tier. The JWT signature has already been verified.
        default_permissions = claims.get(DEFAULT_USER_PERMISSION_CLAIM, [])
        if isinstance(default_permissions, str):
            default_permissions = default_permissions.split()
        if isinstance(default_permissions, list) and all(isinstance(item, str) for item in default_permissions):
            permissions = permissions.union(default_permissions)
        if required_scope not in permissions:
            raise PermissionError("Required permission is missing.")
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise ValueError("Access token has no subject.")
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(401, str(exc)) from exc
    return Identity(subject, claims.get("email"), claims.get("name"), permissions)


class SupabaseStore:
    """Minimal REST client using the server-only key stored on Vercel."""

    def __init__(self) -> None:
        self.url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
        self.key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

    @property
    def configured(self) -> bool:
        return self.url.startswith("https://") and bool(self.key)

    def _request(self, method: str, table: str, payload: Any = None, query: str = "") -> Any:
        if not self.configured:
            raise RuntimeError("Supabase persistence is not configured.")
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.url}/rest/v1/{table}{query}",
            data=body,
            method=method,
            headers={
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Prefer": "return=representation,resolution=merge-duplicates",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Supabase request failed ({exc.code}).") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("Supabase is unavailable.") from exc
        return json.loads(raw.decode("utf-8")) if raw else None

    def upsert_profile(self, identity: Identity) -> dict[str, Any]:
        result = self._request(
            "POST",
            "profiles?on_conflict=auth0_subject",
            {"auth0_subject": identity.subject, "email": identity.email, "display_name": identity.name},
        )
        return result[0] if isinstance(result, list) and result else {}

    def profile(self, subject: str) -> dict[str, Any] | None:
        result = self._request("GET", "profiles", query=f"?auth0_subject=eq.{urllib.parse.quote(subject, safe='')}&select=*")
        return result[0] if isinstance(result, list) and result else None

    def profile_preferences(self, subject: str) -> dict[str, Any] | None:
        query = f"?auth0_subject=eq.{urllib.parse.quote(subject, safe='')}&select=display_name,contact_email,avatar_data,updated_at"
        result = self._request("GET", "profile_preferences", query=query)
        return result[0] if isinstance(result, list) and result else None

    @staticmethod
    def _profile_view(identity: Identity, profile: dict[str, Any] | None, preferences: dict[str, Any] | None) -> dict[str, Any]:
        saved = profile or {}
        settings = preferences or {}
        return {
            "subject": identity.subject,
            "email": identity.email or saved.get("email"),
            "display_name": settings.get("display_name") or saved.get("display_name") or identity.name,
            "contact_email": settings.get("contact_email") or identity.email or saved.get("email"),
            "avatar_data": settings.get("avatar_data"),
        }

    def workspace_profile(self, identity: Identity) -> dict[str, Any]:
        profile = self.upsert_profile(identity)
        return self._profile_view(identity, profile, self.profile_preferences(identity.subject))

    @staticmethod
    def _clean_profile_update(payload: dict[str, Any]) -> dict[str, str | None]:
        if not isinstance(payload, dict):
            raise ValueError("Profile details must be a JSON object.")
        display_name = payload.get("display_name")
        contact_email = payload.get("contact_email")
        avatar_data = payload.get("avatar_data", "__unchanged__")
        if not isinstance(display_name, str) or not (1 <= len(display_name.strip()) <= 80):
            raise ValueError("Display name must contain 1 to 80 characters.")
        clean_email = None
        if contact_email is not None:
            if not isinstance(contact_email, str):
                raise ValueError("Contact email must be text.")
            clean_email = contact_email.strip().lower() or None
            if clean_email and (len(clean_email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", clean_email)):
                raise ValueError("Enter a valid contact email address.")
        cleaned: dict[str, str | None] = {"display_name": display_name.strip(), "contact_email": clean_email}
        if avatar_data != "__unchanged__":
            if avatar_data in (None, ""):
                cleaned["avatar_data"] = None
            elif not isinstance(avatar_data, str) or not re.fullmatch(r"data:image/(?:png|jpeg|webp);base64,[A-Za-z0-9+/=]+", avatar_data):
                raise ValueError("Profile photo must be a PNG, JPEG, or WebP image.")
            else:
                try:
                    image_bytes = base64.b64decode(avatar_data.split(",", 1)[1], validate=True)
                except ValueError as exc:
                    raise ValueError("Profile photo data is invalid.") from exc
                if not image_bytes or len(image_bytes) > 300_000:
                    raise ValueError("Profile photo must be 300 KB or smaller.")
                cleaned["avatar_data"] = avatar_data
        return cleaned

    def update_profile_preferences(self, identity: Identity, payload: dict[str, Any]) -> dict[str, Any]:
        settings = self._clean_profile_update(payload)
        self.upsert_profile(identity)
        record = {"auth0_subject": identity.subject, **settings, "updated_at": "now()"}
        # ``updated_at`` is set by the database default on first insert.  A
        # direct timestamp is not necessary for the browser-facing contract.
        record.pop("updated_at")
        self._request("POST", "profile_preferences?on_conflict=auth0_subject", record)
        return self._profile_view(identity, self.profile(identity.subject), self.profile_preferences(identity.subject))

    def memberships(self, profile_id: str | None) -> list[dict[str, Any]]:
        """Return only the caller's organization names and roles, never secrets."""
        if not profile_id:
            return []
        query = (
            f"?profile_id=eq.{urllib.parse.quote(profile_id, safe='')}"
            "&select=role,organization:organizations(name,slug)"
        )
        result = self._request("GET", "organization_memberships", query=query)
        return result if isinstance(result, list) else []

    def audit(self, identity: Identity, event_type: str, metadata: dict[str, Any] | None = None) -> None:
        profile = self.profile(identity.subject)
        self._request(
            "POST",
            "audit_events",
            {
                "profile_id": profile.get("id") if profile else None,
                "event_type": event_type,
                "metadata": metadata or {},
            },
        )

    def save_private_history(
        self,
        identity: Identity,
        analysis_type: str,
        session_label: str,
        model_summary: dict[str, Any],
        decision_text: str | None,
        source_titles: list[str],
    ) -> dict[str, Any]:
        """Persist metadata only under the verified caller's server-side profile.

        The subject is taken solely from a signature-verified Auth0 token; it
        is never supplied by the browser request body.
        """
        profile = self.upsert_profile(identity)
        profile_id = profile.get("id") if isinstance(profile, dict) else None
        if not isinstance(profile_id, str) or not profile_id:
            raise RuntimeError("The authenticated user profile is unavailable.")
        result = self._request(
            "POST",
            "analysis_history",
            {
                "profile_id": profile_id,
                "analysis_type": analysis_type,
                "session_label": session_label[:80],
                "model_summary": model_summary,
                "decision_text": decision_text[:2400] if isinstance(decision_text, str) else None,
                "source_titles": source_titles[:5],
            },
        )
        return result[0] if isinstance(result, list) and result else {}

    def private_history(self, identity: Identity, limit: int = 20) -> list[dict[str, Any]]:
        """Fetch only records that belong to the verified caller."""
        profile = self.profile(identity.subject)
        profile_id = profile.get("id") if isinstance(profile, dict) else None
        if not isinstance(profile_id, str) or not profile_id:
            return []
        safe_limit = max(1, min(int(limit), 50))
        query = (
            f"?profile_id=eq.{urllib.parse.quote(profile_id, safe='')}"
            "&select=id,analysis_type,session_label,model_summary,decision_text,source_titles,created_at"
            f"&order=created_at.desc&limit={safe_limit}"
        )
        result = self._request("GET", "analysis_history", query=query)
        return result if isinstance(result, list) else []


store = SupabaseStore()


def mcp_unauthorized_headers() -> dict[str, str]:
    resource = mcp_resource()
    if not resource:
        return {"WWW-Authenticate": 'Bearer error="invalid_token"'}
    metadata = resource.rsplit("/mcp", 1)[0] + "/.well-known/oauth-protected-resource/mcp"
    return {"WWW-Authenticate": f'Bearer resource_metadata="{metadata}", scope="mcp:read"'}
