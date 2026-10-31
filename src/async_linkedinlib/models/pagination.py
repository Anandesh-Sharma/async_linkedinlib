"""Result pages whose cursors only continue the request that produced them."""

from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import Generic
from typing import TypeVar

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Cursor:
    """Where the next page starts, tied to one operation, query and session.

    `token` is LinkedIn's opaque pagination token when the operation issues one. `owner`
    names the session that read the page (its device ID); an empty owner, as in a cursor
    built by hand, is accepted by any session.
    """

    operation: str
    scope: str
    start: int
    token: str | None = field(default=None, repr=False)
    owner: str = field(default="", repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.operation or not isinstance(self.scope, str):
            raise ValueError("A cursor needs its operation and query scope.")
        if type(self.start) is not int or self.start < 0:
            raise ValueError("A cursor start must be a nonnegative integer.")

    def check(self, operation: str, scope: str, owner: str = "") -> None:
        """Refuse a cursor from a different operation, query or session."""
        if (self.operation, self.scope) != (operation, scope):
            raise ValueError("This cursor belongs to a different operation or query.")
        if self.owner and owner and self.owner != owner:
            raise ValueError("This cursor belongs to a different session.")


@dataclass(frozen=True, slots=True)
class Page(Generic[T]):
    """One page of results; reading it never fetches another page."""

    items: tuple[T, ...]
    next: Cursor | None = None
    total: int | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def has_more(self) -> bool:
        return self.next is not None
