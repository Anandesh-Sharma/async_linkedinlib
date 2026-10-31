import httpx
import pytest

from async_linkedinlib.exceptions import ProtocolError
from async_linkedinlib.models.posts import MediaKind
from async_linkedinlib.models.posts import UploadedMedia
from async_linkedinlib.resources.posts.media import URL_PREVIEW

ASSET = "urn:li:digitalmediaAsset:D4ETestAsset"
UPLOAD_URL = (
    "https://www.linkedin.com/dms-uploads/sp/sync/v2/D4ETestAsset/uploaded-image/B?ca=x&ut=y"
)


def registration(**changes) -> httpx.Response:
    value = {
        "urn": ASSET,
        "type": "SINGLE",
        "singleUploadUrl": UPLOAD_URL,
        "singleUploadHeaders": {"media-type-family": "STILLIMAGE"},
        "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
    }
    value.update(changes)
    return httpx.Response(200, json={"value": value})


async def test_upload_registers_then_puts_the_bytes_once(api, payloads):
    client, posts, seen = api(registration(), httpx.Response(201))
    async with client:
        uploaded = await posts.media.upload(b"\x89PNG test", MediaKind.IMAGE, filename="test.png")
    register, put = seen
    assert register.method == "POST"
    assert register.url.path == "/voyager/api/voyagerVideoDashMediaUploadMetadata"
    assert payloads.params(register) == {"action": "upload"}
    assert payloads.body(register) == {
        "mediaUploadType": "IMAGE_SHARING",
        "fileSize": 9,
        "hasOverlayImage": False,
        "uploadMetadataType": "DYNAMIC",
        "disableSynchronousUploadMechanism": False,
        "filename": "test.png",
    }
    assert put.method == "PUT"
    assert put.url.host == "www.linkedin.com"
    assert put.url.raw_path == b"/dms-uploads/sp/sync/v2/D4ETestAsset/uploaded-image/B?ca=x&ut=y"
    assert put.content == b"\x89PNG test"
    assert put.headers["content-type"] == "application/octet-stream"
    assert put.headers["media-type-family"] == "STILLIMAGE"
    assert uploaded == UploadedMedia(
        ASSET, MediaKind.IMAGE, ("urn:li:digitalmediaRecipe:feedshare-image",)
    )


async def test_upload_reads_a_path_and_names_the_file_after_it(api, payloads, tmp_path):
    path = tmp_path / "slides.pdf"
    path.write_bytes(b"%PDF-1.4 test")
    client, posts, seen = api(registration(), httpx.Response(201))
    async with client:
        uploaded = await posts.media.upload(path, MediaKind.DOCUMENT)
    assert payloads.body(seen[0])["filename"] == "slides.pdf"
    assert payloads.body(seen[0])["mediaUploadType"] == "DOCUMENT_SHARING"
    assert seen[1].content == b"%PDF-1.4 test"
    assert uploaded.kind is MediaKind.DOCUMENT


@pytest.mark.parametrize(
    "changes",
    [
        {"type": "MULTIPART", "singleUploadUrl": None},
        {"singleUploadUrl": "https://upload.example.test/dms-uploads/x"},
        {"singleUploadUrl": "http://www.linkedin.com/dms-uploads/x"},
        {"singleUploadUrl": "https://www.linkedin.com/voyager/api/me"},
        {"urn": None},
    ],
)
async def test_unsupported_upload_instructions_stop_before_sending_bytes(api, changes):
    client, posts, seen = api(registration(**changes))
    async with client:
        with pytest.raises(ProtocolError):
            await posts.media.upload(b"data", MediaKind.VIDEO, filename="test.mp4")
    assert len(seen) == 1


async def test_upload_refuses_empty_files_and_unknown_kinds(api):
    client, posts, seen = api()
    async with client:
        with pytest.raises(ValueError):
            await posts.media.upload(b"", MediaKind.IMAGE)
        with pytest.raises(ValueError):
            await posts.media.upload(b"data", "AUDIO")
    assert seen == []


async def test_status_asks_for_the_kind_the_app_uses(api, payloads):
    data = {"processingStatus": "READY", "documentProcessingResult": {"totalPageCount": 3}}
    client, posts, seen = api(httpx.Response(200, json=data))
    async with client:
        status = await posts.media.status(UploadedMedia(ASSET, MediaKind.DOCUMENT))
    request = seen[0]
    assert request.method == "GET"
    assert request.url.raw_path.startswith(
        b"/voyager/api/voyagerVideoDashMediaAssetStatus/urn%3Ali%3AdigitalmediaAsset%3AD4ETestAsset?"
    )
    assert payloads.params(request) == {
        "mediaStatusType": "DOCUMENT_PREVIEW",
        "decorationId": "com.linkedin.voyager.dash.deco.video.MediaAssetStatus-6",
    }
    assert (status.urn, status.state, status.page_count) == (ASSET, "READY", 3)


async def test_link_preview_reads_the_article_card(api, payloads):
    preview = {
        "originalUrl": None,
        "update": {
            "metadata": {"shareMediaUrn": "urn:li:article:7000"},
            "content": {
                "articleComponent": {
                    "title": {"text": "Test page"},
                    "subtitle": {"text": "example.test"},
                }
            },
        },
    }
    data = {"data": {"contentcreationDashUpdateUrlPreviewByUrl": {"elements": [preview]}}}
    client, posts, seen = api(httpx.Response(200, json=data))
    async with client:
        card = await posts.media.link_preview("https://example.test/a?b=1")
    assert payloads.params(seen[0])["queryId"] == URL_PREVIEW.id
    assert payloads.variables(seen[0]) == {"url": "https://example.test/a?b=1"}
    assert (card.url, card.article_urn, card.title, card.subtitle, card.original_url) == (
        "https://example.test/a?b=1",
        "urn:li:article:7000",
        "Test page",
        "example.test",
        None,
    )


async def test_link_preview_without_a_card_is_a_protocol_error(api):
    data = {"data": {"contentcreationDashUpdateUrlPreviewByUrl": {"elements": []}}}
    client, posts, _ = api(httpx.Response(200, json=data))
    async with client:
        with pytest.raises(ProtocolError):
            await posts.media.link_preview("https://example.test/")


@pytest.mark.parametrize("url", ["example.test", "ftp://example.test/x", "", None])
async def test_link_preview_needs_a_web_address(api, url):
    client, posts, seen = api()
    async with client:
        with pytest.raises(ValueError):
            await posts.media.link_preview(url)
    assert seen == []
