import pytest

from async_linkedinlib.models.search import TypeaheadKind
from async_linkedinlib.resources.search.queries import GLOBAL_TYPEAHEAD
from async_linkedinlib.resources.search.queries import TYPEAHEAD


def typeahead_reply(*elements):
    return {"data": {"searchDashReusableTypeaheadByType": {"elements": list(elements)}}}


async def test_geo_typeahead_asks_for_places_like_the_filter_sheet(api, payloads):
    element = {
        "trackingUrn": "urn:li:geo:9001",
        "title": payloads.text("Testville, Testland"),
        "target": {"geo": {"entityUrn": "urn:li:fsd_geo:9001"}},
    }
    client, search, seen = api(typeahead_reply(element))
    async with client:
        found = await search.typeahead(TypeaheadKind.GEO, "test  ville", count=5)
    sent = payloads.sent(seen[0])
    assert (sent.query_id, sent.name) == (TYPEAHEAD.id, TYPEAHEAD.name)
    assert sent.variables == {
        "keywords": "test ville",
        "query": {
            "showFullLastNameForConnections": "true",
            "typeaheadFilterQuery": {
                "geoSearchTypes": ["MARKET_AREA", "COUNTRY_REGION", "ADMIN_DIVISION_1", "CITY"],
                "standardizationEntityType": "industryV2",
            },
        },
        "type": "GEO",
        "count": "5",
    }
    suggestion = found[0]
    assert (suggestion.id, suggestion.urn, suggestion.kind) == (
        "9001",
        "urn:li:fsd_geo:9001",
        "geo",
    )
    assert (suggestion.title, suggestion.tracking_urn) == ("Testville, Testland", "urn:li:geo:9001")


async def test_typeahead_reads_record_and_bare_urn_targets(api, payloads):
    company = {
        "trackingUrn": "urn:li:organization:2001",
        "title": payloads.text("Example Co"),
        "subtitle": payloads.text("Software Development"),
        "target": {"company": {"entityUrn": "urn:li:fsd_company:2001"}},
    }
    function = {
        "trackingUrn": "urn:li:jobFunction:eng",
        "title": payloads.text("Engineering"),
        "target": {"jobFunction": "urn:li:fsu_jobfunction:eng"},
    }
    client, search, seen = api(typeahead_reply(company), typeahead_reply(function))
    async with client:
        companies = await search.typeahead(TypeaheadKind.COMPANY, "exam")
        functions = await search.typeahead(TypeaheadKind.JOB_FUNCTION, "eng")
    variables = payloads.sent(seen[0]).variables
    assert variables["type"] == "COMPANY" and "count" not in variables
    assert "geoSearchTypes" not in variables["query"]["typeaheadFilterQuery"]
    assert (companies[0].id, companies[0].kind, companies[0].subtitle) == (
        "2001",
        "company",
        "Software Development",
    )
    assert (functions[0].id, functions[0].urn, functions[0].kind) == (
        "eng",
        "urn:li:fsu_jobfunction:eng",
        "jobFunction",
    )


async def test_suggest_reads_search_bar_suggestions(api, payloads):
    reply = {
        "data": {
            "searchDashTypeaheadByGlobalTypeahead": {
                "elements": [
                    {
                        "suggestionType": "ENTITY_TYPEAHEAD",
                        "entityLockupView": {
                            "trackingUrn": "urn:li:company:2001",
                            "title": payloads.text("Example Co"),
                            "subtitle": payloads.text("Company • Software"),
                        },
                    },
                    {
                        "suggestionType": "QUERY_SUGGESTION_TYPEAHEAD",
                        "entityLockupView": {"title": payloads.text("example jobs")},
                    },
                ]
            }
        }
    }
    client, search, seen = api(reply)
    async with client:
        found = await search.suggest("exam")
    sent = payloads.sent(seen[0])
    assert (sent.query_id, sent.name, sent.variables) == (
        GLOBAL_TYPEAHEAD.id,
        GLOBAL_TYPEAHEAD.name,
        {"query": "exam"},
    )
    assert [(item.kind, item.id, item.title) for item in found] == [
        ("ENTITY_TYPEAHEAD", "2001", "Example Co"),
        ("QUERY_SUGGESTION_TYPEAHEAD", None, "example jobs"),
    ]


@pytest.mark.parametrize(
    "call",
    [
        lambda search: search.typeahead(TypeaheadKind.GEO, "  "),
        lambda search: search.typeahead("PLANET", "x"),
        lambda search: search.typeahead(TypeaheadKind.GEO, "x", count=0),
        lambda search: search.suggest(""),
    ],
)
async def test_bad_typeahead_input_is_rejected(api, call):
    client, search, seen = api()
    async with client:
        with pytest.raises(ValueError):
            await call(search)
    assert seen == []
