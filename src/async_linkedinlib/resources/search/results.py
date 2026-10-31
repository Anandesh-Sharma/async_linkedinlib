"""Decode search replies into pages whose cursors continue only the same query."""

from collections.abc import Callable
from typing import Any
from typing import TypeVar

from ...models._json import dig
from ...models._json import integer
from ...models._json import items
from ...models._json import obj
from ...models._json import text
from ...models.content import Post
from ...models.pagination import Page
from ...models.search import PersonResult
from ...models.search import ResultGroup
from ...models.search import SearchResult
from .. import paging

T = TypeVar("T")
Item = PersonResult | SearchResult | Post


Where = tuple[str, str, int, int, str]  # operation, scope, start, count, cursor owner


def result_page(
    reply: dict[str, Any], read: Callable[[dict[str, Any]], T | None], where: Where
) -> Page[T]:
    """Flatten the items of every cluster on a vertical's page. Banners, counts and feedback
    cards are skipped."""
    entries = [
        obj(entry.get("item"))
        for cluster in items(reply.get("elements"))
        for entry in items(cluster.get("items"))
    ]
    return paging.page(reply, read, *where, elements=entries, total=_total(reply))


def group_page(reply: dict[str, Any], where: Where) -> Page[ResultGroup]:
    """Blended results: one group per cluster that holds people, entities or posts."""
    return paging.page(reply, _group, *where, total=_total(reply))


def job_page(
    reply: dict[str, Any], read: Callable[[dict[str, Any]], T | None], where: Where
) -> Page[T]:
    cards = [obj(element.get("jobCard")) for element in items(reply.get("elements"))]
    return paging.page(reply, read, *where, elements=cards)


def _group(cluster: dict[str, Any]) -> ResultGroup | None:
    found = [
        result
        for entry in items(cluster.get("items"))
        if (result := any_item(obj(entry.get("item")))) is not None
    ]
    return ResultGroup(text(cluster, "title"), tuple(found), cluster) if found else None


def person(item: dict[str, Any]) -> PersonResult | None:
    return PersonResult.from_entity(obj(item.get("entityResult")))


def entity(item: dict[str, Any]) -> SearchResult | None:
    found = obj(item.get("entityResult"))
    return SearchResult.from_entity(found) if found else None


def post(item: dict[str, Any]) -> Post | None:
    update = obj(dig(item, "searchFeedUpdate", "update"))
    if not update:
        return None
    return Post.from_update(update)


def any_item(item: dict[str, Any]) -> Item | None:
    """A blended item: a profile, another entity, or a post."""
    if "searchFeedUpdate" in item:
        return post(item)
    return person(item) or entity(item)


def _total(reply: dict[str, Any]) -> int | None:
    total = integer(reply, "metadata", "totalResultCount")
    return total if total is not None else integer(reply, "paging", "total")
