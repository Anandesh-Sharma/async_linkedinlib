from datetime import UTC
from datetime import datetime

import pytest

from async_linkedinlib import ProtocolError
from async_linkedinlib.models.jobs import WorkplaceType
from async_linkedinlib.models.search_jobs import Commitment
from async_linkedinlib.models.search_jobs import ExperienceLevel
from async_linkedinlib.models.search_jobs import JobDatePosted
from async_linkedinlib.models.search_jobs import JobFilters
from async_linkedinlib.models.search_jobs import JobSort
from async_linkedinlib.models.search_jobs import JobType
from async_linkedinlib.resources.search.queries import JOB_CARDS
from async_linkedinlib.resources.search.queries import JOB_FILTERS


def job_card(job_id="5001", *, easy_apply=True, state=None):
    footers = [{"type": "LISTED_DATE", "timeAt": 1700000000000, "text": None}]
    if easy_apply:
        footers.append({"type": "EASY_APPLY_TEXT", "text": {"text": "Easy Apply"}})
    footers.append({"type": "APPLICANT_COUNT_TEXT", "text": {"text": "Be an early applicant"}})
    return {
        "jobCard": {
            "jobPostingCard": {
                "entityUrn": f"urn:li:fsd_jobPostingCard:({job_id},JOBS_SEARCH)",
                "jobPostingTitle": "Synthetic Engineer",
                "primaryDescription": {"text": "Example Co"},
                "secondaryDescription": {"text": "Testville (Remote)"},
                "jobPosting": {
                    "entityUrn": f"urn:li:fsd_jobPosting:{job_id}",
                    "title": "Synthetic Engineer",
                    "repostedJob": False,
                },
                "logo": {
                    "attributes": [
                        {"detailData": {"companyLogo": {"entityUrn": "urn:li:fsd_company:2001"}}}
                    ]
                },
                "footerItems": footers,
                "jobPostingVerification": {"badge": {"attributes": []}},
                "relevanceInsight": {"text": {"text": "Fits your preferences"}},
                "jobSeekerJobState": {
                    "jobSeekerJobStateActions": (
                        [{"jobSeekerJobStateEnums": state}] if state else []
                    )
                },
            }
        }
    }


def job_reply(*cards, start=0, count=25, total=30):
    return {
        "data": {
            "jobsDashJobCardsByJobSearch": {
                "metadata": {"origin": "JOB_SEARCH_PAGE_JOB_FILTER"},
                "paging": {"start": start, "count": count, "total": total},
                "elements": list(cards),
            }
        }
    }


def test_job_filters_use_the_app_filter_keys():
    filters = JobFilters(
        location="urn:li:geo:9001",
        sort_by=JobSort.MOST_RECENT,
        date_posted=JobDatePosted.PAST_WEEK,
        easy_apply=True,
        under_10_applicants=True,
        in_my_network=True,
        verified=True,
        workplace=[WorkplaceType.REMOTE, WorkplaceType.HYBRID],
        experience=[ExperienceLevel.ENTRY],
        job_types=[JobType.FULL_TIME],
        companies=["2001"],
        places=["9002"],
        distance=25,
        salary=4,
        industries=["4"],
        functions=["eng"],
        titles=["9"],
        commitments=[Commitment.WORK_LIFE_BALANCE],
    )
    assert filters.geo_urn() == "urn:li:fsd_geo:9001"
    assert filters.params() == {
        "sortBy": ["DD"],
        "timePostedRange": ["r604800"],
        "applyWithLinkedin": ["true"],
        "earlyApplicant": ["true"],
        "jobInYourNetwork": ["true"],
        "verifiedJob": ["true"],
        "workplaceType": ["2", "3"],
        "experience": ["2"],
        "jobType": ["F"],
        "company": ["2001"],
        "populatedPlace": ["9002"],
        "distance": ["25"],
        "salaryBucketV2": ["4"],
        "industry": ["4"],
        "function": ["eng"],
        "title": ["9"],
        "commitments": ["3"],
    }


@pytest.mark.parametrize(
    "build",
    [
        lambda: JobFilters(distance=7),
        lambda: JobFilters(distance=True),
        lambda: JobFilters(salary=0),
        lambda: JobFilters(salary=10),
        lambda: JobFilters(location=""),
        lambda: JobFilters(workplace=["remote"]),
        lambda: JobFilters(extra={"applyWithLinkedin": ["true"]}),
    ],
)
def test_invalid_job_filters_raise_value_error(build):
    with pytest.raises(ValueError):
        build()


async def test_jobs_send_the_job_search_query(api, payloads):
    client, search, seen = api(job_reply(job_card()))
    filters = JobFilters(location="9001", easy_apply=True, workplace=[WorkplaceType.ON_SITE])
    async with client:
        page = await search.jobs("python developer", filters, count=10)
    sent = payloads.sent(seen[0])
    assert (sent.query_id, sent.name) == (JOB_CARDS.id, JOB_CARDS.name)
    assert sent.variables == {
        "query": {
            "origin": "JOB_SEARCH_PAGE_JOB_FILTER",
            "keywords": "python developer",
            "locationUnion": {"geoUrn": "urn:li:fsd_geo:9001"},
            "selectedFilters": {"applyWithLinkedin": ["true"], "workplaceType": ["1"]},
            "spellCorrectionEnabled": "true",
        },
        "count": "10",
        "start": "0",
        "includeJobState": "true",
    }
    assert page.total == 30
    assert page.next is not None and page.next.start == 25


async def test_job_search_without_filters_uses_the_search_button_origin(api, payloads):
    client, search, seen = api(job_reply())
    async with client:
        page = await search.jobs()
    query = payloads.sent(seen[0]).variables["query"]
    assert query == {"origin": "JOB_SEARCH_PAGE_SEARCH_BUTTON", "spellCorrectionEnabled": "true"}
    assert page.items == () and page.next is None


async def test_job_cards_keep_ids_for_the_jobs_feature(api):
    client, search, _ = api(job_reply(job_card(state="SAVED"), job_card("5002", easy_apply=False)))
    async with client:
        page = await search.jobs("engineer")
    job, other = page.items
    assert (job.id, job.urn) == ("5001", "urn:li:fsd_jobPosting:5001")
    assert (job.title, job.company, job.company_urn, job.location) == (
        "Synthetic Engineer",
        "Example Co",
        "urn:li:fsd_company:2001",
        "Testville (Remote)",
    )
    assert job.listed_at == datetime.fromtimestamp(1700000000, UTC)
    assert (job.easy_apply, job.promoted, job.verified, job.reposted) == (True, False, True, False)
    assert job.applicants == "Be an early applicant"
    assert job.insight == "Fits your preferences"
    assert job.states == ("SAVED",)
    assert other.easy_apply is False and other.states == ()


async def test_job_cursor_continues_only_the_same_job_query(api, payloads):
    client, search, seen = api(job_reply(job_card()), job_reply(job_card("5002"), start=25))
    async with client:
        page = await search.jobs("engineer", JobFilters(location="9001"))
        with pytest.raises(ValueError, match="different operation or query"):
            await search.jobs("engineer", JobFilters(location="9002"), cursor=page.next)
        with pytest.raises(ValueError, match="different operation or query"):
            await search.people("engineer", cursor=page.next)
        later = await search.jobs("engineer", JobFilters(location="9001"), cursor=page.next)
    assert payloads.sent(seen[1]).variables["start"] == "25"
    assert later.items[0].id == "5002"
    assert later.next is None


async def test_job_filter_discovery_uses_the_job_query(api, payloads):
    reply = {
        "data": {
            "jobsDashSearchFilterClustersResourceByFilters": {
                "elements": [
                    {
                        "secondaryFilterGroups": [
                            {
                                "filters": [
                                    {"parameterName": "placeholder_upsell", "upsellSlot": {"x": 1}}
                                ]
                            },
                            {
                                "filters": [
                                    {
                                        "parameterName": "salaryBucketV2",
                                        "renderType": "SINGLE_SELECT",
                                        "displayName": {"text": "Salary"},
                                        "secondaryFilterValues": [
                                            {"value": "1", "displayName": "$40,000+"}
                                        ],
                                    }
                                ]
                            },
                        ]
                    }
                ]
            }
        }
    }
    client, search, seen = api(reply)
    async with client:
        found = await search.job_filters("engineer", JobFilters(location="9001"))
    sent = payloads.sent(seen[0])
    assert (sent.query_id, sent.name) == (JOB_FILTERS.id, JOB_FILTERS.name)
    assert sent.variables["query"]["locationUnion"] == {"geoUrn": "urn:li:fsd_geo:9001"}
    assert [(item.key, item.options[0].label) for item in found] == [("salaryBucketV2", "$40,000+")]


async def test_job_reply_without_cards_is_a_protocol_error(api):
    client, search, _ = api({"data": {"jobsDashJobCardsByJobSearch": {"paging": {}}}})
    async with client:
        with pytest.raises(ProtocolError):
            await search.jobs("engineer")
