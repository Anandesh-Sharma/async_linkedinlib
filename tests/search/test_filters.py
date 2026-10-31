import pytest

from async_linkedinlib.models.search import Vertical
from async_linkedinlib.models.search_filters import CompanyFilters
from async_linkedinlib.models.search_filters import ContentType
from async_linkedinlib.models.search_filters import CourseFilters
from async_linkedinlib.models.search_filters import CourseLength
from async_linkedinlib.models.search_filters import CourseLevel
from async_linkedinlib.models.search_filters import Network
from async_linkedinlib.models.search_filters import PeopleFilters
from async_linkedinlib.models.search_filters import PostedBy
from async_linkedinlib.models.search_filters import PostFilters
from async_linkedinlib.models.search_filters import ProductFilters
from async_linkedinlib.models.search_filters import ServiceFilters
from async_linkedinlib.resources.search.queries import FILTERS


def test_people_filters_use_the_app_filter_keys():
    filters = PeopleFilters(
        network=["F"],
        locations=["9001"],
        current_companies=["urn:li:fsd_company:2001"],
        past_companies=["urn:li:organization:2002"],
        schools=["3001"],
        industries=["4"],
        profile_languages=["en", "_o"],
        service_categories=["602"],
        connection_of="urn:li:fsd_profile:ACoFriend",
        follower_of="ACoCreator",
        open_to_volunteer=True,
        first_name="Ada",
        last_name="Example",
        title="Engineer",
        company="Example Co",
        school="Test University",
        extra={"seniorityV2": ["120"]},
    )
    assert filters.params() == {
        "network": ["F"],
        "geoUrn": ["9001"],
        "currentCompany": ["2001"],
        "pastCompany": ["2002"],
        "schoolFilter": ["3001"],
        "industry": ["4"],
        "profileLanguage": ["en", "_o"],
        "serviceCategory": ["602"],
        "connectionOf": ["ACoFriend"],
        "followerOf": ["ACoCreator"],
        "openToVolunteer": ["true"],
        "firstName": ["Ada"],
        "lastName": ["Example"],
        "title": ["Engineer"],
        "company": ["Example Co"],
        "schoolFreetext": ["Test University"],
        "seniorityV2": ["120"],
    }
    assert PeopleFilters().params() == {}


def test_other_vertical_filters_map_to_their_keys():
    posts = PostFilters(
        content_type=ContentType.DOCUMENTS,
        posted_by=[PostedBy.ME, PostedBy.PEOPLE_YOU_FOLLOW],
        from_members=["ACoAuthor"],
        mentions_members=["ACoMentioned"],
        mentions_companies=["2001"],
        author_industries=["4"],
        author_companies=["2002"],
        author_title="CTO",
    )
    assert posts.params() == {
        "contentType": ["documents"],
        "postedBy": ["me", "following"],
        "fromMember": ["ACoAuthor"],
        "mentionsMember": ["ACoMentioned"],
        "mentionsOrganization": ["2001"],
        "authorIndustry": ["4"],
        "authorCompany": ["2002"],
        "authorJobTitle": ["CTO"],
    }
    company = CompanyFilters(locations=["9001"], industries=["4"], network=[Network.FIRST])
    assert company.params() == {
        "companyHqGeo": ["9001"],
        "industryCompanyVertical": ["4"],
        "network": ["F"],
    }
    assert ServiceFilters(service_categories=["602"], locations=["9001"]).params() == {
        "serviceCategory": ["602"],
        "geoUrn": ["9001"],
    }
    assert ProductFilters(categories=["1361"], companies=["2001"], free_plan=True).params() == {
        "productCategory": ["1361"],
        "productCompany": ["2001"],
        "productFreePlan": ["true"],
    }
    course = CourseFilters(
        levels=[CourseLevel.BEGINNER],
        lengths=[CourseLength.UNDER_10_MINUTES],
        software=["Python"],
        topics=["7164"],
        education_units=["CPE"],
    )
    assert course.params() == {
        "difficultyLevel": ["Beginner"],
        "timeToComplete": ["< 10 mins"],
        "softwareNames": ["Python"],
        "categoryIds": ["7164"],
        "continuingEducationUnits": ["CPE"],
    }


@pytest.mark.parametrize(
    "build",
    [
        lambda: PeopleFilters(locations="9001"),
        lambda: PeopleFilters(locations=[""]),
        lambda: PeopleFilters(locations=["90 01"]),
        lambda: PeopleFilters(current_companies=["urn:li:fsd_x:(1,2)"]),
        lambda: PeopleFilters(network=["X"]),
        lambda: PeopleFilters(open_to_volunteer="yes"),
        lambda: PeopleFilters(title="  "),
        lambda: PeopleFilters(extra={"geoUrn": ["1"]}),
        lambda: PeopleFilters(extra={"resultType": ["JOBS"]}),
        lambda: PeopleFilters(extra={"bad key": ["1"]}),
        lambda: PeopleFilters(extra={"seniorityV2": "120"}),
        lambda: PostFilters(sort_by="newest"),
        lambda: CourseFilters(lengths=["forever"]),
    ],
)
def test_invalid_filters_raise_value_error(build):
    with pytest.raises(ValueError):
        build()


def filter_view(key, values=(), *, kind="MULTI_SELECT", typeahead=None, **extra):
    return {
        "parameterName": key,
        "displayName": {"text": key.title()},
        "renderType": kind,
        "typeaheadType": typeahead,
        "appliedCount": 0,
        "primaryFilterValues": [],
        "secondaryFilterValues": [
            {"value": value, "displayName": label, "count": 0, "selected": False}
            for value, label in values
        ],
        **extra,
    }


async def test_filter_discovery_lists_each_filter_once(api, payloads):
    network = filter_view("network", [("F", "1st"), ("S", "2nd")])
    reply = {
        "data": {
            "searchDashFilterClustersByFilters": {
                "elements": [
                    {
                        "primaryFilterGroups": [
                            {"filters": [filter_view("resultType", [("ALL", "All")])]},
                            {"filters": [network]},
                        ],
                        "secondaryFilterGroups": [
                            {"filters": [network]},
                            {
                                "filters": [
                                    filter_view("geoUrn", [("9001", "Testville")], typeahead="GEO")
                                ]
                            },
                            {"filters": [filter_view("premium", upsellSlot={"x": 1})]},
                            {"filters": [filter_view("firstName", kind="FREE_TEXT")]},
                        ],
                    }
                ]
            }
        }
    }
    client, search, seen = api(reply)
    async with client:
        found = await search.filters(Vertical.PEOPLE, "ada", PeopleFilters(network=["F"]))
    sent = payloads.sent(seen[0])
    assert (sent.query_id, sent.name) == (FILTERS.id, FILTERS.name)
    assert sent.variables == {
        "query": {
            "flagshipSearchIntent": "SEARCH_SRP",
            "keywords": "ada",
            "queryParameters": {"resultType": ["PEOPLE"], "network": ["F"]},
            "spellCorrectionEnabled": "true",
        }
    }
    assert [item.key for item in found] == ["network", "geoUrn", "firstName"]
    location = found[1]
    assert (location.label, location.kind, location.typeahead) == ("Geourn", "MULTI_SELECT", "GEO")
    assert [(option.value, option.label) for option in location.options] == [("9001", "Testville")]
    assert found[2].options == ()


async def test_filter_discovery_checks_the_filters_type(api):
    client, search, seen = api()
    async with client:
        with pytest.raises(ValueError, match="PeopleFilters"):
            await search.filters(Vertical.PEOPLE, "ada", PostFilters())
        with pytest.raises(ValueError):
            await search.filters(Vertical.GROUPS, "ada", PeopleFilters())
        with pytest.raises(ValueError):
            await search.filters("JOBS")
    assert seen == []
