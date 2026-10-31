"""Search people, posts, companies, jobs and other verticals, their filters and typeahead.

Every call is one read. Nothing here adds to the viewer's search history; the app sends
that as a separate write, which this client does not.
"""

from collections.abc import Callable
from typing import Any
from typing import TypeVar

from ...models._json import items
from ...models.content import Post
from ...models.pagination import Cursor
from ...models.pagination import Page
from ...models.search import Filter
from ...models.search import PersonResult
from ...models.search import ResultGroup
from ...models.search import SearchResult
from ...models.search import Suggestion
from ...models.search import TypeaheadKind
from ...models.search import Vertical
from ...models.search import filters_from_clusters
from ...models.search_filters import CompanyFilters
from ...models.search_filters import CourseFilters
from ...models.search_filters import Params
from ...models.search_filters import PeopleFilters
from ...models.search_filters import PostFilters
from ...models.search_filters import ProductFilters
from ...models.search_filters import ServiceFilters
from ...models.search_jobs import JobFilters
from ...models.search_jobs import JobResult
from ...transport import restli
from ...transport.voyager import Voyager
from .. import paging
from . import queries
from . import results

T = TypeVar("T")
VerticalFilters = (
    PeopleFilters | PostFilters | CompanyFilters | ServiceFilters | ProductFilters | CourseFilters
)
FILTER_TYPES: dict[Vertical, type[VerticalFilters]] = {
    Vertical.PEOPLE: PeopleFilters,
    Vertical.POSTS: PostFilters,
    Vertical.COMPANIES: CompanyFilters,
    Vertical.SERVICES: ServiceFilters,
    Vertical.PRODUCTS: ProductFilters,
    Vertical.COURSES: CourseFilters,
}
MAX_COUNT = 50


class Search:
    """Search LinkedIn the way the app's search and job search screens do.

    Vertical methods return one page; pass `page.next` as `cursor` with the same keywords
    and filters to continue. `count` is a page size from 1 to 50.
    """

    def __init__(self, voyager: Voyager) -> None:
        self._voyager = voyager

    async def all(
        self, keywords: str, *, count: int = 10, cursor: Cursor | None = None
    ) -> Page[ResultGroup]:
        """Blended results: groups such as Jobs, Posts, People and Companies."""
        if not _keywords(keywords):
            raise ValueError("Blended search needs keywords.")
        reply, where = await self._clusters(Vertical.ALL, keywords, {}, count, cursor)
        return results.group_page(reply, where)

    async def people(
        self,
        keywords: str = "",
        filters: PeopleFilters | None = None,
        *,
        count: int = 10,
        cursor: Cursor | None = None,
    ) -> Page[PersonResult]:
        return await self._vertical(
            Vertical.PEOPLE, keywords, filters, count, cursor, results.person
        )

    async def posts(
        self,
        keywords: str = "",
        filters: PostFilters | None = None,
        *,
        count: int = 10,
        cursor: Cursor | None = None,
    ) -> Page[Post]:
        """Posts as feed `Post`s; results the feed model cannot read are left out."""
        return await self._vertical(Vertical.POSTS, keywords, filters, count, cursor, results.post)

    async def companies(
        self,
        keywords: str = "",
        filters: CompanyFilters | None = None,
        *,
        count: int = 10,
        cursor: Cursor | None = None,
    ) -> Page[SearchResult]:
        return await self._vertical(
            Vertical.COMPANIES, keywords, filters, count, cursor, results.entity
        )

    async def groups(
        self, keywords: str, *, count: int = 10, cursor: Cursor | None = None
    ) -> Page[SearchResult]:
        return await self._vertical(Vertical.GROUPS, keywords, None, count, cursor, results.entity)

    async def schools(
        self, keywords: str, *, count: int = 10, cursor: Cursor | None = None
    ) -> Page[SearchResult]:
        return await self._vertical(Vertical.SCHOOLS, keywords, None, count, cursor, results.entity)

    async def events(
        self, keywords: str, *, count: int = 10, cursor: Cursor | None = None
    ) -> Page[SearchResult]:
        return await self._vertical(Vertical.EVENTS, keywords, None, count, cursor, results.entity)

    async def courses(
        self,
        keywords: str = "",
        filters: CourseFilters | None = None,
        *,
        count: int = 10,
        cursor: Cursor | None = None,
    ) -> Page[SearchResult]:
        """LinkedIn Learning courses."""
        return await self._vertical(
            Vertical.COURSES, keywords, filters, count, cursor, results.entity
        )

    async def products(
        self,
        keywords: str = "",
        filters: ProductFilters | None = None,
        *,
        count: int = 10,
        cursor: Cursor | None = None,
    ) -> Page[SearchResult]:
        return await self._vertical(
            Vertical.PRODUCTS, keywords, filters, count, cursor, results.entity
        )

    async def services(
        self,
        keywords: str = "",
        filters: ServiceFilters | None = None,
        *,
        count: int = 10,
        cursor: Cursor | None = None,
    ) -> Page[PersonResult]:
        """Members who offer services."""
        return await self._vertical(
            Vertical.SERVICES, keywords, filters, count, cursor, results.person
        )

    async def jobs(
        self,
        keywords: str = "",
        filters: JobFilters | None = None,
        *,
        count: int = 25,
        cursor: Cursor | None = None,
    ) -> Page[JobResult]:
        """Job cards; pass `JobResult.id` to the jobs feature for details or applying."""
        query = _job_query(keywords, filters)
        operation, scope = "search.jobs", restli.encode(query)
        start, _token = paging.resume(cursor, operation, scope, self._voyager.owner)
        size = _count(count)
        data = await self._voyager.query(
            queries.JOB_CARDS,
            {"query": query, "count": size, "start": start, "includeJobState": True},
        )
        reply = paging.collection(data, "jobsDashJobCardsByJobSearch")
        where = (operation, scope, start, size, self._voyager.owner)
        return results.job_page(reply, JobResult.from_card, where)

    async def filters(
        self,
        vertical: Vertical,
        keywords: str = "",
        applied: VerticalFilters | None = None,
    ) -> tuple[Filter, ...]:
        """The filters and suggested values the app offers for a vertical and query."""
        vertical = Vertical(vertical)
        query = queries.search_query(vertical, _keywords(keywords), _params(vertical, applied))
        data = await self._voyager.query(queries.FILTERS, {"query": query})
        reply = paging.collection(data, "searchDashFilterClustersByFilters")
        return filters_from_clusters(items(reply.get("elements")))

    async def job_filters(
        self, keywords: str = "", filters: JobFilters | None = None
    ) -> tuple[Filter, ...]:
        """Job search filters for a query, such as salary buckets and distances near a place."""
        data = await self._voyager.query(
            queries.JOB_FILTERS, {"query": _job_query(keywords, filters)}
        )
        reply = paging.collection(data, "jobsDashSearchFilterClustersResourceByFilters")
        return filters_from_clusters(items(reply.get("elements")))

    async def typeahead(
        self, kind: TypeaheadKind, keywords: str, *, count: int | None = None
    ) -> tuple[Suggestion, ...]:
        """Find filter values by name, for example `typeahead(TypeaheadKind.GEO, "Berlin")`."""
        kind = TypeaheadKind(kind)
        if not _keywords(keywords):
            raise ValueError("Typeahead needs some text to match.")
        variables = queries.typeahead_variables(
            kind, _keywords(keywords), None if count is None else _count(count)
        )
        data = await self._voyager.query(queries.TYPEAHEAD, variables)
        reply = paging.collection(data, "searchDashReusableTypeaheadByType")
        return tuple(Suggestion.from_typeahead(item) for item in items(reply.get("elements")))

    async def suggest(self, keywords: str) -> tuple[Suggestion, ...]:
        """The search bar's suggestions: matching entities and completed keywords."""
        if not _keywords(keywords):
            raise ValueError("Suggestions need some text to match.")
        data = await self._voyager.query(queries.GLOBAL_TYPEAHEAD, {"query": _keywords(keywords)})
        reply = paging.collection(data, "searchDashTypeaheadByGlobalTypeahead")
        return tuple(Suggestion.from_global(item) for item in items(reply.get("elements")))

    async def _vertical(
        self,
        vertical: Vertical,
        keywords: str,
        filters: VerticalFilters | None,
        count: int,
        cursor: Cursor | None,
        read: Callable[[dict[str, Any]], T | None],
    ) -> Page[T]:
        params = _params(vertical, filters)
        reply, where = await self._clusters(vertical, keywords, params, count, cursor)
        return results.result_page(reply, read, where)

    async def _clusters(
        self, vertical: Vertical, keywords: str, params: Params, count: int, cursor: Cursor | None
    ) -> tuple[dict[str, Any], results.Where]:
        query = queries.search_query(vertical, _keywords(keywords), params)
        operation, scope = f"search.{vertical.name.lower()}", restli.encode(query)
        start, token = paging.resume(cursor, operation, scope, self._voyager.owner)
        size = _count(count)
        variables = {
            "start": start,
            "count": size,
            "origin": queries.search_origin(vertical, params),
            "query": query,
            "paginationToken": token,
        }
        data = await self._voyager.query(queries.CLUSTERS, variables)
        reply = paging.collection(data, "searchDashClustersByAll")
        return reply, (operation, scope, start, size, self._voyager.owner)


def _params(vertical: Vertical, filters: VerticalFilters | None) -> Params:
    if filters is None:
        return {}
    expected = FILTER_TYPES.get(vertical)
    if expected is None or not isinstance(filters, expected):
        name = expected.__name__ if expected else "no filters"
        raise ValueError(f"{vertical.name.lower()} search takes {name}.")
    return filters.params()


def _job_query(keywords: str, filters: JobFilters | None) -> dict[str, Any]:
    if filters is not None and not isinstance(filters, JobFilters):
        raise ValueError("Job search takes JobFilters.")
    filters = filters or JobFilters()
    return queries.job_query(_keywords(keywords), filters.geo_urn(), filters.params())


def _keywords(keywords: str) -> str:
    if not isinstance(keywords, str):
        raise ValueError("keywords must be text.")
    return " ".join(keywords.split())


def _count(count: int) -> int:
    if type(count) is not int or not 1 <= count <= MAX_COUNT:
        raise ValueError(f"count must be an integer from 1 to {MAX_COUNT}.")
    return count
