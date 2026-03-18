"""core.oauth

Interactive OAuth helpers for Microsoft identity platform (v2 endpoint).

Flow:
- Begin: generate auth URL (with state) and return to user.
- Finish: user pastes redirect URL (or code) back; we exchange for tokens.

This is designed for a "copy/paste" loop (no local callback server required).

We keep this minimal and compatible with the existing get_tokens.py behavior.
(PKCE could be added later; current repo script works without it.)
"""

from __future__ import annotations

import secrets
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import httpx


DEFAULT_REDIRECT_URI = "http://localhost:3000/callback"
DEFAULT_SCOPES = "offline_access https://graph.microsoft.com/Tasks.ReadWrite https://graph.microsoft.com/User.Read"


@dataclass
class AuthSession:
    state: str
    created_at: float
    redirect_uri: str = DEFAULT_REDIRECT_URI


def build_authorize_url(
    *,
    client_id: str,
    tenant_id: str = "consumers",
    redirect_uri: str = DEFAULT_REDIRECT_URI,
    scopes: str = DEFAULT_SCOPES,
    state: Optional[str] = None,
) -> Tuple[str, AuthSession]:
    state = state or secrets.token_urlsafe(16)
    sess = AuthSession(state=state, created_at=time.time(), redirect_uri=redirect_uri)

    authority = f"https://login.microsoftonline.com/{tenant_id}"
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": scopes,
        "state": state,
    }
    return f"{authority}/oauth2/v2.0/authorize?{urllib.parse.urlencode(params)}", sess


def parse_code_from_redirect(redirect: str) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
    """Return (code, state, params). Accepts full URL or just querystring."""
    redirect = (redirect or "").strip()
    if not redirect:
        return None, None, {}

    # allow user to paste just the code
    if "http" not in redirect and "=" not in redirect and len(redirect) > 10:
        return redirect, None, {"code": redirect}

    # if user pastes only query part
    if redirect.startswith("?"):
        qs = redirect[1:]
    else:
        try:
            parsed = urllib.parse.urlparse(redirect)
            qs = parsed.query
        except Exception:
            qs = redirect

    params = dict(urllib.parse.parse_qsl(qs, keep_blank_values=True))
    return params.get("code"), params.get("state"), params


async def exchange_code_for_token(
    *,
    client_id: str,
    code: str,
    tenant_id: str = "consumers",
    redirect_uri: str = DEFAULT_REDIRECT_URI,
    scopes: str = DEFAULT_SCOPES,
    client_secret: Optional[str] = None,
    timeout_s: float = 20.0,
) -> Dict[str, Any]:
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    token_url = f"{authority}/oauth2/v2.0/token"

    data = {
        "client_id": client_id,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "scope": scopes,
    }
    if client_secret:
        data["client_secret"] = client_secret

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        r = await client.post(token_url, data=data)
        try:
            payload = r.json()
        except Exception:
            payload = {"error": "invalid_json", "error_description": r.text}

    if r.status_code >= 400:
        # normalize
        if isinstance(payload, dict):
            payload.setdefault("error", f"http_{r.status_code}")
        else:
            payload = {"error": f"http_{r.status_code}", "error_description": str(payload)}
    return payload
