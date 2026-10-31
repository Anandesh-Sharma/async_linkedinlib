"""Files and link cards for posts: upload, processing status, link previews.

An upload is registered with `voyagerVideoDashMediaUploadMetadata?action=upload`; LinkedIn
answers with the asset URN and a single upload URL on www.linkedin.com (`/dms-uploads/`)
that takes the bytes in one PUT. Galleries and polls are separate entities that the share
references; `Posts.create` makes them through the helpers here.
"""

import asyncio
import os
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import quote
from urllib.parse import urlsplit

from ...exceptions import ProtocolError
from ...exceptions import UnconfirmedWrite
from ...models._json import dig
from ...models._json import integer
from ...models._json import items
from ...models._json import obj
from ...models._json import string
from ...models._json import text
from ...models.posts import Image
from ...models.posts import LinkPreview
from ...models.posts import MediaKind
from ...models.posts import NewPoll
from ...models.posts import UploadedMedia
from ...models.posts_results import MediaStatus
from ...transport import Transport
from ...transport.voyager import GraphQLQuery
from ...transport.voyager import Voyager
from . import payloads

UPLOAD_METADATA = "voyagerVideoDashMediaUploadMetadata"
ASSET_STATUS = "voyagerVideoDashMediaAssetStatus"
MULTI_PHOTOS = "voyagerVideoDashMultiPhotos"
STATUS_DECORATION = "com.linkedin.voyager.dash.deco.video.MediaAssetStatus-6"
URL_PREVIEW = GraphQLQuery(
    "voyagerContentcreationDashUpdateUrlPreview.0891457da461730e024a24803ff8e1e7",
    "UpdateUrlPreviewByUrl",
)
CREATE_POLL = GraphQLQuery(
    "voyagerFeedDashPollsPollSummary.10244461333ea4d87e8177aa97aebc24", "CreatePoll"
)
# The status kind the app asks for per upload use case.
_STATUS_TYPES = {
    MediaKind.IMAGE: "IMAGE",
    MediaKind.VIDEO: "VIDEO",
    MediaKind.DOCUMENT: "DOCUMENT_PREVIEW",
}


class PostMedia:
    """Upload files for posts and preview links; nothing here publishes anything."""

    def __init__(self, voyager: Voyager) -> None:
        self._voyager = voyager

    async def upload(
        self,
        file: str | os.PathLike[str] | bytes,
        kind: MediaKind,
        *,
        filename: str | None = None,
    ) -> UploadedMedia:
        """Store an image, video or document; attach the result with `Image`, `Video`..."""
        kind = MediaKind(kind)
        if isinstance(file, bytes):
            data, name = file, filename
        else:
            path = Path(file)
            data = await asyncio.to_thread(path.read_bytes)
            name = filename or path.name
        if not data:
            raise ValueError("The file is empty.")
        body: dict[str, object] = {
            "mediaUploadType": kind.value,
            "fileSize": len(data),
            "hasOverlayImage": False,
            "uploadMetadataType": "DYNAMIC",
            "disableSynchronousUploadMechanism": False,
        }
        if name:
            body["filename"] = name
        reply = await self._voyager.post(UPLOAD_METADATA, body, {"action": "upload"})
        upload = obj(reply.data.get("value"))
        urn = string(upload, "urn")
        if not urn:
            raise UnconfirmedWrite("LinkedIn did not register the upload.")
        target = _single_upload_path(upload)
        headers = {
            key: value
            for key, value in obj(upload.get("singleUploadHeaders")).items()
            if isinstance(value, str)
        }
        headers["content-type"] = "application/octet-stream"
        response = await self._voyager.transport.request(
            "PUT", target, content=data, headers=headers
        )
        if response.status_code not in (200, 201):
            raise UnconfirmedWrite("LinkedIn did not confirm the upload.")
        recipes = tuple(r for r in upload.get("recipes") or () if isinstance(r, str))
        return UploadedMedia(urn, kind, recipes)

    async def status(self, media: UploadedMedia) -> MediaStatus:
        """Read whether LinkedIn finished processing an upload."""
        if not isinstance(media, UploadedMedia):
            raise ValueError("An UploadedMedia from upload() is required.")
        data = await self._voyager.get(
            f"{ASSET_STATUS}/{quote(media.urn, safe='')}",
            {"mediaStatusType": _STATUS_TYPES[media.kind], "decorationId": STATUS_DECORATION},
        )
        return MediaStatus(
            urn=media.urn,
            state=string(data, "processingStatus"),
            page_count=integer(data, "documentProcessingResult", "totalPageCount"),
            raw=data,
        )

    async def link_preview(self, url: str) -> LinkPreview:
        """Build the article card for a web address, as the share box does on paste."""
        parts = urlsplit(url) if isinstance(url, str) else None
        if parts is None or parts.scheme not in ("http", "https") or not parts.netloc:
            raise ValueError("An http or https URL is required.")
        data = await self._voyager.query(URL_PREVIEW, {"url": url})
        found = items(dig(data, "contentcreationDashUpdateUrlPreviewByUrl", "elements"))
        preview = found[0] if found else {}
        update = obj(preview.get("update"))
        article = string(update, "metadata", "shareMediaUrn")
        if not article:
            raise ProtocolError("LinkedIn returned no preview for this URL.")
        card = obj(dig(update, "content", "articleComponent"))
        return LinkPreview(
            url=url,
            article_urn=article,
            title=text(card, "title"),
            subtitle=text(card, "subtitle"),
            original_url=string(preview, "originalUrl"),
            raw=preview,
        )


async def create_gallery(voyager: Voyager, images: Sequence[Image], member_id: str) -> str:
    """Create the multi-photo entity a gallery post references; returns its URN."""
    body = payloads.multi_photo(images, f"urn:li:member:{member_id}")
    reply = await voyager.post(MULTI_PHOTOS, body)
    urn = string(reply.data, "identifierUrn") or reply.created_id
    if not urn:
        raise UnconfirmedWrite("LinkedIn did not create the image gallery.")
    return urn


async def create_poll(voyager: Voyager, poll: NewPoll) -> str:
    """Create the poll entity a poll post references; returns its URN."""
    data = await voyager.mutate(CREATE_POLL, {"pollInput": payloads.poll(poll)})
    urn = string(data, "doCreatePollFeedDashPollsPollSummary", "result", "entityUrn")
    if not urn:
        raise UnconfirmedWrite("LinkedIn did not create the poll.")
    return urn


def _single_upload_path(upload: dict[str, object]) -> str:
    """The origin-relative path of a single-request upload on www.linkedin.com."""
    kind = upload.get("type")
    url = upload.get("singleUploadUrl")
    if kind != "SINGLE" or not isinstance(url, str):
        name = kind if isinstance(kind, str) and kind.isidentifier() else "different"
        raise ProtocolError(f"LinkedIn asked for a {name} upload, which is not supported.")
    path = Transport.upload_path(url, "/dms-uploads/")
    if path is None:
        raise ProtocolError("LinkedIn offered an upload location this client does not support.")
    return path
