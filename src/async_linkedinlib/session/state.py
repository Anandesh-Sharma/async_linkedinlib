"""Scoped cookies and atomic, private session persistence."""

import json
import os
import tempfile
import time
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from uuid import uuid4

import httpx

from ..config import ClientProfile
from ..exceptions import SessionError
from .cookies import SessionCookie


@dataclass(slots=True, repr=False)
class Session:
    """Local credential presence is not proof that LinkedIn still accepts the session."""

    device_id: str = field(default_factory=lambda: str(uuid4()))
    profile: ClientProfile = field(default_factory=ClientProfile)
    cookies: list[SessionCookie] = field(default_factory=list)
    member_id: str | None = None
    rate_limit_until: float = 0.0

    def __repr__(self) -> str:
        return f"Session(authenticated={self.authenticated})"

    @property
    def authenticated(self) -> bool:
        return bool(self.cookie_value("li_at") and self.cookie_value("JSESSIONID"))

    def cookie_value(self, name: str, path: str = "/") -> str | None:
        valid = [
            cookie
            for cookie in self.cookies
            if cookie.name == name
            and (cookie.expires is None or cookie.expires > time.time())
            and (path == cookie.path or path.startswith(cookie.path.rstrip("/") + "/"))
            and (not cookie.host_only or cookie.domain == "www.linkedin.com")
        ]
        if not valid:
            return None
        # Prefer the most specific matching cookie, including a host-specific cookie.
        cookie = max(valid, key=lambda c: (len(c.path), len(c.domain.lstrip("."))))
        return cookie.value

    def clear_authentication(self) -> None:
        self.cookies = [c for c in self.cookies if c.name != "li_at"]
        self.member_id = None

    def to_httpx(self) -> httpx.Cookies:
        jar = httpx.Cookies()
        for cookie in self.cookies:
            jar.jar.set_cookie(cookie.to_cookie())
        return jar

    def update_cookies(self, jar: httpx.Cookies) -> None:
        self.cookies = [
            SessionCookie(
                name=c.name,
                value=c.value or "",
                domain=c.domain,
                path=c.path,
                secure=c.secure,
                expires=c.expires,
                host_only=not c.domain_specified,
            )
            for c in jar.jar
            if c.domain.lstrip(".") in {"linkedin.com", "www.linkedin.com"}
        ]

    @classmethod
    def from_cookies(cls, li_at: str, jsessionid: str) -> "Session":
        """Import your own session cookie pair; accepts JSESSIONID with or without quotes."""
        if not li_at.strip() or not jsessionid.strip().strip('"'):
            raise SessionError("Both li_at and JSESSIONID are required.")
        csrf = jsessionid.strip().strip('"')
        return cls(
            cookies=[
                SessionCookie("li_at", li_at.strip(), ".www.linkedin.com"),
                SessionCookie("JSESSIONID", f'"{csrf}"', ".www.linkedin.com"),
            ]
        )

    def save(self, path: str | Path) -> None:
        """Atomically write mode 0600; credentials are never printed or put in errors."""
        destination = Path(path).expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=destination.parent, delete=False
            ) as stream:
                temporary = stream.name
                os.fchmod(stream.fileno(), 0o600)
                json.dump({"schema_version": 1, **asdict(self)}, stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    @classmethod
    def load(cls, path: str | Path) -> "Session":
        """Load supported state without silently replacing corrupt files or expired tokens."""
        try:
            data = json.loads(Path(path).expanduser().read_text())
            if data.pop("schema_version") != 1:
                raise ValueError
            profile = ClientProfile(**data.pop("profile"))
            cookies = [SessionCookie(**cookie) for cookie in data.pop("cookies")]
            state = cls(profile=profile, cookies=cookies, **data)
            if (
                not isinstance(state.device_id, str)
                or not state.device_id
                or any(ch in state.device_id for ch in "\r\n")
                or not isinstance(state.rate_limit_until, (float, int))
                or (state.member_id is not None and not isinstance(state.member_id, str))
            ):
                raise ValueError
            return state
        except (ValueError, TypeError, KeyError, AttributeError, SessionError):
            raise SessionError("Invalid or unsupported LinkedIn session file.") from None
