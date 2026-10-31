"""Store a resume or cover letter for an Easy Apply form, as the app's file picker does.

`voyagerJobsDashAmbryUploadUrls?action=requestUrl` returns an upload URL on
www.linkedin.com (`/ambry/?x-li-ambry-ep=...`); the file bytes are posted there once and
LinkedIn answers 201 with the stored file's `location`. The app answers the file slot
with `urn:li:fsd_resume:<location>`. Nothing is attached or applied until a submission
names that URN.
"""

import asyncio
import os
from pathlib import Path

from ...exceptions import ProtocolError
from ...exceptions import UnconfirmedWrite
from ...models.jobs_apply import UploadedFile
from ...transport import Transport
from ...transport.voyager import Voyager

UPLOAD_URLS = "voyagerJobsDashAmbryUploadUrls"
# The app's MimeType names for the document types resume slots accept.
DOCUMENT_TYPES = {
    "PDF": "application/pdf",
    "DOC": "application/msword",
    "DOCX": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_EXTENSIONS = {".pdf": "PDF", ".doc": "DOC", ".docx": "DOCX"}


def document_type(filename: str) -> str:
    """The app's MimeType name (PDF, DOC or DOCX) for a file name."""
    kind = _EXTENSIONS.get(Path(filename).suffix.lower())
    if kind is None:
        raise ValueError("Resumes and cover letters must be .pdf, .doc or .docx files.")
    return kind


async def upload(
    voyager: Voyager,
    file: str | os.PathLike[str] | bytes,
    filename: str | None,
    max_size: int | None,
) -> UploadedFile:
    if max_size is not None and (type(max_size) is not int or max_size < 1):
        raise ValueError("max_size must be a positive number of bytes.")
    if isinstance(file, bytes):
        if not filename:
            raise ValueError("A file name is required when uploading bytes.")
        data, name = file, filename
    else:
        path = Path(file)
        if max_size is not None and (await asyncio.to_thread(path.stat)).st_size > max_size:
            raise ValueError(f"The file is larger than {max_size} bytes.")
        data = await asyncio.to_thread(path.read_bytes)
        name = filename or path.name
    if not data:
        raise ValueError("The file is empty.")
    if max_size is not None and len(data) > max_size:
        raise ValueError(f"The file is larger than {max_size} bytes.")
    kind = document_type(name)
    reply = await voyager.post(
        UPLOAD_URLS, {"contentType": kind, "filename": name}, {"action": "requestUrl"}
    )
    target = Transport.upload_path(reply.data.get("value"), "/ambry/")
    if target is None:
        raise ProtocolError("LinkedIn offered an upload location this client does not support.")
    response = await voyager.transport.request(
        "POST", target, content=data, headers={"content-type": DOCUMENT_TYPES[kind]}
    )
    location = response.headers.get("location")
    if response.status_code != 201 or not location:
        raise UnconfirmedWrite("LinkedIn did not confirm the file upload.")
    return UploadedFile(
        urn=f"urn:li:fsd_resume:{location}",
        file_name=name,
        content_type=DOCUMENT_TYPES[kind],
        size=len(data),
    )
