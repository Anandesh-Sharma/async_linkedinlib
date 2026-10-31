"""Job postings and the viewer's job tracker, as the Android job details screen reads them."""

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


class WorkplaceType(StrEnum):
    """Where the work happens (the app's `WorkplaceTypeEnum`)."""

    ON_SITE = "ON_SITE"
    REMOTE = "REMOTE"
    HYBRID = "HYBRID"


# `voyagerJobsDashWorkplaceTypes` lists these IDs for the three workplace types; job search
# filters take the same IDs.
WORKPLACE_IDS = {
    WorkplaceType.ON_SITE: "1",
    WorkplaceType.REMOTE: "2",
    WorkplaceType.HYBRID: "3",
}
_WORKPLACE_BY_ID = {number: kind for kind, number in WORKPLACE_IDS.items()}


class TrackedStatus(StrEnum):
    """The job tracker's lists (the "My jobs" `cardType` filter values)."""

    SAVED = "SAVED"
    IN_PROGRESS = "IN_PROGRESS"
    APPLIED = "APPLIED"
    ARCHIVED = "ARCHIVED"


@dataclass(frozen=True, slots=True)
class Job:
    """One job posting with the viewer's apply and save state.

    `location` and `applicants_text` are the text LinkedIn shows; `applicants` is the
    posting's apply count (for external jobs, the number of apply clicks). `apply_url` is
    the company's site, or LinkedIn's own apply page for Easy Apply jobs.
    `reference_id` and `tracking_id` are the job details tracking values the app sends
    back with an Easy Apply submission.
    """

    id: str
    urn: str
    title: str | None
    company: str | None
    company_urn: str | None
    location: str | None
    location_urn: str | None
    workplace_types: tuple[WorkplaceType, ...]
    employment_type: str | None
    description: str | None
    listed_at: datetime | None
    applicants: int | None
    applicants_text: str | None
    state: str | None
    easy_apply: bool | None
    apply_url: str | None
    applied: bool | None
    applied_at: datetime | None
    saved: bool | None
    url: str | None
    reference_id: str | None = field(default=None, repr=False)
    tracking_id: str | None = field(default=None, repr=False)
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_json(cls, job_id: str, posting: dict[str, Any], sections: dict[str, Any]) -> "Job":
        """Combine the posting record with the job details top card and description."""
        top = obj(_section(sections, "topCardV2"))
        card = obj(top.get("jobPostingCard"))
        apply = obj(
            dig(card, "primaryActionV2", "applyJobAction", "applyJobActionResolutionResult")
        )
        location, shown_at, applicants_text = _subtitle_parts(obj(card.get("tertiaryDescription")))
        workplace = [
            _WORKPLACE_BY_ID.get(urn_id(urn) or "")
            for urn in posting.get("workplaceTypes") or []
            if isinstance(urn, str)
        ]
        listed = integer(posting, "listedAt")
        return cls(
            id=job_id,
            urn=f"urn:li:fsd_jobPosting:{job_id}",
            title=string(posting, "title") or string(card, "jobPostingTitle"),
            company=string(posting, "companyDetails", "name") or text(card, "primaryDescription"),
            company_urn=string(posting, "companyDetails", "companyUrn")
            or string(card, "jobPosting", "companyDetails", "jobCompany", "company", "entityUrn"),
            location=location,
            location_urn=string(posting, "locationUrn"),
            workplace_types=tuple(kind for kind in workplace if kind is not None),
            employment_type=urn_id(string(posting, "employmentStatusUrn")),
            description=text(_section(sections, "jobDescription"), "jobPosting", "description")
            or text(posting, "description"),
            listed_at=epoch_ms(listed) if listed is not None else shown_at,
            applicants=integer(posting, "numApplies"),
            applicants_text=applicants_text,
            state=string(posting, "jobState"),
            easy_apply=boolean(apply, "onsiteApply"),
            apply_url=string(apply, "companyApplyUrl") or string(posting, "companyApplyUrl"),
            applied=boolean(apply, "applied"),
            applied_at=epoch_ms(integer(apply, "appliedAt")),
            saved=_saved(card),
            url=string(posting, "jobPostingUrl"),
            reference_id=string(top, "jobTrackingData", "referenceId"),
            tracking_id=string(top, "jobTrackingData", "trackingId"),
            raw={"posting": deepcopy(posting), "sections": deepcopy(sections)},
        )


@dataclass(frozen=True, slots=True)
class TrackedJob:
    """A job in one of the viewer's tracker lists (saved, in progress, applied, archived)."""

    id: str
    title: str | None
    company: str | None
    location: str | None
    insights: tuple[str, ...]
    easy_apply: bool
    saved: bool | None
    saved_at: datetime | None
    url: str | None
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_result(cls, result: dict[str, Any]) -> "TrackedJob | None":
        """Read a tracker `entityResult`; None when it is not a job posting."""
        tracking = string(result, "trackingUrn") or ""
        if not tracking.startswith("urn:li:fsd_jobPosting:"):
            return None
        actions = items(result.get("overflowActions"))
        saves = [obj(dig(a, "actionDetails", "saveAction")) for a in actions]
        save = next((found for found in saves if found), {})
        insights = [
            title.strip()
            for insight in items(result.get("insightsResolutionResults"))
            if (title := text(insight, "simpleInsight", "title"))
        ]
        url = string(result, "navigationUrl")
        return cls(
            id=tracking.rsplit(":", 1)[-1],
            title=text(result, "title"),
            company=text(result, "primarySubtitle"),
            location=text(result, "secondarySubtitle"),
            insights=tuple(insights),
            easy_apply=any(a.get("searchActionType") == "EASY_APPLY_TO_JOB" for a in actions),
            saved=boolean(save, "saved"),
            saved_at=epoch_ms(integer(save, "savedAt")),
            url=url.split("?", 1)[0] if url else None,
            raw=deepcopy(result),
        )


def _section(sections: dict[str, Any], name: str) -> Any:
    """The first detail section card with this name from the sections finder reply."""
    for element in items(sections.get("elements")):
        for section in items(element.get("jobPostingDetailSection")):
            if isinstance(section.get(name), dict):
                return section[name]
    return None


def _saved(card: dict[str, Any]) -> bool | None:
    for action in items(card.get("secondaryActionsV2ResolutionResults")):
        saved = boolean(action, "saveJobAction", "saveStateResolutionResult", "saved")
        if saved is not None:
            return saved
    return None


def _subtitle_parts(
    description: dict[str, Any],
) -> tuple[str | None, datetime | None, str | None]:
    """Split "Location · 15 hours ago · 1 applicant" around its time-ago span.

    The span carrying the posting time is marked by an `epoch` attribute; the location is
    the text before it and the applicant count the text after it, up to the next separator
    or the paragraph that follows on its own line.
    """
    value = string(description, "text")
    if not value:
        return None, None, None
    attributes = items(description.get("attributesV2"))
    epoch = next((a for a in attributes if dig(a, "detailData", "epoch")), None)
    if epoch is None:
        return value.split(" · ", 1)[0].strip() or None, None, None
    start, length = integer(epoch, "start") or 0, integer(epoch, "length") or 0
    paragraph = min(
        (
            integer(a, "start") or len(value)
            for a in attributes
            if dig(a, "detailData", "style") == "PARAGRAPH"
        ),
        default=len(value),
    )
    before = value[:start].rstrip(" ·").strip()
    after = value[start + length : paragraph].strip(" ·").split(" · ", 1)[0].strip()
    return before or None, epoch_ms(integer(epoch, "detailData", "epoch", "epochAt")), after or None
