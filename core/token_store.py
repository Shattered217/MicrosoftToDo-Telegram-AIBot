"""core.token_store

Persist tokens locally (host-side) in a private file.

We intentionally do NOT write tokens into git-tracked files or logs.
Default path:
  ~/.openclaw/state/mstodo/tokens.json

File permissions:
- Create with 0600 (best-effort).

This is a simple store meant for the OpenClaw+MCP integration.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional


def _default_path() -> str:
    return os.path.expanduser("~/.openclaw/state/mstodo/tokens.json")


@dataclass
class TokenBundle:
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_at: Optional[float] = None  # unix timestamp
    token_type: Optional[str] = None
    scope: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TokenBundle":
        return cls(
            access_token=d.get("access_token"),
            refresh_token=d.get("refresh_token"),
            expires_at=d.get("expires_at"),
            token_type=d.get("token_type"),
            scope=d.get("scope"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "token_type": self.token_type,
            "scope": self.scope,
        }


class TokenStore:
    def __init__(self, path: Optional[str] = None):
        self.path = path or _default_path()

    def load(self) -> TokenBundle:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return TokenBundle.from_dict(json.load(f) or {})
        except FileNotFoundError:
            return TokenBundle()

    def save(self, bundle: TokenBundle) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(bundle.to_dict(), f, ensure_ascii=False, indent=2)
        try:
            os.chmod(tmp, 0o600)
        except Exception:
            pass
        os.replace(tmp, self.path)
        try:
            os.chmod(self.path, 0o600)
        except Exception:
            pass
