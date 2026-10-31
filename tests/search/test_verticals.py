import pytest

from async_linkedinlib import HTTPError
from async_linkedinlib import ProtocolError
from async_linkedinlib.exceptions import OperationRejected
from async_linkedinlib.models.content import Post
from async_linkedinlib.models.pagination import Cursor
from async_linkedinlib.models.search import PersonResult
from async_linkedinlib.models.search import SearchResult
from async_linkedinlib.models.search_filters import CompanyFilters
from async_linkedinlib.models.search_filters import CompanySize
from async_linkedinlib.models.search_filters import DatePosted
from async_linkedinlib.models.search_filters import Network
from async_linkedinlib.models.search_filters import PeopleFilters
from async_linkedinlib.models.search_filters import PostFilters
from async_linkedinlib.models.search_filters import PostSort
from async_linkedinlib.resources.search.queries import CLUSTERS
from async_linkedinlib.transport import restli


async def test_people_sends_the_app_search_query_with_filters(api, payloads):
    client, search, seen = api(payloads.clusters([{"entityResult": payloads.person_entity()}]))
    filters = PeopleFilters(
        network=[Network.SECOND, Network.THIRD_PLUS],
        locations=["urn:li:fsd_geo:9001"],
        current_companies=["2001"],
        title="staff engineer",
    )
    async with client:
        page = await search.people("software  engineer", filters)
    request = seen[0]
    assert request.method == "GET"
    assert request.url.path == "/voyager/api/graphql"
    sent = payloads.sent(request)
    assert (sent.query_id, sent.name) == (CLUSTERS.id, CLUSTERS.name)
    assert sent.variables == {
        "start": "0",
        "count": "10",
        "origin": "FACETED_SEARCH",
        "query": {
            "flagshipSearchIntent": "SEARCH_SRP",
            "keywords": "software engineer",
            "queryParameters": {
                "resultType": ["PEOPLE"],
                "network": ["S", "O"],
                "geoUrn": ["9001"],
                "currentCompany": ["2001"],
                "title": ["staff engineer"],
            },
            "spellCorrectionEnabled": "true",
        },
    }
    raw = request.url.query.decode()
    assert "queryParameters:(resultType:List(PEOPLE),network:List(S,O)" in raw
    assert page.total == 12345


async def test_people_results_read_profile_fields(api, payloads):
    upsell = {"upsellSlot": {"slotUrn": "urn:li:fsd_upsellSlot:1"}}
    client, search, _ = api(
        payloads.clusters(
            [{"simpleTextV2": {"text": payloads.text("About 2 results")}}],
            [{"entityResult": payloads.person_entity()}, upsell],
            [{"feedbackCard": {}}],
        )
    )
    async with client:
        page = await search.people("ada")
    assert len(page.items) == 1
    person = page.items[0]
    assert isinstance(person, PersonResult)
    assert person.urn == payloads.PROFILE
    assert person.id == "ACoTestProfileOne"
    assert person.member_urn == "urn:li:member:1001"
    assert (person.name, person.headline, person.location) == (
        "Ada Example",
        "Engineer at Example Co",
        "Testville",
    )
    assert person.distance == "DISTANCE_2"
    assert person.public_id == "ada-example"
    assert person.url == "https://www.linkedin.com/in/ada-example"
    assert person.verified is True
    assert person.insights == ("3 mutual connections",)
    assert person.raw["trackingUrn"] == "urn:li:member:1001"


async def test_vertical_without_filters_switches_vertical_and_omits_empty_keywords(api, payloads):
    client, search, seen = api(payloads.clusters([]))
    async with client:
        await search.people()
    variables = payloads.sent(seen[0]).variables
    assert variables["origin"] == "SWITCH_SEARCH_VERTICAL"
    assert "keywords" not in variables["query"]
    assert variables["query"]["queryParameters"] == {"resultType": ["PEOPLE"]}


async def test_next_page_continues_with_start_and_token(api, payloads):
    first = payloads.clusters(
        [{"entityResult": payloads.person_entity()}], start=0, total=25, token="tok-1"
    )
    second = payloads.clusters(
        [{"entityResult": payloads.person_entity("urn:li:fsd_profile:ACoTestTwo")}],
        start=10,
        total=25,
    )
    client, search, seen = api(first, second)
    async with client:
        page = await search.people("ada")
        assert page.next is not None and page.next.start == 10
        later = await search.people("ada", cursor=page.next)
    variables = payloads.sent(seen[1]).variables
    assert variables["start"] == "10"
    assert variables["paginationToken"] == "tok-1"
    assert later.items[0].id == "ACoTestTwo"
    assert later.next is not None and later.next.start == 20


async def test_last_page_has_no_cursor(api, payloads):
    reply = payloads.clusters([{"entityResult": payloads.person_entity()}], start=90, total=100)
    client, search, _ = api(reply)
    async with client:
        page = await search.people("ada", cursor=Cursor("search.people", _scope("ada"), 90))
    assert page.next is None


def _scope(keywords):
    return restli.encode(
        {
            "flagshipSearchIntent": "SEARCH_SRP",
            "keywords": keywords,
            "queryParameters": {"resultType": ["PEOPLE"]},
            "spellCorrectionEnabled": True,
        }
    )


async def test_cursor_from_another_query_or_vertical_is_refused(api, payloads):
    reply = payloads.clusters([{"entityResult": payloads.person_entity()}], total=50)
    client, search, seen = api(reply)
    async with client:
        page = await search.people("ada")
        with pytest.raises(ValueError, match="different operation or query"):
            await search.people("grace", cursor=page.next)
        with pytest.raises(ValueError, match="different operation or query"):
            await search.people("ada", PeopleFilters(network=[Network.FIRST]), cursor=page.next)
        with pytest.raises(ValueError, match="different operation or query"):
            await search.companies("ada", cursor=page.next)
    assert len(seen) == 1


async def test_posts_reuse_the_feed_post_model_and_filters(api, payloads):
    video_update = payloads.update("urn:li:activity:3002")
    actor = video_update.pop("actor")
    video_update.pop("commentary")
    video_update["content"] = {
        "largeSingleVideoComponent": {"actor": actor, "commentary": payloads.text("A video")}
    }
    client, search, seen = api(
        payloads.clusters(
            [
                {"searchFeedUpdate": {"update": payloads.update()}},
                {"searchFeedUpdate": {"update": video_update}},
                {"searchFeedUpdate": {"update": {"metadata": {}}}},
            ]
        )
    )
    filters = PostFilters(
        sort_by=PostSort.LATEST,
        date_posted=DatePosted.PAST_WEEK,
        from_companies=["urn:li:organization:2001"],
    )
    async with client:
        page = await search.posts("ai", filters)
    query = payloads.sent(seen[0]).variables["query"]
    assert query["queryParameters"] == {
        "resultType": ["CONTENT"],
        "sortBy": ["date_posted"],
        "datePosted": ["past-week"],
        "fromOrganization": ["2001"],
    }
    assert [type(post) for post in page.items] == [Post, Post]
    first, video = page.items
    assert (first.urn, first.text, first.age) == ("urn:li:activity:3001", "Synthetic post", "2h")
    assert first.author is not None and first.author.urn == "urn:li:member:1001"
    assert (video.urn, video.text, video.content_type) == (
        "urn:li:activity:3002",
        "A video",
        "largeSingleVideo",
    )


async def test_companies_map_to_search_results(api, payloads):
    client, search, seen = api(payloads.clusters([{"entityResult": payloads.company_entity()}]))
    async with client:
        page = await search.companies(
            "example", CompanyFilters(sizes=[CompanySize.SIZE_11_50], has_jobs=True)
        )
    params = payloads.sent(seen[0]).variables["query"]["queryParameters"]
    assert params == {"resultType": ["COMPANIES"], "companySize": ["C"], "hasJobs": ["1"]}
    company = page.items[0]
    assert isinstance(company, SearchResult)
    assert (company.urn, company.id, company.kind) == ("urn:li:fsd_company:2001", "2001", "company")
    assert company.tracking_urn == "urn:li:company:2001"
    assert (company.title, company.subtitle, company.secondary_subtitle) == (
        "Example Co",
        "Software Development • Testville",
        "1K followers",
    )
    assert company.url == "https://www.linkedin.com/company/example-co/"


@pytest.mark.parametrize(
    ("method", "vertical"),
    [
        ("groups", "GROUPS"),
        ("schools", "SCHOOLS"),
        ("events", "EVENTS"),
        ("courses", "LEARNING"),
        ("products", "PRODUCTS"),
    ],
)
async def test_entity_verticals_send_their_result_type(api, payloads, method, vertical):
    client, search, seen = api(payloads.clusters([{"entityResult": payloads.company_entity()}]))
    async with client:
        page = await getattr(search, method)("python", count=3)
    variables = payloads.sent(seen[0]).variables
    assert variables["query"]["queryParameters"] == {"resultType": [vertical]}
    assert variables["count"] == "3"
    assert page.items[0].id == "2001"


async def test_services_return_people(api, payloads):
    client, search, seen = api(payloads.clusters([{"entityResult": payloads.person_entity()}]))
    async with client:
        page = await search.services("python")
    assert payloads.sent(seen[0]).variables["query"]["queryParameters"] == {
        "resultType": ["SERVICES"]
    }
    assert isinstance(page.items[0], PersonResult)


async def test_all_groups_blended_clusters(api, payloads):
    reply = payloads.clusters(
        [{"entityResult": payloads.person_entity()}],
        [{"searchFeedUpdate": {"update": payloads.update()}}],
        [{"entityResult": payloads.company_entity()}],
        [{"feedbackCard": {}}],
        titles=("People", "Posts", "Companies", None),
    )
    client, search, seen = api(reply)
    async with client:
        page = await search.all("python")
    variables = payloads.sent(seen[0]).variables
    assert variables["origin"] == "GLOBAL_SEARCH_HEADER"
    assert variables["query"]["queryParameters"] == {"resultType": ["ALL"]}
    assert [group.title for group in page.items] == ["People", "Posts", "Companies"]
    assert [type(group.items[0]) for group in page.items] == [PersonResult, Post, SearchResult]


async def test_graphql_errors_and_bad_replies_fail_clearly(api, payloads):
    client, search, _ = api(
        {"errors": [{"message": "Invalid query"}]},
        {"data": {"somethingElse": {}}},
        b"not json",
        (500, {"message": "boom"}),
    )
    async with client:
        with pytest.raises(OperationRejected, match="Invalid query"):
            await search.people("ada")
        with pytest.raises(ProtocolError):
            await search.people("ada")
        with pytest.raises(ProtocolError):
            await search.people("ada")
        with pytest.raises(HTTPError):
            await search.people("ada")


@pytest.mark.parametrize(
    "call",
    [
        lambda search: search.people("ada", count=0),
        lambda search: search.people("ada", count=51),
        lambda search: search.people("ada", count=True),
        lambda search: search.people(42),
        lambda search: search.all(" "),
        lambda search: search.people("ada", PostFilters()),
        lambda search: search.groups("ada", cursor="next"),
    ],
)
async def test_bad_input_is_rejected_before_any_request(api, call):
    client, search, seen = api()
    async with client:
        with pytest.raises(ValueError):
            await call(search)
    assert seen == []
