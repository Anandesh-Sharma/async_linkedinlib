"""Typed search filters per vertical, mapped to the query keys the app's filter sheets use.

ID fields take IDs or simple URNs (`"1035"`, `"urn:li:fsd_company:1035"`); typeahead
`Suggestion.id` values fit directly. `extra` adds raw query keys from `Search.filters()` that
have no typed field, for example `{"seniorityV2": ["120"]}`; it cannot repeat a typed key.
"""

import re
from collections.abc import Mapping
from collections.abc import Sequence
from dataclasses import dataclass
from dataclasses import field
from enum import StrEnum
from typing import Any

Params = dict[str, list[str]]


class Network(StrEnum):
    """Connection degree."""

    FIRST = "F"
    SECOND = "S"
    THIRD_PLUS = "O"


class PostSort(StrEnum):
    RELEVANCE = "relevance"  # Top match
    LATEST = "date_posted"


class DatePosted(StrEnum):
    PAST_24_HOURS = "past-24h"
    PAST_WEEK = "past-week"
    PAST_MONTH = "past-month"


class ContentType(StrEnum):
    VIDEOS = "videos"
    IMAGES = "photos"
    JOB_POSTS = "jobs"
    LIVE_VIDEOS = "liveVideos"
    DOCUMENTS = "documents"
    COLLABORATIVE_ARTICLES = "collaborativeArticles"


class PostedBy(StrEnum):
    FIRST_CONNECTIONS = "first"
    ME = "me"
    PEOPLE_YOU_FOLLOW = "following"


class CompanySize(StrEnum):
    SIZE_1_10 = "B"
    SIZE_11_50 = "C"
    SIZE_51_200 = "D"
    SIZE_201_500 = "E"
    SIZE_501_1000 = "F"
    SIZE_1001_5000 = "G"
    SIZE_5001_10000 = "H"
    SIZE_10001_PLUS = "I"


class CourseLevel(StrEnum):
    BEGINNER = "Beginner"
    INTERMEDIATE = "Intermediate"
    ADVANCED = "Advanced"


class CourseLength(StrEnum):
    UNDER_10_MINUTES = "< 10 mins"
    MINUTES_10_30 = "10 - 30 mins"
    MINUTES_30_60 = "30 - 60 mins"
    HOURS_1_2 = "1 - 2 hours"
    HOURS_2_3 = "2 - 3 hours"
    OVER_3_HOURS = "3+ hours"


@dataclass(frozen=True, slots=True)
class PeopleFilters:
    """People search filters; `first_name` to `school` are the free-text keyword filters."""

    network: Sequence[Network] = ()
    locations: Sequence[str] = ()
    current_companies: Sequence[str] = ()
    past_companies: Sequence[str] = ()
    schools: Sequence[str] = ()
    industries: Sequence[str] = ()
    profile_languages: Sequence[str] = ()  # language codes: en, fr, ... ("_o" = others)
    service_categories: Sequence[str] = ()
    connection_of: str | None = None  # profile ID or URN
    follower_of: str | None = None  # profile ID or URN
    open_to_volunteer: bool = False
    first_name: str | None = None
    last_name: str | None = None
    title: str | None = None
    company: str | None = None
    school: str | None = None
    extra: Mapping[str, Sequence[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.params()

    def params(self) -> Params:
        return merge(
            {
                "network": choices(Network, "network", self.network),
                "geoUrn": ids("locations", self.locations),
                "currentCompany": ids("current_companies", self.current_companies),
                "pastCompany": ids("past_companies", self.past_companies),
                "schoolFilter": ids("schools", self.schools),
                "industry": ids("industries", self.industries),
                "profileLanguage": ids("profile_languages", self.profile_languages),
                "serviceCategory": ids("service_categories", self.service_categories),
                "connectionOf": one_id("connection_of", self.connection_of),
                "followerOf": one_id("follower_of", self.follower_of),
                "openToVolunteer": flag("open_to_volunteer", self.open_to_volunteer),
                "firstName": phrase("first_name", self.first_name),
                "lastName": phrase("last_name", self.last_name),
                "title": phrase("title", self.title),
                "company": phrase("company", self.company),
                "schoolFreetext": phrase("school", self.school),
            },
            self.extra,
        )


@dataclass(frozen=True, slots=True)
class PostFilters:
    """Post (content) search filters; member fields take profile IDs, company fields IDs."""

    sort_by: PostSort | None = None
    date_posted: DatePosted | None = None
    content_type: ContentType | None = None
    posted_by: Sequence[PostedBy] = ()
    from_members: Sequence[str] = ()
    from_companies: Sequence[str] = ()
    mentions_members: Sequence[str] = ()
    mentions_companies: Sequence[str] = ()
    author_industries: Sequence[str] = ()
    author_companies: Sequence[str] = ()
    author_title: str | None = None
    extra: Mapping[str, Sequence[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.params()

    def params(self) -> Params:
        return merge(
            {
                "sortBy": choices(PostSort, "sort_by", optional(self.sort_by)),
                "datePosted": choices(DatePosted, "date_posted", optional(self.date_posted)),
                "contentType": choices(ContentType, "content_type", optional(self.content_type)),
                "postedBy": choices(PostedBy, "posted_by", self.posted_by),
                "fromMember": ids("from_members", self.from_members),
                "fromOrganization": ids("from_companies", self.from_companies),
                "mentionsMember": ids("mentions_members", self.mentions_members),
                "mentionsOrganization": ids("mentions_companies", self.mentions_companies),
                "authorIndustry": ids("author_industries", self.author_industries),
                "authorCompany": ids("author_companies", self.author_companies),
                "authorJobTitle": phrase("author_title", self.author_title),
            },
            self.extra,
        )


@dataclass(frozen=True, slots=True)
class CompanyFilters:
    """Company search filters; `locations` are headquarters geo IDs."""

    locations: Sequence[str] = ()
    industries: Sequence[str] = ()
    sizes: Sequence[CompanySize] = ()
    has_jobs: bool = False
    network: Sequence[Network] = ()
    extra: Mapping[str, Sequence[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.params()

    def params(self) -> Params:
        return merge(
            {
                "companyHqGeo": ids("locations", self.locations),
                "industryCompanyVertical": ids("industries", self.industries),
                "companySize": choices(CompanySize, "sizes", self.sizes),
                "hasJobs": ["1"] if flag("has_jobs", self.has_jobs) else [],
                "network": choices(Network, "network", self.network),
            },
            self.extra,
        )


@dataclass(frozen=True, slots=True)
class ServiceFilters:
    """Service provider search filters."""

    service_categories: Sequence[str] = ()
    locations: Sequence[str] = ()
    network: Sequence[Network] = ()
    profile_languages: Sequence[str] = ()
    extra: Mapping[str, Sequence[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.params()

    def params(self) -> Params:
        return merge(
            {
                "serviceCategory": ids("service_categories", self.service_categories),
                "geoUrn": ids("locations", self.locations),
                "network": choices(Network, "network", self.network),
                "profileLanguage": ids("profile_languages", self.profile_languages),
            },
            self.extra,
        )


@dataclass(frozen=True, slots=True)
class ProductFilters:
    """Product search filters; categories come from the PRODUCT_CATEGORY typeahead."""

    categories: Sequence[str] = ()
    companies: Sequence[str] = ()
    free_plan: bool = False
    extra: Mapping[str, Sequence[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.params()

    def params(self) -> Params:
        return merge(
            {
                "productCategory": ids("categories", self.categories),
                "productCompany": ids("companies", self.companies),
                "productFreePlan": flag("free_plan", self.free_plan),
            },
            self.extra,
        )


@dataclass(frozen=True, slots=True)
class CourseFilters:
    """LinkedIn Learning course filters; `software`, `topics` and `education_units` take the
    values `Search.filters(Vertical.COURSES, ...)` lists (software names, topic IDs, CPE...)."""

    levels: Sequence[CourseLevel] = ()
    lengths: Sequence[CourseLength] = ()
    software: Sequence[str] = ()
    topics: Sequence[str] = ()
    education_units: Sequence[str] = ()
    extra: Mapping[str, Sequence[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.params()

    def params(self) -> Params:
        return merge(
            {
                "difficultyLevel": choices(CourseLevel, "levels", self.levels),
                "timeToComplete": choices(CourseLength, "lengths", self.lengths),
                "softwareNames": phrases("software", self.software),
                "categoryIds": ids("topics", self.topics),
                "continuingEducationUnits": phrases("education_units", self.education_units),
            },
            self.extra,
        )


def merge(typed: Params, extra: Mapping[str, Sequence[str]]) -> Params:
    """Drop empty filters and add validated raw keys."""
    found = {key: values for key, values in typed.items() if values}
    if not isinstance(extra, Mapping):
        raise ValueError("extra maps query keys to lists of values.")
    for key, values in extra.items():
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", key):
            raise ValueError("extra keys are query parameter names such as seniorityV2.")
        if key in typed or key in ("resultType", "keywords"):
            raise ValueError(f"extra cannot set {key}; use its typed field or argument.")
        found[key] = phrases(f"extra[{key}]", values)
    return {key: values for key, values in found.items() if values}


def ids(name: str, values: Sequence[str]) -> list[str]:
    return [identifier(name, value) for value in sequence(name, values)]


def one_id(name: str, value: str | None) -> list[str]:
    return [] if value is None else [identifier(name, value)]


def identifier(name: str, value: object) -> str:
    """An ID, or the last part of a simple URN such as urn:li:fsd_geo:103644278."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} takes IDs or URNs as nonempty strings.")
    value = value.strip()
    if value.startswith("urn:li:"):
        if "(" in value:
            raise ValueError(f"{name} takes simple URNs, not compound ones.")
        value = value.rsplit(":", 1)[1]
    if not value or any(char.isspace() for char in value):
        raise ValueError(f"{name} takes IDs without spaces.")
    return value


def choices(kind: type[StrEnum], name: str, values: Sequence[StrEnum | str]) -> list[str]:
    try:
        return [kind(value).value for value in sequence(name, values)]
    except ValueError:
        options = ", ".join(member.name for member in kind)
        raise ValueError(f"{name} takes {kind.__name__} values: {options}.") from None


def optional(value: StrEnum | str | None) -> tuple[StrEnum | str, ...]:
    return () if value is None else (value,)


def phrase(name: str, value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonempty text.")
    return [value.strip()]


def phrases(name: str, values: Sequence[str]) -> list[str]:
    return [item for value in sequence(name, values) for item in phrase(name, value)]


def flag(name: str, value: bool) -> list[str]:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be True or False.")
    return ["true"] if value else []


def sequence(name: str, values: object) -> Sequence[Any]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError(f"{name} takes a list of values, not a single string.")
    return values
