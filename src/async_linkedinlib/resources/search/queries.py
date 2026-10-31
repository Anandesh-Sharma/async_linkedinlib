"""The app's persisted search operations and the variables it sends them.

Search screens build a `SearchQueryForInput` (SearchFrameworkUtils.getSearchQuery) and job
search a `JobSearchQueryForInput` (JobSearchQueryUtils); filters travel as a map of query
keys to value lists, which rest.li writes as `(geoUrn:List(103644278),...)`.
"""

from typing import Any

from ...models.search import TypeaheadKind
from ...models.search import Vertical
from ...models.search_filters import Params
from ...transport.voyager import GraphQLQuery

CLUSTERS = GraphQLQuery(
    "voyagerSearchDashClusters.c2c5d4b012c05a6a94396191208d45f6", "SearchClusterCollection"
)
FILTERS = GraphQLQuery(
    "voyagerSearchDashFilterClusters.d163cc1a7c36e8f4472c2b539b730829",
    "SearchFilterClustersByFilters",
)
TYPEAHEAD = GraphQLQuery(
    "voyagerSearchDashReusableTypeahead.ae52ba922ef9ede5129d80936bd4249c",
    "SearchReusableTypeaheadByType",
)
GLOBAL_TYPEAHEAD = GraphQLQuery(
    "voyagerSearchDashTypeahead.0b3defba877012c806fcd8427c7ce135", "SearchGlobalTypeahead"
)
JOB_CARDS = GraphQLQuery(
    "voyagerJobsDashJobCards.eb54097e5bda5435af797ec5bbedf723", "JobCardsByJobSearch"
)
JOB_FILTERS = GraphQLQuery(
    "voyagerJobsDashSearchFilterClustersResource.4a3b04e4d980bf06ab986f66ef129f4e",
    "JobSearchFiltersByJobSeachQuery",
)

# The filter sheet's location typeahead asks for these place types.
GEO_SEARCH_TYPES = ("MARKET_AREA", "COUNTRY_REGION", "ADMIN_DIVISION_1", "CITY")


def search_query(vertical: Vertical, keywords: str, params: Params) -> dict[str, Any]:
    """A `SearchQueryForInput`; keywords are left out when empty, as the app does."""
    return {
        "flagshipSearchIntent": "SEARCH_SRP",
        "keywords": keywords or None,
        "queryParameters": {"resultType": [vertical.value], **params},
        "spellCorrectionEnabled": True,
    }


def search_origin(vertical: Vertical, params: Params) -> str:
    """The origin the app reports: the search bar, a vertical switch or applied filters."""
    if vertical is Vertical.ALL:
        return "GLOBAL_SEARCH_HEADER"
    return "FACETED_SEARCH" if params else "SWITCH_SEARCH_VERTICAL"


def job_query(keywords: str, geo_urn: str | None, params: Params) -> dict[str, Any]:
    """A `JobSearchQueryForInput`; `locationUnion` is the geoUrn member of its union."""
    return {
        "origin": "JOB_SEARCH_PAGE_JOB_FILTER" if params else "JOB_SEARCH_PAGE_SEARCH_BUTTON",
        "keywords": keywords or None,
        "locationUnion": {"geoUrn": geo_urn} if geo_urn else None,
        "selectedFilters": params or None,
        "spellCorrectionEnabled": True,
    }


def typeahead_variables(kind: TypeaheadKind, keywords: str, count: int | None) -> dict[str, Any]:
    """TypeaheadRoutes.buildTypeaheadQuery as the search filter sheet calls it."""
    filter_query: dict[str, Any] = {"standardizationEntityType": "industryV2"}
    if kind is TypeaheadKind.GEO:
        filter_query = {"geoSearchTypes": list(GEO_SEARCH_TYPES), **filter_query}
    return {
        "keywords": keywords,
        "query": {"showFullLastNameForConnections": True, "typeaheadFilterQuery": filter_query},
        "type": kind.value,
        "count": count,
    }
