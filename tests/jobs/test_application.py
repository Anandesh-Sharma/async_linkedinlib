import json
from urllib.parse import parse_qs

import httpx
import pytest

from async_linkedinlib import ProtocolError
from async_linkedinlib.exceptions import OperationRejected
from async_linkedinlib.models.jobs_apply import QuestionKind
from async_linkedinlib.transport.restli import encode

JOB_ID = "1234567890"
JOB_URN = f"urn:li:fsd_jobPosting:{JOB_ID}"
UPLOAD_URL = "https://www.linkedin.com/ambry/?x-li-ambry-ep=SIGNED-TOKEN"


def form_reply(payload):
    return httpx.Response(
        200, json={"data": {"jobsDashOnsiteApplyApplicationByJobPosting": {"elements": [payload]}}}
    )


async def test_application_reads_the_form_by_job_posting(make_jobs, form_payload):
    seen = []

    def handle(request):
        seen.append(request)
        return form_reply(form_payload)

    client, jobs = make_jobs(handle)
    async with client:
        form = await jobs.application(JOB_ID)
    raw = seen[0].url.query.decode()
    assert seen[0].method == "GET"
    assert f"variables={encode({'jobPostingUrn': JOB_URN})}" in raw
    assert parse_qs(raw)["queryId"] == [
        "voyagerJobsDashOnsiteApplyApplication.3a3ede1703d12540cf2e7e4bd04a3bbd"
    ]
    assert parse_qs(raw)["queryName"] == ["JobsOnsiteApplyApplicationByJobPosting"]
    assert (form.job_id, form.company, form.applied) == (JOB_ID, "Example Foods", False)
    assert [page.section for page in form.pages] == ["CONTACT_INFO", "RESUME", "BASIC"]
    assert form.pages[2].title == "Additional Questions"
    assert not form.needs_data_consent and not form.has_repeatable_sections


async def test_questions_carry_kind_options_prefill_and_limits(make_jobs, form_payload):
    client, jobs = make_jobs(lambda request: form_reply(form_payload))
    async with client:
        form = await jobs.application(JOB_URN)
    email, country, phone, licence, years, shifts, notes, start, licence_class = form.questions
    assert (email.kind, email.required, email.section) == (
        QuestionKind.DROPDOWN,
        True,
        "CONTACT_INFO",
    )
    assert email.prefilled == ("person@example.com",)
    assert country.options[0].label == "Testland (+99)"
    assert country.options[0].urn == "urn:li:country:tl" and country.options[0].value is None
    assert country.input_values == (
        {
            "entityInputValue": {
                "inputEntityName": "Testland (+99)",
                "inputEntityUrn": "urn:li:country:tl",
            }
        },
    )
    assert (phone.kind, phone.min_length, phone.max_length, phone.prefilled) == (
        QuestionKind.TEXT,
        0,
        20,
        (),
    )
    assert licence.kind is QuestionKind.SINGLE_CHOICE
    assert [(o.label, o.value) for o in licence.options] == [("Yes", "Yes"), ("No", "No")]
    assert (years.kind, years.whole_number, years.minimum, years.maximum) == (
        QuestionKind.NUMBER,
        True,
        0.0,
        99.0,
    )
    assert (shifts.kind, shifts.min_choices, shifts.max_choices) == (QuestionKind.CHECKBOX, 1, 2)
    assert notes.kind is QuestionKind.MULTILINE_TEXT and not notes.required
    assert (start.kind, start.component) == (QuestionKind.OTHER, "dateFormComponent")
    assert licence_class.conditional and licence_class.kind is QuestionKind.DROPDOWN
    assert form.question("Mobile phone number") is phone
    assert form.question(phone.id) is phone


async def test_file_slots_and_offered_resumes(make_jobs, form_payload):
    client, jobs = make_jobs(lambda request: form_reply(form_payload))
    async with client:
        form = await jobs.application(JOB_ID)
    (slot,) = form.files
    assert slot.label == "Resume" and slot.section == "RESUME" and slot.required
    assert slot.mime_types == ("DOC", "DOCX", "PDF") and slot.max_size == 2000
    assert form.file("RESUME") is slot and form.file("Resume") is slot
    (resume,) = form.resumes
    assert resume.urn == "urn:li:fsd_resume:old-1"
    assert (resume.file_name, resume.file_type, resume.size) == ("old.pdf", "PDF", 900)
    with pytest.raises(ValueError):
        form.file("COVER_LETTER")


async def test_lookups_refuse_unknown_and_ambiguous_labels(make_jobs, form_payload):
    groups = form_payload["jobApplicationForms"][2]["questionGroupings"][0]["formSection"]
    duplicate = dict(groups["formElementGroups"][0]["formElements"][0], urn="urn:li:other")
    groups["formElementGroups"][0]["formElements"].append(duplicate)
    client, jobs = make_jobs(lambda request: form_reply(form_payload))
    async with client:
        form = await jobs.application(JOB_ID)
    with pytest.raises(ValueError, match="Several"):
        form.question("Do you have a forklift licence?")
    with pytest.raises(ValueError, match="no question"):
        form.question("Favourite colour?")


async def test_forms_needing_consent_or_repeats_are_marked(make_jobs, form_payload):
    form_payload["jobApplicationForms"].append(
        {"questionGroupings": [{"questionGroupingType": "DATA_CONSENT", "formSection": {}}]}
    )
    basic = form_payload["jobApplicationForms"][2]["questionGroupings"][0]["formSection"]
    basic["repeatableSectionData"] = {"minRequiredSections": 1}
    client, jobs = make_jobs(lambda request: form_reply(form_payload))
    async with client:
        form = await jobs.application(JOB_ID)
    assert form.needs_data_consent and form.has_repeatable_sections
    assert form.questions[3].repeatable and not form.questions[0].repeatable


async def test_jobs_without_easy_apply_are_rejected(make_jobs):
    error = {
        "data": {"jobsDashOnsiteApplyApplicationByJobPosting": None},
        "errors": [{"message": "x"}],
    }
    client, jobs = make_jobs(lambda request: httpx.Response(200, json=error))
    async with client:
        with pytest.raises(OperationRejected):
            await jobs.application(JOB_ID)
    empty = {"data": {"jobsDashOnsiteApplyApplicationByJobPosting": {"elements": []}}}
    client, jobs = make_jobs(lambda request: httpx.Response(200, json=empty))
    async with client:
        with pytest.raises(ProtocolError):
            await jobs.application(JOB_ID)


def upload_handler(seen, *, url=UPLOAD_URL, status=201, location="/AbC123.pdf"):
    def handle(request):
        seen.append(request)
        if request.url.path == "/voyager/api/voyagerJobsDashAmbryUploadUrls":
            return httpx.Response(200, json={"value": url})
        headers = {"location": location} if location else {}
        return httpx.Response(status, headers=headers)

    return handle


async def test_upload_requests_a_url_then_posts_the_file_bytes(make_jobs, tmp_path):
    resume = tmp_path / "My Resume.PDF"
    resume.write_bytes(b"%PDF-1.4 synthetic")
    seen = []
    client, jobs = make_jobs(upload_handler(seen))
    async with client:
        uploaded = await jobs.upload_file(resume)
    ask, put = seen
    assert ask.method == "POST"
    assert (
        ask.url.raw_path.decode() == "/voyager/api/voyagerJobsDashAmbryUploadUrls?action=requestUrl"
    )
    assert json.loads(ask.content) == {"contentType": "PDF", "filename": "My Resume.PDF"}
    assert put.method == "POST"
    assert put.url.host == "www.linkedin.com"
    assert put.url.raw_path.decode() == "/ambry/?x-li-ambry-ep=SIGNED-TOKEN"
    assert put.headers["content-type"] == "application/pdf"
    assert put.content == b"%PDF-1.4 synthetic"
    assert uploaded.urn == "urn:li:fsd_resume:/AbC123.pdf"
    assert (uploaded.file_name, uploaded.size) == ("My Resume.PDF", 18)


async def test_upload_accepts_named_bytes_for_word_files(make_jobs):
    seen = []
    client, jobs = make_jobs(upload_handler(seen))
    async with client:
        uploaded = await jobs.upload_file(b"doc", filename="cv.docx")
    assert json.loads(seen[0].content)["contentType"] == "DOCX"
    assert uploaded.content_type.endswith("wordprocessingml.document")


@pytest.mark.parametrize(("file", "filename"), [(b"x", None), (b"x", "cv.exe"), (b"", "cv.pdf")])
async def test_upload_rejects_bad_files_before_any_request(make_jobs, file, filename):
    client, jobs = make_jobs(lambda request: pytest.fail("no request expected"))
    async with client:
        with pytest.raises(ValueError):
            await jobs.upload_file(file, filename=filename)


@pytest.mark.parametrize(
    "options",
    [
        {"url": "https://media.example.com/ambry/?x=1"},
        {"url": "http://www.linkedin.com/ambry/?x=1"},
        {"url": None},
        {"status": 200},
        {"location": None},
    ],
)
async def test_upload_refuses_other_hosts_and_unconfirmed_uploads(make_jobs, options):
    seen = []
    client, jobs = make_jobs(upload_handler(seen, **options))
    async with client:
        with pytest.raises(ProtocolError):
            await jobs.upload_file(b"%PDF", filename="cv.pdf")
    assert all(request.url.host == "www.linkedin.com" for request in seen)


async def test_upload_refuses_a_file_over_the_slot_limit_before_sending(make_jobs, tmp_path):
    seen = []
    _, jobs = make_jobs(lambda request: seen.append(request))
    resume = tmp_path / "cv.pdf"
    resume.write_bytes(b"%PDF" + b"x" * 100)
    with pytest.raises(ValueError, match="larger than 50 bytes"):
        await jobs.upload_file(resume, max_size=50)
    with pytest.raises(ValueError, match="larger than 50 bytes"):
        await jobs.upload_file(b"x" * 51, filename="cv.pdf", max_size=50)
    assert seen == []
