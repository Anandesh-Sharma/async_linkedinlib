"""Search results, available filters and typeahead matches as Voyager search describes them."""

from copy import deepcopy
from dataclasses import dataclass
from dataclasses import field
from enum import StrEnum
from typing import Any

from ._json import dig
from ._json import integer
from ._json import items
from ._json import obj
from ._json import public_id
from ._json import string
from ._json import text
from ._json import urn_id
from .content import Post


class Vertical(StrEnum):
    """Search verticals (the app's `resultType` values); job search has its own operation."""

    ALL = "ALL"
    PEOPLE = "PEOPLE"
    POSTS = "CONTENT"
    COMPANIES = "COMPANIES"
    GROUPS = "GROUPS"
    SCHOOLS = "SCHOOLS"
    EVENTS = "EVENTS"
    COURSES = "LEARNING"
    PRODUCTS = "PRODUCTS"
    SERVICES = "SERVICES"


class TypeaheadKind(StrEnum):
    """Typeahead lists that turn names into filter values; `Filter.typeahead` names one."""

    GEO = "GEO"
    COMPANY = "COMPANY"
    SCHOOL = "SCHOOL"
    INDUSTRY = "INDUSTRY"
    PEOPLE = "PEOPLE"
    CONNECTIONS = "CONNECTIONS"
    SKILL = "SKILL"  # service categories
    JOB_FUNCTION = "JOB_FUNCTION"
    PRODUCT_CATEGORY = "PRODUCT_CATEGORY"


@dataclass(frozen=True, slots=True)
class PersonResult:
    """A member in people or services results.

    `id` is the profile ID (`ACoA...`) that people filters such as `connection_of` take.
    `distance` is the app's network distance: DISTANCE_1, DISTANCE_2, DISTANCE_3 or
    OUT_OF_NETWORK. `name` can be "LinkedIn Member" for profiles the viewer cannot see.
    """

    urn: str
    id: str | None
    member_urn: str | None
    name: str | None
    headline: str | None
    location: str | None
    distance: str | None
    public_id: str | None
    url: str | None
    verified: bool
    summary: str | None = None
    insights: tuple[str, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_entity(cls, entity: dict[str, Any]) -> "PersonResult | None":
        """Build from an `EntityResultViewModel`; None when it is not a profile."""
        urn = entity_urn(entity)
        if not urn or not urn.startswith("urn:li:fsd_profile:"):
            return None
        tracking = string(entity, "trackingUrn")
        icons = items(dig(entity, "badgeIcon", "attributes"))
        badge = " ".join(string(icon, "detailData", "systemImage") or "" for icon in icons)
        url = _url(entity)
        return cls(
            urn=urn,
            id=urn_id(urn),
            member_urn=tracking if tracking and tracking.startswith("urn:li:member:") else None,
            name=text(entity, "title"),
            headline=text(entity, "primarySubtitle"),
            location=text(entity, "secondarySubtitle"),
            distance=string(entity, "entityCustomTrackingInfo", "memberDistance"),
            public_id=public_id(url, ("in",)),
            url=url,
            verified="VERIFIED" in badge,
            summary=text(entity, "summary"),
            insights=_insights(entity),
            raw=deepcopy(entity),
        )


@dataclass(frozen=True, slots=True)
class SearchResult:
    """A company, group, school, event, course, product or job in search results.

    `urn` is the entity (for example `urn:li:fsd_company:1035` or `urn:li:fsd_jobPosting:<id>`)
    and `id` its last part, the value company and school filters take. `kind` is the URN's
    entity type without the `fsd_` prefix: company, group, event, lyndaCourse, jobPosting...
    """

    urn: str
    id: str | None
    kind: str | None
    tracking_urn: str | None
    title: str | None
    subtitle: str | None
    secondary_subtitle: str | None
    summary: str | None
    url: str | None
    insights: tuple[str, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_entity(cls, entity: dict[str, Any]) -> "SearchResult | None":
        urn = entity_urn(entity)
        if not urn:
            return None
        kind = urn.split(":")[2] if urn.count(":") >= 3 else None
        return cls(
            urn=urn,
            id=urn_id(urn),
            kind=kind.removeprefix("fsd_") if kind else None,
            tracking_urn=string(entity, "trackingUrn"),
            title=text(entity, "title"),
            subtitle=text(entity, "primarySubtitle"),
            secondary_subtitle=text(entity, "secondarySubtitle"),
            summary=text(entity, "summary"),
            url=_url(entity),
            insights=_insights(entity),
            raw=deepcopy(entity),
        )


@dataclass(frozen=True, slots=True)
class ResultGroup:
    """One block of blended results, such as "People" or "Posts", in the server's order."""

    title: str | None
    items: tuple["PersonResult | SearchResult | Post", ...]
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class FilterOption:
    """One value a filter offers; `value` is what the filter's key takes."""

    value: str
    label: str | None
    selected: bool | None = None
    count: int | None = None


@dataclass(frozen=True, slots=True)
class Filter:
    """A filter the app shows for a query.

    `key` is the query parameter (for example `geoUrn` or `timePostedRange`); typed filter
    fields map to these keys, and any key can go in a filter's `extra`. `kind` is the app's
    render type (MULTI_SELECT, SINGLE_SELECT, TOGGLE, FREE_TEXT, SLIDER). `options` are the
    suggested values; `typeahead` names the `TypeaheadKind` that finds more.
    """

    key: str
    label: str | None
    kind: str | None
    options: tuple[FilterOption, ...]
    typeahead: str | None = None
    applied: int | None = None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Filter | None":
        key = string(data, "parameterName")
        if not key or data.get("upsellSlot") or data.get("upsellSlotUrn"):
            return None
        options: dict[str, FilterOption] = {}
        values = items(data.get("primaryFilterValues")) + items(data.get("secondaryFilterValues"))
        for value in values:
            option = string(value, "value")
            if option is not None and option not in options:
                selected = value.get("selected")
                options[option] = FilterOption(
                    value=option,
                    label=string(value, "displayName"),
                    selected=selected if isinstance(selected, bool) else None,
                    count=integer(value, "count"),
                )
        return cls(
            key=key,
            label=text(data, "displayName"),
            kind=string(data, "renderType"),
            options=tuple(options.values()),
            typeahead=string(data, "typeaheadType"),
            applied=integer(data, "appliedCount"),
        )


def filters_from_clusters(clusters: list[dict[str, Any]]) -> tuple[Filter, ...]:
    """Every filter of a `SearchFilterCluster` collection, once each, in the app's order.

    The "all filters" sheet (secondary) lists every filter; the top bar (primary) repeats a few.
    """
    found: dict[str, Filter] = {}
    for cluster in clusters:
        for side in ("secondary", "primary"):
            views = items(cluster.get(f"{side}Filters"))
            for group in items(cluster.get(f"{side}FilterGroups")):
                views += items(group.get("filters"))
            for view in views:
                parsed = Filter.from_json(view)
                if parsed and parsed.key != "resultType" and parsed.key not in found:
                    found[parsed.key] = parsed
    return tuple(found.values())


@dataclass(frozen=True, slots=True)
class Suggestion:
    """A typeahead match.

    `id` is the value filters take (a geo, company, school, industry or profile ID).
    `urn` is the matched entity; it is None for a keyword suggestion from `suggest`.
    `kind` is the entity type for typed lookups (geo, company, profile...) and the
    suggestion type (ENTITY_TYPEAHEAD, QUERY_SUGGESTION_TYPEAHEAD) for `suggest`.
    """

    title: str | None
    subtitle: str | None
    urn: str | None
    id: str | None
    tracking_urn: str | None
    kind: str | None
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_typeahead(cls, element: dict[str, Any]) -> "Suggestion":
        """Read a `TypeaheadViewModel`, whose `target` union holds the matched entity as a
        record with `entityUrn` (geo, company, profile) or as a bare URN (jobFunction)."""
        kind, urn = None, None
        for key, value in obj(element.get("target")).items():
            found = value if isinstance(value, str) else string(value, "entityUrn")
            if found and found.startswith("urn:li:"):
                kind, urn = key, found
                break
        tracking = string(element, "trackingUrn")
        return cls(
            title=text(element, "title"),
            subtitle=text(element, "subtitle"),
            urn=urn,
            id=urn_id(urn or tracking),
            tracking_urn=tracking,
            kind=kind,
            raw=deepcopy(element),
        )

    @classmethod
    def from_global(cls, element: dict[str, Any]) -> "Suggestion":
        """Read a search-bar `SearchSuggestionViewModel`."""
        view = obj(element.get("entityLockupView"))
        tracking = string(view, "trackingUrn")
        return cls(
            title=text(view, "title"),
            subtitle=text(view, "subtitle"),
            urn=None,
            id=urn_id(tracking),
            tracking_urn=tracking,
            kind=string(element, "suggestionType"),
            raw=deepcopy(element),
        )


def entity_urn(entity: dict[str, Any]) -> str | None:
    """The entity inside `urn:li:fsd_entityResultViewModel:(<entity>,SEARCH_SRP,DEFAULT)`."""
    wrapper = string(entity, "entityUrn")
    if not wrapper:
        return None
    head, _, rest = wrapper.partition(":(")
    if not rest or not head.endswith("fsd_entityResultViewModel"):
        return wrapper
    depth = 0
    for index, char in enumerate(rest):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            return rest[:index] or None
    return None


def _url(entity: dict[str, Any]) -> str | None:
    url = string(entity, "navigationUrl")
    return url.split("?", 1)[0] if url else None


def _insights(entity: dict[str, Any]) -> tuple[str, ...]:
    found = []
    for result in items(entity.get("insightsResolutionResults")):
        label = text(result, "simpleInsight", "title")
        if label:
            found.append(label)
    return tuple(found)
