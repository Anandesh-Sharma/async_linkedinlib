"""Turn Voyager collections into pages, continuing them the way the app's pager does."""

from collections.abc import Callable
from typing import Any
from typing import TypeVar

from ..exceptions import ProtocolError
from ..models._json import integer
from ..models._json import items
from ..models._json import obj
from ..models._json import string
from ..models.pagination import Cursor
from ..models.pagination import Page

T = TypeVar("T")


def collection(data: dict[str, Any], field: str) -> dict[str, Any]:
    """The named collection of a GraphQL `data` object; it must carry an elements list."""
    found = data.get(field)
    if not isinstance(found, dict) or not isinstance(found.get("elements"), list):
        raise ProtocolError(f"LinkedIn's reply had no {field} collection.")
    return found


def resume(
    cursor: Cursor | None, operation: str, scope: str, owner: str = ""
) -> tuple[int, str | None]:
    """Where a request starts and its pagination token; the cursor must belong to it."""
    if cursor is None:
        return 0, None
    if not isinstance(cursor, Cursor):
        raise ValueError("cursor must be a Cursor from a previous page.")
    cursor.check(operation, scope, owner)
    return cursor.start, cursor.token


def page(
    found: dict[str, Any],
    read: Callable[[dict[str, Any]], T | None],
    operation: str,
    scope: str,
    start: int,
    count: int,
    owner: str = "",
    *,
    elements: list[dict[str, Any]] | None = None,
    total: int | None = None,
) -> Page[T]:
    """Read each element; elements that `read` turns into None are left out of `items`.

    `elements` replaces the collection's own when results are nested deeper. `total` is
    shown instead of `paging.total` for finders that report a separate estimate; paging
    still stops at `paging.total`. Paging follows the collection's own elements, so a page
    whose entries are all skipped still continues.
    """
    own = items(found.get("elements"))
    bound = integer(found, "paging", "total")
    results = tuple(
        result for result in map(read, own if elements is None else elements) if result is not None
    )
    following = _next(found, bool(own), bound, operation, scope, start, count, owner)
    return Page(results, following, bound if total is None else total, found)


def _next(
    found: dict[str, Any],
    any_elements: bool,
    total: int | None,
    operation: str,
    scope: str,
    start: int,
    count: int,
    owner: str,
) -> Cursor | None:
    # The app continues at paging.start + paging.count while the total allows it, or while
    # pages come back non-empty when there is no total. An empty page always ends here.
    if not any_elements:
        return None
    paging = obj(found.get("paging"))
    first = integer(paging, "start")
    size = integer(paging, "count")
    step = size if size is not None and size > 0 else count
    next_start = (start if first is None else first) + step
    if total is not None and next_start >= total:
        return None
    token = string(found, "metadata", "paginationToken") or None
    return Cursor(operation, scope, next_start, token, owner)
