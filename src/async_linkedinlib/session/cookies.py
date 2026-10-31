"""Scoped, serializable cookies."""

from dataclasses import dataclass
from http.cookiejar import Cookie

from ..exceptions import SessionError


@dataclass(slots=True, repr=False)
class SessionCookie:
    """Preserve cookie scope and expiry instead of flattening the cookie jar."""

    name: str
    value: str
    domain: str
    path: str = "/"
    secure: bool = True
    expires: int | None = None
    host_only: bool = False

    def __post_init__(self) -> None:
        if (
            not all(isinstance(v, str) for v in (self.name, self.value, self.domain, self.path))
            or not self.name
            or not self.path.startswith("/")
            or self.domain.lstrip(".") not in {"linkedin.com", "www.linkedin.com"}
            or any(ch in self.name + self.value for ch in "\r\n")
            or type(self.secure) is not bool
            or type(self.host_only) is not bool
            or (self.expires is not None and type(self.expires) is not int)
        ):
            raise SessionError("Invalid LinkedIn cookie state.")

    def to_cookie(self) -> Cookie:
        return Cookie(
            version=0,
            name=self.name,
            value=self.value,
            port=None,
            port_specified=False,
            domain=self.domain,
            domain_specified=not self.host_only,
            domain_initial_dot=self.domain.startswith("."),
            path=self.path,
            path_specified=True,
            secure=self.secure,
            expires=self.expires,
            discard=self.expires is None,
            comment=None,
            comment_url=None,
            rest={},
        )
