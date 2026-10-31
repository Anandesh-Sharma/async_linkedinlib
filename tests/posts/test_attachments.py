import httpx
import pytest

from async_linkedinlib.exceptions import ProtocolError
from async_linkedinlib.models.posts import Document
from async_linkedinlib.models.posts import Image
from async_linkedinlib.models.posts import LinkPreview
from async_linkedinlib.models.posts import MediaKind
from async_linkedinlib.models.posts import NewPoll
from async_linkedinlib.models.posts import PollDuration
from async_linkedinlib.models.posts import UploadedMedia
from async_linkedinlib.models.posts import Video
from async_linkedinlib.resources.posts.media import CREATE_POLL

CREATED = "createContentcreationDashShares"
IMAGE_RECIPE = "urn:li:digitalmediaRecipe:feedshare-image"


def media(kind: MediaKind, asset: str = "D4ETestAsset1") -> UploadedMedia:
    return UploadedMedia(f"urn:li:digitalmediaAsset:{asset}", kind, (IMAGE_RECIPE,))


def created(payloads) -> httpx.Response:
    return httpx.Response(200, json=payloads.share_reply(CREATED, payloads.update(), "Done"))


def shared_media(payloads, request: httpx.Request) -> dict:
    return payloads.body(request)["variables"]["entity"]["media"]


async def test_one_image_is_shared_directly_with_its_alt_text(api, payloads):
    client, posts, seen = api(created(payloads))
    async with client:
        await posts.create("", media=Image(media(MediaKind.IMAGE), "A test square"))
    assert len(seen) == 1
    assert shared_media(payloads, seen[0]) == {
        "category": "IMAGE",
        "mediaUrn": "urn:li:digitalmediaAsset:D4ETestAsset1",
        "recipes": [IMAGE_RECIPE],
        "tapTargets": [],
        "nativeMediaSource": "PRE_RECORDED",
        "altText": "A test square",
    }


async def test_several_images_become_a_gallery_the_share_references(api, payloads, session):
    session.member_id = "42"
    gallery = httpx.Response(
        201,
        json={"identifierUrn": "urn:li:fsd_multiPhoto:5000"},
        headers={"x-restli-id": "urn:li:fsd_multiPhoto:5000"},
    )
    client, posts, seen = api(gallery, created(payloads))
    first, second = media(MediaKind.IMAGE, "D4EOne"), media(MediaKind.IMAGE, "D4ETwo")
    async with client:
        await posts.create("Test gallery", media=[Image(first, "one"), Image(second)])
    assert seen[0].method == "POST"
    assert seen[0].url.path == "/voyager/api/voyagerVideoDashMultiPhotos"
    assert payloads.body(seen[0]) == {
        "authorUrn": "urn:li:member:42",
        "entities": [
            {
                "mediaUrn": first.urn,
                "tapTargets": [],
                "mediaSource": "PRE_RECORDED",
                "altText": "one",
            },
            {"mediaUrn": second.urn, "tapTargets": [], "mediaSource": "PRE_RECORDED"},
        ],
    }
    assert shared_media(payloads, seen[1]) == {
        "category": "URN_REFERENCE",
        "mediaUrn": "urn:li:fsd_multiPhoto:5000",
    }


async def test_a_gallery_needs_the_session_member_and_sends_nothing_without_it(api):
    client, posts, seen = api()
    images = [Image(media(MediaKind.IMAGE, "D4EOne")), Image(media(MediaKind.IMAGE, "D4ETwo"))]
    async with client:
        with pytest.raises(ValueError, match="account.me"):
            await posts.create("Test", media=images)
    assert seen == []


async def test_a_poll_is_created_first_then_referenced(api, payloads):
    poll_reply = {
        "value": {
            "data": {
                "doCreatePollFeedDashPollsPollSummary": {
                    "result": {"entityUrn": "urn:li:fsd_pollSummary:6000"}
                }
            }
        }
    }
    client, posts, seen = api(httpx.Response(200, json=poll_reply), created(payloads))
    poll = NewPoll("Test question?", ("Yes", "No"), PollDuration.THREE_DAYS)
    async with client:
        await posts.create("Test poll", media=poll)
    assert payloads.body(seen[0]) == {
        "queryId": CREATE_POLL.id,
        "queryName": "CreatePoll",
        "variables": {
            "pollInput": {
                "question": "Test question?",
                "options": ["Yes", "No"],
                "duration": "THREE_DAYS",
            }
        },
    }
    assert shared_media(payloads, seen[1]) == {
        "category": "URN_REFERENCE",
        "mediaUrn": "urn:li:fsd_pollSummary:6000",
    }


async def test_a_poll_reply_without_its_urn_stops_before_the_post(api):
    empty = {"value": {"data": {"doCreatePollFeedDashPollsPollSummary": {"result": {}}}}}
    client, posts, seen = api(httpx.Response(200, json=empty))
    async with client:
        with pytest.raises(ProtocolError):
            await posts.create("Test", media=NewPoll("Q?", ("A", "B")))
    assert len(seen) == 1


@pytest.mark.parametrize(
    ("attachment", "expected"),
    [
        (
            Video(UploadedMedia("urn:li:digitalmediaAsset:D4EVideo", MediaKind.VIDEO, ("r1",))),
            {
                "category": "VIDEO",
                "mediaUrn": "urn:li:digitalmediaAsset:D4EVideo",
                "recipes": ["r1"],
                "tapTargets": [],
                "nativeMediaSource": "PRE_RECORDED",
            },
        ),
        (
            Document(
                UploadedMedia("urn:li:digitalmediaAsset:D4EDoc", MediaKind.DOCUMENT, ("r2",)),
                "Test slides",
            ),
            {
                "category": "NATIVE_DOCUMENT",
                "mediaUrn": "urn:li:digitalmediaAsset:D4EDoc",
                "recipes": ["r2"],
                "title": "Test slides",
            },
        ),
        (
            LinkPreview("https://example.test/a", "urn:li:article:7000"),
            {"category": "URN_REFERENCE", "mediaUrn": "urn:li:article:7000"},
        ),
        (
            LinkPreview(
                "https://example.test/a",
                "urn:li:article:7000",
                original_url="https://example.test/",
            ),
            {
                "category": "URN_REFERENCE",
                "mediaUrn": "urn:li:article:7000",
                "originalUrl": "https://example.test/",
            },
        ),
    ],
)
async def test_video_document_and_link_share_media(api, payloads, attachment, expected):
    client, posts, seen = api(created(payloads))
    async with client:
        await posts.create("Test", media=attachment)
    assert shared_media(payloads, seen[0]) == expected


@pytest.mark.parametrize(
    "build",
    [
        lambda: Image(media(MediaKind.VIDEO)),
        lambda: Video(media(MediaKind.IMAGE)),
        lambda: Document(media(MediaKind.DOCUMENT), " "),
        lambda: Document(media(MediaKind.IMAGE), "Title"),
        lambda: Image("urn:li:digitalmediaAsset:D4E"),
        lambda: NewPoll("Q?", ("Only one",)),
        lambda: NewPoll("Q?", ("1", "2", "3", "4", "5", "6")),
        lambda: NewPoll("Q?", ("Yes", "x" * 31)),
        lambda: NewPoll("Q" * 141, ("Yes", "No")),
        lambda: NewPoll(" ", ("Yes", "No")),
        lambda: NewPoll("Q?", ("Yes", "No"), "FOREVER"),
    ],
)
def test_attachments_check_their_inputs(build):
    with pytest.raises(ValueError):
        build()


def test_poll_limits_count_utf16_units_like_the_app():
    assert NewPoll("Q?", ("x" * 30, "y")).options == ("x" * 30, "y")
    with pytest.raises(ValueError):
        NewPoll("Q?", ("🧪" * 16, "y"))
