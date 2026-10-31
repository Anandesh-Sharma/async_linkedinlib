"""The recorded Google ID-token exchange; Google token acquisition is caller-owned."""

import asyncio
import secrets

from ..exceptions import AuthenticationError
from ..exceptions import ChallengeRequired
from ..exceptions import ProtocolError
from ..models import Member
from ..resources import Account
from ..session.cookies import SessionCookie
from ..transport import Transport


class Auth:
    """Bootstrap fresh browser cookies and exchange one caller-supplied Google ID token."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport
        self._lock = asyncio.Lock()

    async def prepare(self) -> None:
        """Fetch current server cookies; create the mobile CSRF cookie if none was issued."""
        await self._transport.request("GET", "/mob/tracking")
        state = self._transport.session
        if not state.cookie_value("JSESSIONID"):
            state.cookies.append(
                SessionCookie(
                    "JSESSIONID",
                    f'"ajax:{secrets.randbelow(9 * 10**18) + 10**18}"',
                    ".www.linkedin.com",
                )
            )
        self._transport.checkpoint()

    async def login_google(self, id_token: str) -> Member:
        """Exchange a fresh token for the LinkedIn Android audience, then verify the member.

        Tokens are not persisted or automatically retried. Challenges must be completed
        in the official app. This does not obtain a Google token or accept passwords.
        """
        if not isinstance(id_token, str) or not id_token.strip():
            raise ValueError("A fresh Google ID token is required.")
        async with self._lock:
            state = self._transport.session
            if state.authenticated:
                raise AuthenticationError(
                    "A session already exists; use account.me() to verify it."
                )
            await self.prepare()
            form = {
                "soogleLoginRequestType": "ONE_TAP_AUTO_LOGIN",
                "googleIdToken": id_token,
                "client_enabled_features": "ANDROID_NATIVE_CAPTCHA",
            }
            for name in ("JSESSIONID", "bcookie", "bscookie", "lang", "lidc"):
                value = state.cookie_value(name)
                if value is not None:
                    form[name] = value.strip('"')
            try:
                response = await self._transport.request("POST", "/uas/authenticate", form)
                result = self._transport.json_object(response)
                challenge = result.get("challenge_url")
                if isinstance(challenge, str) and challenge:
                    raise ChallengeRequired(challenge)
                if result.get("login_result") != "PASS":
                    raise AuthenticationError("LinkedIn did not accept the Google sign-in.")
                if not state.authenticated:
                    raise ProtocolError("Login succeeded without the required session cookies.")
            except BaseException:
                state.clear_authentication()
                self._transport.checkpoint()
                raise
            finally:
                form.clear()
            # A temporary verification failure must not discard a successfully issued session.
            return await Account(self._transport).me()
