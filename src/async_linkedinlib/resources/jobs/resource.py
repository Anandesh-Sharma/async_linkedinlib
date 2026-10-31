"""Job details, saved jobs, the job tracker and Easy Apply through the app's Voyager calls.

- `get`: the posting record (`voyagerJobsDashJobPostings/<urn>`) plus the job details top
  card and description (`JobPostingDetailSectionsByCardSectionTypesV2`, cards TOP_CARD_V2
  and JOB_DESCRIPTION_CARD, as the job details screen asks).
- `save`/`unsave`: a `{"patch": {"$set": {"saved": ...}}}` on the job's save state
  (`voyagerFeedDashSaveStates/urn:li:fsd_saveState:(SAVE,<job urn>)`), as SaveJobManager.
- `tracked`: the "My jobs" tracker, `SearchClusterCollection` with intent
  SEARCH_MY_ITEMS_JOB_SEEKER and a `cardType` filter.
- `application`/`upload_file`/`submission`/`submit`: the Easy Apply steps of
  JobApplyRepositoryImpl. Only `submit` applies, and it is sent once.
"""

import os
import re
from collections.abc import Mapping

from ...exceptions import ProtocolError
from ...models._json import dig
from ...models._json import integer
from ...models._json import items
from ...models._json import obj
from ...models._json import string
from ...models.jobs import Job
from ...models.jobs import TrackedJob
from ...models.jobs import TrackedStatus
from ...models.jobs_apply import ApplicationForm
from ...models.jobs_apply import ApplicationStatus
from ...models.jobs_apply import Submission
from ...models.jobs_apply import UploadedFile
from ...models.pagination import Cursor
from ...models.pagination import Page
from ...transport.voyager import GraphQLQuery
from ...transport.voyager import Voyager
from .. import paging
from ..search.queries import CLUSTERS
from . import answers as answer_rules
from . import upload as uploads
from .answers import Answer
from .answers import FileAnswer

POSTINGS = "voyagerJobsDashJobPostings"
SAVE_STATES = "voyagerFeedDashSaveStates"
ONSITE_APPLY = "voyagerJobsDashOnsiteApplyApplication"
DETAIL_SECTIONS = GraphQLQuery(
    "voyagerJobsDashJobPostingDetailSections.65c973ecf268b881b304305978de9fed",
    "JobPostingDetailSectionsByCardSectionTypesV2",
)
APPLICATION = GraphQLQuery(
    "voyagerJobsDashOnsiteApplyApplication.3a3ede1703d12540cf2e7e4bd04a3bbd",
    "JobsOnsiteApplyApplicationByJobPosting",
)
# The cards the job details screen requests first: header, apply state and description.
DETAIL_CARDS = ("TOP_CARD_V2", "JOB_DESCRIPTION_CARD")
TRACKER_INTENT = "SEARCH_MY_ITEMS_JOB_SEEKER"

_JOB = re.compile(
    r"(?:urn:li:(?:fsd_jobPosting|jobPosting|fs_normalized_jobPosting|fs_jobPosting):)?([0-9]+)"
)


class Jobs:
    """Read jobs, save them, and apply with Easy Apply in explicit steps."""

    def __init__(self, voyager: Voyager) -> None:
        self._voyager = voyager

    async def get(self, job: str) -> Job:
        """Read a job posting; HTTPError 404 when it does not exist."""
        job_id = job_id_of(job)
        urn = f"urn:li:fsd_jobPosting:{job_id}"
        posting = await self._voyager.get(f"{POSTINGS}/{urn}")
        sections = await self._voyager.query(
            DETAIL_SECTIONS,
            {"cardSectionTypes": list(DETAIL_CARDS), "jobPostingUrn": urn, "includeJobState": True},
        )
        found = obj(sections.get("jobsDashJobPostingDetailSectionsByCardSectionTypes"))
        if string(posting, "entityUrn") != urn or not found:
            raise ProtocolError("LinkedIn returned an unexpected job posting.")
        return Job.from_json(job_id, posting, found)

    async def save(self, job: str) -> None:
        """Save a job to the viewer's saved jobs."""
        await self._set_saved(job, True)

    async def unsave(self, job: str) -> None:
        """Remove a job from the viewer's saved jobs."""
        await self._set_saved(job, False)

    async def tracked(
        self,
        status: TrackedStatus = TrackedStatus.SAVED,
        *,
        count: int = 10,
        cursor: Cursor | None = None,
    ) -> Page[TrackedJob]:
        """Read one page of the viewer's saved, in-progress, applied or archived jobs."""
        status = TrackedStatus(status)
        if type(count) is not int or not 1 <= count <= 100:
            raise ValueError("count must be between 1 and 100.")
        scope = status.value
        start, token = paging.resume(cursor, "jobs.tracked", scope, self._voyager.owner)
        variables = {
            "query": {
                "flagshipSearchIntent": TRACKER_INTENT,
                "queryParameters": {"cardType": [status.value]},
            },
            "count": count,
            "paginationToken": token,
            "start": start,
        }
        data = await self._voyager.query(CLUSTERS, variables)
        clusters = paging.collection(data, "searchDashClustersByAll")
        results = [
            obj(dig(entry, "item", "entityResult"))
            for cluster in items(clusters.get("elements"))
            for entry in items(cluster.get("items"))
        ]
        total = integer(clusters, "paging", "total")
        if total is None:
            total = integer(clusters, "metadata", "totalResultCount")
        return paging.page(
            clusters,
            TrackedJob.from_result,
            "jobs.tracked",
            scope,
            start,
            count,
            self._voyager.owner,
            elements=results,
            total=total,
        )

    async def application(self, job: str) -> ApplicationForm:
        """Read a job's Easy Apply form; OperationRejected for jobs without Easy Apply."""
        job_id = job_id_of(job)
        data = await self._voyager.query(
            APPLICATION, {"jobPostingUrn": f"urn:li:fsd_jobPosting:{job_id}"}
        )
        found = items(dig(data, "jobsDashOnsiteApplyApplicationByJobPosting", "elements"))
        if not found:
            raise ProtocolError("LinkedIn returned no Easy Apply form for this job.")
        return ApplicationForm.from_json(job_id, found[0])

    async def upload_file(
        self,
        file: str | os.PathLike[str] | bytes,
        *,
        filename: str | None = None,
        max_size: int | None = None,
    ) -> UploadedFile:
        """Store a .pdf, .doc or .docx resume or cover letter for a submission to name.

        The upload applies to nothing by itself and LinkedIn offers no way to delete it, so
        pass the slot's limit (`form.file("Resume").max_size`) to refuse a file before it is
        stored.
        """
        return await uploads.upload(self._voyager, file, filename, max_size)

    def submission(
        self,
        form: ApplicationForm,
        answers: Mapping[str, Answer],
        *,
        files: Mapping[str, FileAnswer] | None = None,
        follow_company: bool = False,
        job: Job | None = None,
    ) -> Submission:
        """Check answers against the form and build the submission; nothing is sent.

        Keys are question URNs or labels. Text questions take strings, number questions
        numbers, choice questions an option label (checkboxes a list of labels). Unanswered
        questions keep LinkedIn's prefill. `files` maps file slots (URN, label or section
        such as RESUME) to an UploadedFile, a Resume or a resume URN. Pass the `Job` from
        `get` to send its tracking values like the app. The app's follow-company box
        starts checked; here following is off unless asked for.
        """
        if job is not None and job.id != form.job_id:
            raise ValueError("The job and the form belong to different jobs.")
        return answer_rules.build(
            form,
            answers,
            files,
            follow_company=follow_company,
            reference_id=job.reference_id if job else None,
            tracking_id=job.tracking_id if job else None,
        )

    async def submit(self, submission: Submission) -> ApplicationStatus:
        """Submit the application once; a timeout leaves the outcome unknown."""
        if not isinstance(submission, Submission):
            raise ValueError("Build the submission with Jobs.submission first.")
        job_id_of(submission.job_id)
        reply = await self._voyager.post(
            ONSITE_APPLY, submission.body, {"action": "submitApplication"}
        )
        return ApplicationStatus.from_json(obj(reply.data.get("value")))

    async def _set_saved(self, job: str, saved: bool) -> None:
        urn = f"urn:li:fsd_jobPosting:{job_id_of(job)}"
        await self._voyager.post(
            f"{SAVE_STATES}/urn:li:fsd_saveState:(SAVE,{urn})",
            {"patch": {"$set": {"saved": saved}}},
        )


def job_id_of(job: str) -> str:
    """The numeric job ID from an ID or a job posting URN."""
    found = _JOB.fullmatch(job) if isinstance(job, str) else None
    if not found:
        raise ValueError("A job ID or urn:li:fsd_jobPosting:<id> is required.")
    return found[1]
