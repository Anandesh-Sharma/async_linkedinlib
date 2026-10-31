"""Public failures with messages that never include credentials or response bodies."""


class LinkedInError(Exception):
    """Base class for expected client failures."""


class SessionError(LinkedInError):
    """The session file is invalid or cannot be used."""


class SessionInUse(SessionError):
    """Another client owns this session file."""


class AuthenticationError(LinkedInError):
    """Credentials were rejected or the session expired."""


class ChallengeRequired(AuthenticationError):
    """Complete verification in the official app; no automatic continuation occurs."""

    def __init__(self, challenge_url: str | None = None) -> None:
        super().__init__("LinkedIn requires verification in the official app.")
        # The URL can contain private state, so it is never part of the message or repr.
        self.challenge_url = challenge_url


class RateLimited(LinkedInError):
    """No retry occurs; retry_after is the remaining cooldown in seconds."""

    def __init__(self, retry_after: float) -> None:
        super().__init__("LinkedIn rate limit reached; wait before another request.")
        self.retry_after = retry_after


class ProtocolError(LinkedInError):
    """The response does not match the supported protocol."""


class UnconfirmedWrite(ProtocolError):
    """LinkedIn accepted a write, but its reply could not be read.

    The change may have been applied. Read the state back before sending it again; the
    client never retries a write.
    """


class HTTPError(LinkedInError):
    """An HTTP failure, without attaching the credential-bearing HTTPX response.

    `reason` is rest.li's one-line client-error message when the reply carried one.
    """

    def __init__(self, status_code: int, reason: str | None = None) -> None:
        detail = f": {reason}" if reason else "."
        super().__init__(f"LinkedIn returned HTTP {status_code}{detail}")
        self.status_code = status_code
        self.reason = reason


class OperationRejected(LinkedInError):
    """LinkedIn answered but refused the operation, for example a GraphQL validation error.

    `reasons` holds the server's messages; nothing was retried.
    """

    def __init__(self, reasons: tuple[str, ...]) -> None:
        summary = reasons[0] if reasons else "no reason given"
        super().__init__(f"LinkedIn rejected the operation: {summary}")
        self.reasons = reasons


class NetworkError(LinkedInError):
    """The exchange failed; its outcome may be unknown and it was not retried."""
