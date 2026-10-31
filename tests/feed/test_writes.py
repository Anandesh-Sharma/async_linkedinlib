import httpx
import pytest

from async_linkedinlib import ProtocolError
from async_linkedinlib import ReactionType
from async_linkedinlib.exceptions import OperationRejected
from async_linkedinlib.models.pagination import Cursor
from async_linkedinlib.resources import reactions
from async_linkedinlib.resources.feed import queries
from async_linkedinlib.resources.search.queries import CLUSTERS

UPDATE = "urn:li:fsd_update:(urn:li:activity:1,MAIN_FEED,EMPTY,DEFAULT,false)"
OPTION = "urn:li:fsu_pollOption:urn:li:pollOption:(urn:li:poll:1,11)"
SAVED = "searchDashClustersByAll"


@pytest.mark.parametrize(("method", "saved"), [("save", True), ("unsave", False)])
async def test_save_state_is_keyed_on_the_activity(api, fx, method, saved):
    client, feed, seen = api(lambda r: fx.action("updateFeedDashSaveStates"))
    async with client:
        assert await getattr(feed, method)("urn:li:activity:5") is None
    request = seen[0]
    assert request.method == "POST"
    assert fx.params(request) == {
        "action": "execute",
        "queryId": queries.SAVE_STATE.id,
        "queryName": "UpdateSaveStateBySaveStateUrn",
    }
    assert fx.body(request)["variables"] == {
        "entity": {
            "entity": {
                "saved": saved,
                "preDashEntityUrn": "urn:li:fs_saveAction:(SAVE,urn:li:activity:5)",
            },
            "resourceKey": "urn:li:fsd_saveState:(SAVE,urn:li:activity:5)",
        }
    }


async def test_saving_a_ugc_post_urn_is_refused_before_sending(api, fx):
    client, feed, seen = api(lambda r: fx.action("updateFeedDashSaveStates"))
    async with client:
        with pytest.raises(ValueError, match="activity_urn"):
            await feed.save("urn:li:ugcPost:5")
    assert seen == []


@pytest.mark.parametrize(
    ("method", "query", "field"),
    [
        ("hide", queries.HIDE, "doFeedbackFeedDashUpdateFeedback"),
        ("undo_hide", queries.UNDO_HIDE, "doUndoFeedbackFeedDashUpdateFeedback"),
    ],
)
async def test_hide_and_undo_address_the_feed_update(api, fx, method, query, field):
    client, feed, seen = api(lambda r: fx.action(field, ""))
    async with client:
        await getattr(feed, method)(UPDATE)
        with pytest.raises(ValueError, match="update URN"):
            await getattr(feed, method)("urn:li:activity:1")
    assert fx.params(seen[0])["queryId"] == query.id
    assert fx.body(seen[0])["variables"] == {"updateUrn": UPDATE}
    assert len(seen) == 1


@pytest.mark.parametrize(("method", "query"), [("vote", queries.VOTE), ("unvote", queries.UNVOTE)])
async def test_votes_address_the_poll_option(api, fx, method, query):
    client, feed, seen = api(lambda r: fx.action("doSubmitVoteSocialDashPollVotes", {}))
    async with client:
        await getattr(feed, method)(OPTION)
        with pytest.raises(ValueError, match="poll option"):
            await getattr(feed, method)("")
    assert fx.params(seen[0])["queryName"] == query.name
    assert fx.body(seen[0])["variables"] == {"pollOptionUrn": OPTION}
    assert len(seen) == 1


async def test_rejected_and_empty_action_replies(api, fx):
    replies = [
        httpx.Response(200, json={"value": {"errors": [{"message": "Not allowed"}]}}),
        httpx.Response(200, json={"value": {"data": {}}}),
    ]
    client, feed, seen = api(lambda r: replies[len(seen) - 1])
    async with client:
        with pytest.raises(OperationRejected, match="Not allowed"):
            await feed.hide(UPDATE)
        with pytest.raises(ProtocolError, match="no result"):
            await feed.hide(UPDATE)
    assert len(seen) == 2


async def test_reaction_writes_use_the_shared_reaction_mutations(api, fx):
    client, feed, seen = api(lambda r: fx.action("anyReactionField"))
    async with client:
        await feed.react("urn:li:activity:1", ReactionType.LOVE)
        await feed.change_reaction("urn:li:activity:1", ReactionType.FUNNY)
        await feed.unreact("urn:li:activity:1")
    assert [fx.params(r)["queryId"] for r in seen] == [
        reactions.CREATE.id,
        reactions.UPDATE.id,
        reactions.DELETE.id,
    ]
    assert fx.body(seen[0])["variables"] == {
        "threadUrn": "urn:li:activity:1",
        "entity": {"reactionType": "EMPATHY"},
    }
    assert fx.body(seen[1])["variables"]["newReactionType"] == "ENTERTAINMENT"


def saved_reply(results, *, errors=None, token="s1", total=12):
    found = {
        "metadata": {"paginationToken": token, "entityResultAttributes": None},
        "paging": {"start": 0, "count": 2, "total": total},
        "elements": [{"items": [{"item": {"entityResult": result}} for result in results]}],
    }
    payload: dict = {"data": {SAVED: found}}
    if errors:
        payload["errors"] = errors
    return httpx.Response(200, json=payload)


METADATA_NULL = {
    "message": "The field at path '/searchDashClustersByAll/metadata/x' was declared non null",
    "path": [SAVED, "metadata", "entityResultAttributes", "templateType"],
    "extensions": {"classification": "NullValueInNonNullableField"},
}


async def test_saved_lists_my_items_and_tolerates_the_metadata_null(api, fx):
    results = [{"trackingUrn": "urn:li:activity:1"}, {"trackingUrn": "urn:li:activity:2"}]
    client, feed, seen = api(lambda r: saved_reply(results, errors=[METADATA_NULL]))
    async with client:
        page = await feed.saved(count=2)
        await feed.saved(count=2, cursor=page.next)
    assert fx.params(seen[0]) == {
        "queryId": CLUSTERS.id,
        "queryName": "SearchClusterCollection",
    }
    assert seen[0].headers["x-li-graphql-pegasus-client"] == "true"
    assert fx.variables(seen[0]) == {
        "query": {"flagshipSearchIntent": "SEARCH_MY_ITEMS_SAVED_POSTS"},
        "count": "2",
        "start": "0",
    }
    assert fx.variables(seen[1])["paginationToken"] == "s1"
    assert [post.urn for post in page.items] == ["urn:li:activity:1", "urn:li:activity:2"]
    assert page.total == 12
    assert page.next == Cursor("feed.saved", "", 2, "s1")


@pytest.mark.parametrize(
    "error",
    [
        {"message": "Variable 'query' has an invalid value", "path": None},
        {**METADATA_NULL, "extensions": {"classification": "DataFetchingException"}},
    ],
)
async def test_saved_refuses_other_errors(api, fx, error):
    client, feed, seen = api(lambda r: saved_reply([], errors=[error]))
    async with client:
        with pytest.raises(OperationRejected):
            await feed.saved()


async def test_saved_accepts_null_field_errors_anywhere(api, fx):
    error = {**METADATA_NULL, "path": [SAVED, "elements", 0, "items"]}
    client, feed, seen = api(lambda r: saved_reply([], errors=[error]))
    async with client:
        assert (await feed.saved()).items == ()


async def test_empty_saved_list_ends_paging(api, fx):
    reply = httpx.Response(
        200, json={"data": {SAVED: {"metadata": {"paginationToken": ""}, "elements": []}}}
    )
    client, feed, seen = api(lambda r: reply)
    async with client:
        page = await feed.saved()
    assert page.items == () and page.next is None
