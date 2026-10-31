"""Job search filters and job cards from the app's job search results.

Job details and applying belong to the jobs feature: pass `JobResult.id` to it.
"""

from collections.abc import Mapping
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from enum import StrEnum
from typing import Any

from ._json import boolean
from ._json import dig
from ._json import epoch_ms
from ._json import integer
from ._json import items
from ._json import obj
from ._json import string
from ._json import text
from ._json import urn_id
from .jobs import WORKPLACE_IDS
from .jobs import WorkplaceType
from .search_filters import Params
from .search_filters import choices
from .search_filters import flag
from .search_filters import identifier
from .search_filters import ids
from .search_filters import merge
from .search_filters import optional


class JobSort(StrEnum):
    MOST_RELEVANT = "R"
    MOST_RECENT = "DD"


class JobDatePosted(StrEnum):
    PAST_24_HOURS = "r86400"
    PAST_WEEK = "r604800"
    PAST_MONTH = "r2592000"


class ExperienceLevel(StrEnum):
    INTERNSHIP = "1"
    ENTRY = "2"
    ASSOCIATE = "3"
    MID_SENIOR = "4"
    DIRECTOR = "5"
    EXECUTIVE = "6"


class JobType(StrEnum):
    FULL_TIME = "F"
    PART_TIME = "P"
    CONTRACT = "C"
    TEMPORARY = "T"
    VOLUNTEER = "V"
    INTERNSHIP = "I"
    OTHER = "O"


class Commitment(StrEnum):
    """Employer commitments the app lets job seekers filter by."""

    DIVERSITY = "1"
    SUSTAINABILITY = "2"
    WORK_LIFE_BALANCE = "3"
    SOCIAL_IMPACT = "4"
    CAREER_GROWTH = "5"


DISTANCES = (0, 5, 10, 25, 50, 100)


@dataclass(frozen=True, slots=True)
class JobFilters:
    """Job search filters.

    `location` is a geo ID or URN (GEO typeahead); `distance` is miles from it (0, 5, 10,
    25, 50 or 100) and `places` narrows to populated places inside it. `salary` is the
    app's bucket index from `Search.job_filters()` (in the US 1 = $40,000+ ... 9 = $200,000+).
    `functions` take codes such as "eng"; `titles` and `companies` take IDs.
    """

    location: str | None = None
    sort_by: JobSort | None = None
    date_posted: JobDatePosted | None = None
    easy_apply: bool = False
    under_10_applicants: bool = False
    in_my_network: bool = False
    verified: bool = False
    workplace: Sequence[WorkplaceType] = ()
    experience: Sequence[ExperienceLevel] = ()
    job_types: Sequence[JobType] = ()
    companies: Sequence[str] = ()
    places: Sequence[str] = ()
    distance: int | None = None
    salary: int | None = None
    industries: Sequence[str] = ()
    functions: Sequence[str] = ()
    titles: Sequence[str] = ()
    commitments: Sequence[Commitment] = ()
    extra: Mapping[str, Sequence[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.params()
        self.geo_urn()

    def geo_urn(self) -> str | None:
        """The location as the `urn:li:fsd_geo:<id>` the job query takes."""
        if self.location is None:
            return None
        return "urn:li:fsd_geo:" + identifier("location", self.location)

    def params(self) -> Params:
        if self.distance is not None and (
            type(self.distance) is not int or self.distance not in DISTANCES
        ):
            raise ValueError("distance must be one of 0, 5, 10, 25, 50 or 100 miles.")
        if self.salary is not None and (type(self.salary) is not int or not 1 <= self.salary <= 9):
            raise ValueError("salary must be a bucket index from 1 to 9.")
        return merge(
            {
                "sortBy": choices(JobSort, "sort_by", optional(self.sort_by)),
                "timePostedRange": choices(
                    JobDatePosted, "date_posted", optional(self.date_posted)
                ),
                "applyWithLinkedin": flag("easy_apply", self.easy_apply),
                "earlyApplicant": flag("under_10_applicants", self.under_10_applicants),
                "jobInYourNetwork": flag("in_my_network", self.in_my_network),
                "verifiedJob": flag("verified", self.verified),
                "workplaceType": [
                    WORKPLACE_IDS[WorkplaceType(kind)]
                    for kind in choices(WorkplaceType, "workplace", self.workplace)
                ],
                "experience": choices(ExperienceLevel, "experience", self.experience),
                "jobType": choices(JobType, "job_types", self.job_types),
                "company": ids("companies", self.companies),
                "populatedPlace": ids("places", self.places),
                "distance": [] if self.distance is None else [str(self.distance)],
                "salaryBucketV2": [] if self.salary is None else [str(self.salary)],
                "industry": ids("industries", self.industries),
                "function": ids("functions", self.functions),
                "title": ids("titles", self.titles),
                "commitments": choices(Commitment, "commitments", self.commitments),
            },
            self.extra,
        )


@dataclass(frozen=True, slots=True)
class JobResult:
    """One job card from job search.

    `id` is the job posting ID for the jobs feature; `urn` is `urn:li:fsd_jobPosting:<id>`.
    `easy_apply`, `promoted` and `verified` mirror the labels the card shows. `states` are
    the viewer's states for the job (SAVED, APPLIED, VIEWED, APPLICATION_IN_PROGRESS).
    """

    id: str
    urn: str
    title: str | None
    company: str | None
    company_urn: str | None
    location: str | None
    listed_at: datetime | None
    easy_apply: bool
    promoted: bool
    verified: bool
    reposted: bool | None = None
    applicants: str | None = None
    insight: str | None = None
    states: tuple[str, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_card(cls, card: dict[str, Any]) -> "JobResult | None":
        """Build from a `JobCard`; None for cards that are not job postings."""
        posting_card = obj(card.get("jobPostingCard"))
        posting = obj(posting_card.get("jobPosting"))
        urn = string(posting, "entityUrn")
        job_id = urn_id(urn)
        if not urn or not job_id:
            return None
        footers = {
            string(footer, "type"): footer for footer in items(posting_card.get("footerItems"))
        }
        listed = integer(footers.get("LISTED_DATE"), "timeAt")
        logo = items(dig(posting_card, "logo", "attributes"))
        states = (
            string(action, "jobSeekerJobStateEnums")
            for action in items(dig(posting_card, "jobSeekerJobState", "jobSeekerJobStateActions"))
        )
        return cls(
            id=job_id,
            urn=urn,
            title=string(posting_card, "jobPostingTitle") or string(posting, "title"),
            company=text(posting_card, "primaryDescription"),
            company_urn=string(logo[0], "detailData", "companyLogo", "entityUrn") if logo else None,
            location=text(posting_card, "secondaryDescription"),
            listed_at=epoch_ms(listed),
            easy_apply="EASY_APPLY_TEXT" in footers,
            promoted="PROMOTED" in footers,
            verified=bool(dig(posting_card, "jobPostingVerification", "badge")),
            reposted=boolean(posting, "repostedJob"),
            applicants=text(footers.get("APPLICANT_COUNT_TEXT"), "text"),
            insight=text(posting_card, "relevanceInsight", "text"),
            states=tuple(state for state in states if state),
            raw=deepcopy(card),
        )
