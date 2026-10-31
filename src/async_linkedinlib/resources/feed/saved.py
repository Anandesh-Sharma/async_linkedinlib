"""The viewer's saved posts, which the app lists as "My items" search results.

Every reply to this list carries a GraphQL error beside complete data: the server reports a
null in `metadata.entityResultAttributes`, a field the list does not use, so the read accepts
null-field errors and nothing else.
"""

from ...models._json import items
from ...models._json import obj
from ...models.feed import SavedPost
from ...models.pagination import Cursor
from ...models.pagination import Page
from ...transport.voyager import Voyager
from .. import paging
from ..search.queries import CLUSTERS
from . import urns

FIELD = "searchDashClustersByAll"
_INTENT = "SEARCH_MY_ITEMS_SAVED_POSTS"


async def read(voyager: Voyager, count: int, cursor: Cursor | None) -> Page[SavedPost]:
    """One page of saved posts, most recently saved first."""
    size = urns.count(count)
    start, token = paging.resume(cursor, "feed.saved", "", voyager.owner)
    variables = {
        "query": {"flagshipSearchIntent": _INTENT},
        "count": size,
        "paginationToken": token,
        "start": start,
    }
    data = await voyager.query(CLUSTERS, variables, ignore_null_field_errors=True)
    found = paging.collection(data, FIELD)
    # Each search cluster lists entity results; saved posts are those results.
    results = [
        obj(entry.get("item")).get("entityResult")
        for cluster in items(found.get("elements"))
        for entry in items(cluster.get("items"))
    ]
    return paging.page(
        found,
        SavedPost.from_result,
        "feed.saved",
        "",
        start,
        size,
        voyager.owner,
        elements=[result for result in results if isinstance(result, dict)],
    )
