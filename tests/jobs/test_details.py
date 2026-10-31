import json
from datetime import UTC
from datetime import datetime
from urllib.parse import parse_qs

import httpx
import pytest

from async_linkedinlib import HTTPError
from async_linkedinlib import ProtocolError
from async_linkedinlib.exceptions import OperationRejected
from async_linkedinlib.models.jobs import TrackedStatus
from async_linkedinlib.models.jobs import WorkplaceType
from async_linkedinlib.models.pagination import Cursor
from async_linkedinlib.transport.restli import encode

JOB_ID = "1234567890"
JOB_URN = f"urn:li:fsd_jobPosting:{JOB_ID}"
LISTED = 1700000000000

POSTING = {
    "entityUrn": JOB_URN,
    "title": "Line Cook",
    "companyDetails": {"name": "Example Foods", "companyUrn": "urn:li:fsd_company:42"},
    "locationUrn": "urn:li:fsd_geo:7",
    "workplaceTypes": ["urn:li:fsd_workplaceType:3"],
    "employmentStatusUrn": "urn:li:fsd_employmentStatus:PART_TIME",
    "description": {"text": "Posting description"},
    "listedAt": LISTED,
    "numApplies": 12,
    "jobState": "LISTED",
    "jobPostingUrl": f"https://www.linkedin.com/jobs/view/{JOB_ID}/",
}
LINE = "Testville, Region · 3 days ago · 12 applicants"
SUBTITLE = LINE + "Promoted · Responses managed"
AGO = LINE.index("3 days ago")
SECTIONS = {
    "elements": [
        {
            "jobPostingDetailSection": [
                {
                    "topCardV2": {
                        "jobTrackingData": {"referenceId": "ref==", "trackingId": "track=="},
                        "jobPostingCard": {
                            "jobPostingTitle": "Line Cook",
                            "primaryDescription": {"text": "Example Foods"},
                            "tertiaryDescription": {
                                "text": SUBTITLE,
                                "attributesV2": [
                                    {"start": 0, "length": 17, "detailData": {}},
                                    {
                                        "start": AGO,
                                        "length": 10,
                                        "detailData": {
                                            "epoch": {"type": "TIME_AGO", "epochAt": LISTED}
                                        },
                                    },
                                    {
                                        "start": len(LINE),
                                        "length": len(SUBTITLE) - len(LINE),
                                        "detailData": {"style": "PARAGRAPH"},
                                    },
                                ],
                            },
                            "secondaryActionsV2ResolutionResults": [
                                {"saveJobAction": {"saveStateResolutionResult": {"saved": True}}}
                            ],
                            "primaryActionV2": {
                                "applyJobAction": {
                                    "applyJobActionResolutionResult": {
                                        "onsiteApply": True,
                                        "applied": True,
                                        "appliedAt": LISTED + 1000,
                                        "companyApplyUrl": f"https://www.linkedin.com/job-apply/{JOB_ID}",
                                    }
                                }
                            },
                        },
                    }
                }
            ]
        },
        {
            "jobPostingDetailSection": [
                {"jobDescription": {"jobPosting": {"description": {"text": "Full description"}}}}
            ]
        },
    ]
}


def graphql_reply(field, value):
    return httpx.Response(200, json={"data": {field: value}})


def details_handler(seen, posting=POSTING, sections=SECTIONS):
    def handle(request):
        seen.append(request)
        if request.url.path.startswith("/voyager/api/voyagerJobsDashJobPostings/"):
            return httpx.Response(200, json=posting)
        return graphql_reply("jobsDashJobPostingDetailSectionsByCardSectionTypes", sections)

    return handle


async def test_get_reads_the_posting_and_the_job_details_cards(make_jobs):
    seen = []
    client, jobs = make_jobs(details_handler(seen))
    async with client:
        job = await jobs.get(f"urn:li:jobPosting:{JOB_ID}")
    posting, cards = seen
    assert posting.method == "GET"
    assert posting.url.raw_path.decode() == f"/voyager/api/voyagerJobsDashJobPostings/{JOB_URN}"
    raw = cards.url.query.decode()
    variables = {
        "cardSectionTypes": ["TOP_CARD_V2", "JOB_DESCRIPTION_CARD"],
        "jobPostingUrn": JOB_URN,
        "includeJobState": True,
    }
    assert f"variables={encode(variables)}" in raw
    assert parse_qs(raw)["queryId"] == [
        "voyagerJobsDashJobPostingDetailSections.65c973ecf268b881b304305978de9fed"
    ]
    assert job.id == JOB_ID and job.urn == JOB_URN
    assert (job.title, job.company, job.company_urn) == (
        "Line Cook",
        "Example Foods",
        "urn:li:fsd_company:42",
    )
    assert job.location == "Testville, Region"
    assert job.location_urn == "urn:li:fsd_geo:7"
    assert job.workplace_types == (WorkplaceType.HYBRID,)
    assert job.employment_type == "PART_TIME"
    assert job.description == "Full description"
    assert job.listed_at == datetime.fromtimestamp(LISTED / 1000, UTC)
    assert (job.applicants, job.applicants_text) == (12, "12 applicants")
    assert (job.easy_apply, job.applied, job.saved, job.state) == (True, True, True, "LISTED")
    assert job.applied_at == datetime.fromtimestamp((LISTED + 1000) / 1000, UTC)
    assert job.apply_url == f"https://www.linkedin.com/job-apply/{JOB_ID}"
    assert (job.reference_id, job.tracking_id) == ("ref==", "track==")
    assert "track==" not in repr(job)


async def test_get_keeps_unknown_fields_absent(make_jobs):
    sparse = {"entityUrn": JOB_URN}
    client, jobs = make_jobs(details_handler([], sparse, {"elements": [{"x": 1}]}))
    async with client:
        job = await jobs.get(JOB_ID)
    assert job.title is None and job.location is None and job.listed_at is None
    assert job.workplace_types == () and job.easy_apply is None and job.saved is None


async def test_get_reports_a_missing_job(make_jobs):
    client, jobs = make_jobs(lambda request: httpx.Response(404, json={"status": 404}))
    async with client:
        with pytest.raises(HTTPError) as error:
            await jobs.get(JOB_ID)
    assert error.value.status_code == 404


async def test_get_rejects_another_posting_and_graphql_errors(make_jobs):
    other = dict(POSTING, entityUrn="urn:li:fsd_jobPosting:1")
    client, jobs = make_jobs(details_handler([], other))
    async with client:
        with pytest.raises(ProtocolError):
            await jobs.get(JOB_ID)

    def failing(request):
        if "graphql" in request.url.path:
            return httpx.Response(200, json={"data": None, "errors": [{"message": "boom"}]})
        return httpx.Response(200, json=POSTING)

    client, jobs = make_jobs(failing)
    async with client:
        with pytest.raises(OperationRejected):
            await jobs.get(JOB_ID)


@pytest.mark.parametrize("bad", ["", "abc", "urn:li:activity:1", "12 3", None])
async def test_job_ids_are_validated(make_jobs, bad):
    client, jobs = make_jobs(lambda request: pytest.fail("no request expected"))
    async with client:
        with pytest.raises(ValueError):
            await jobs.get(bad)


@pytest.mark.parametrize(("method", "saved"), [("save", True), ("unsave", False)])
async def test_save_and_unsave_patch_the_job_save_state(make_jobs, method, saved):
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(204)

    client, jobs = make_jobs(handle)
    async with client:
        assert await getattr(jobs, method)(JOB_URN) is None
    request = seen[0]
    assert request.method == "POST"
    assert request.url.raw_path.decode() == (
        f"/voyager/api/voyagerFeedDashSaveStates/urn:li:fsd_saveState:(SAVE,{JOB_URN})"
    )
    assert json.loads(request.content) == {"patch": {"$set": {"saved": saved}}}


def tracker_reply(job_ids, total):
    results = [
        {
            "item": {
                "entityResult": {
                    "trackingUrn": f"urn:li:fsd_jobPosting:{job_id}",
                    "title": {"text": f"Job {job_id}"},
                    "primarySubtitle": {"text": "Example Foods"},
                    "secondarySubtitle": {"text": "Testville (On-site)"},
                    "insightsResolutionResults": [
                        {"simpleInsight": {"title": {"text": "  Posted 1d ago"}}}
                    ],
                    "navigationUrl": f"https://www.linkedin.com/jobs/view/{job_id}/?refId=x",
                    "overflowActions": [
                        {
                            "searchActionType": "EASY_APPLY_TO_JOB",
                            "actionDetails": {"navigationAction": {}},
                        },
                        {
                            "searchActionType": "UNSAVE_JOB",
                            "actionDetails": {"saveAction": {"saved": True, "savedAt": LISTED}},
                        },
                    ],
                }
            }
        }
        for job_id in job_ids
    ]
    results.append({"item": {"entityResult": {"trackingUrn": "urn:li:fsd_company:1"}}})
    return {
        "metadata": {"totalResultCount": total},
        "paging": {"start": 0, "count": 2, "total": total},
        "elements": [{"items": results}],
    }


async def test_tracked_lists_one_page_and_continues_only_its_own_list(make_jobs):
    seen = []

    def handle(request):
        seen.append(request)
        return graphql_reply("searchDashClustersByAll", tracker_reply(["11", "12"], 3))

    client, jobs = make_jobs(handle)
    async with client:
        page = await jobs.tracked(TrackedStatus.APPLIED, count=2)
        with pytest.raises(ValueError):
            await jobs.tracked(TrackedStatus.SAVED, cursor=page.next)
        await jobs.tracked(TrackedStatus.APPLIED, count=2, cursor=page.next)
    first, second = seen
    query = {
        "flagshipSearchIntent": "SEARCH_MY_ITEMS_JOB_SEEKER",
        "queryParameters": {"cardType": ["APPLIED"]},
    }
    assert (
        f"variables={encode({'query': query, 'count': 2, 'start': 0})}" in first.url.query.decode()
    )
    assert (
        f"variables={encode({'query': query, 'count': 2, 'start': 2})}" in second.url.query.decode()
    )
    assert parse_qs(first.url.query.decode())["queryName"] == ["SearchClusterCollection"]
    assert page.total == 3 and page.next == Cursor("jobs.tracked", "APPLIED", 2)
    job = page.items[0]
    assert [item.id for item in page.items] == ["11", "12"]
    assert (job.title, job.company, job.location) == (
        "Job 11",
        "Example Foods",
        "Testville (On-site)",
    )
    assert job.insights == ("Posted 1d ago",)
    assert job.easy_apply is True and job.saved is True
    assert job.saved_at == datetime.fromtimestamp(LISTED / 1000, UTC)
    assert job.url == "https://www.linkedin.com/jobs/view/11/"


async def test_tracked_last_page_has_no_cursor_and_bad_input_fails(make_jobs):
    client, jobs = make_jobs(
        lambda request: graphql_reply("searchDashClustersByAll", tracker_reply(["11"], 1))
    )
    async with client:
        page = await jobs.tracked()
        assert page.next is None and page.total == 1
        with pytest.raises(ValueError):
            await jobs.tracked("FAVOURITES")
        with pytest.raises(ValueError):
            await jobs.tracked(count=0)

    client, jobs = make_jobs(lambda request: graphql_reply("searchDashClustersByAll", None))
    async with client:
        with pytest.raises(ProtocolError):
            await jobs.tracked()
