import json

import httpx
import pytest

from async_linkedinlib.models.jobs import Job
from async_linkedinlib.models.jobs_apply import ApplicationForm
from async_linkedinlib.models.jobs_apply import Submission
from async_linkedinlib.models.jobs_apply import UploadedFile

JOB_ID = "1234567890"
ELEMENT = "urn:li:fsd_formElement:urn:li:jobs_applyformcommon_easyApplyFormElement"
FILE_ELEMENT = (
    "urn:li:fsu_jobApplicationFileUploadFormElement:"
    f"urn:li:jobs_applyformcommon_easyApplyFormElement:({JOB_ID},5,document)"
)
EMAIL = {"inputEntityName": "person@example.com"}
COUNTRY = {"inputEntityName": "Testland (+99)", "inputEntityUrn": "urn:li:country:tl"}
UPLOAD = UploadedFile("urn:li:fsd_resume:/AbC123.pdf", "cv.pdf", "application/pdf", 900)
ANSWERS = {
    "Mobile phone number": " 5550100 ",
    "Do you have a forklift licence?": "No",
    "Years of experience?": 4,
}


def urn(number, kind):
    return f"{ELEMENT}:({JOB_ID},{number},{kind})"


def response(element, values):
    return {
        "formElementUrn": element,
        "formElementInputValues": values,
        "formElementInputValuesResolutionResults": values,
    }


@pytest.fixture
def form(form_payload):
    return ApplicationForm.from_json(JOB_ID, form_payload)


@pytest.fixture
def job():
    return Job(
        id=JOB_ID,
        urn=f"urn:li:fsd_jobPosting:{JOB_ID}",
        **dict.fromkeys(
            [
                "title", "company", "company_urn", "location", "location_urn",
                "employment_type", "description", "listed_at", "applicants",
                "applicants_text", "state", "easy_apply", "apply_url", "applied",
                "applied_at", "saved", "url",
            ]
        ),
        workplace_types=(),
        reference_id="ref==",
        tracking_id="AAECAwQFBgcICQoLDA0ODw==",
    )  # fmt: skip


def test_submission_body_matches_the_app(make_jobs, form, job):
    _, jobs = make_jobs(lambda request: pytest.fail("building sends nothing"))
    submission = jobs.submission(
        form,
        dict(ANSWERS, **{"Which shifts suit you?": ["Morning", "NIGHT", "Morning"]}),
        files={"Resume": UPLOAD},
        job=job,
        follow_company=True,
    )
    assert submission.job_id == JOB_ID
    assert submission.body == {
        "followCompany": True,
        "referenceId": "ref==",
        "trackingCode": "",
        "trackingId": "".join(chr(byte) for byte in range(16)),
        "responses": [
            response(urn(1, "multipleChoice"), [{"entityInputValue": EMAIL}]),
            response(urn(2, "phoneNumber~country"), [{"entityInputValue": COUNTRY}]),
            response(urn(3, "phoneNumber~nationalNumber"), [{"textInputValue": "5550100"}]),
            response(urn(4, "multipleChoice"), [{"entityInputValue": {"inputEntityName": "No"}}]),
            response(urn(6, "numeric"), [{"textInputValue": "4"}]),
            response(
                urn(7, "multipleChoice"),
                [
                    {"entityInputValue": {"inputEntityName": "MORNING"}},
                    {"entityInputValue": {"inputEntityName": "NIGHT"}},
                ],
            ),
        ],
        "fileUploadResponses": [{"formElementUrn": FILE_ELEMENT, "inputUrn": UPLOAD.urn}],
    }  # fmt: skip
    review = dict(submission.answers)
    assert review["Mobile phone number"] == ("5550100",)
    assert review["Resume"] == (UPLOAD.urn,)
    assert "5550100" not in repr(submission)


def test_choices_without_enum_strings_send_label_and_urn(make_jobs, form):
    _, jobs = make_jobs(lambda request: None)
    submission = jobs.submission(
        form, dict(ANSWERS, **{"Phone country code": "Otherland (+98)"}), files={"RESUME": UPLOAD}
    )
    assert submission.body["responses"][1]["formElementInputValues"] == [
        {
            "entityInputValue": {
                "inputEntityName": "Otherland (+98)",
                "inputEntityUrn": "urn:li:country:ol",
            }
        }
    ]
    assert submission.body["referenceId"] == "" and "trackingId" not in submission.body
    assert submission.body["followCompany"] is False


def test_offered_resumes_and_resume_urns_answer_file_slots(make_jobs, form):
    _, jobs = make_jobs(lambda request: None)
    for attached in (form.resumes[0], "urn:li:fsd_resume:old-1"):
        submission = jobs.submission(form, ANSWERS, files={FILE_ELEMENT: attached})
        assert submission.body["fileUploadResponses"][0]["inputUrn"] == "urn:li:fsd_resume:old-1"


def test_required_questions_and_files_must_be_answered(make_jobs, form):
    _, jobs = make_jobs(lambda request: None)
    with pytest.raises(ValueError) as error:
        jobs.submission(form, {"Do you have a forklift licence?": "Yes"})
    message = str(error.value)
    assert "Mobile phone number" in message and "Years of experience?" in message
    assert "Resume" in message
    # The conditional question is never forced; the email keeps its prefill.
    assert "Which licence class?" not in message and "Email address" not in message


@pytest.mark.parametrize(
    ("key", "value", "match"),
    [
        ("Do you have a forklift licence?", "Maybe", "no option"),
        ("Do you have a forklift licence?", ["Yes", "No"], "one choice"),
        ("Do you have a forklift licence?", 1, "label"),
        ("Mobile phone number", "5" * 21, "at most 20"),
        ("Mobile phone number", 5550100, "takes text"),
        ("Mobile phone number", "   ", "empty"),
        ("Years of experience?", 2.5, "whole number"),
        ("Years of experience?", "100", "at most 99"),
        ("Years of experience?", "-1", "at least 0"),
        ("Years of experience?", "many", "takes a plain decimal number"),
        ("Years of experience?", True, "takes a number"),
        ("Which shifts suit you?", ["Morning", "Evening", "Night"], "at most 2"),
        ("Which shifts suit you?", [], "needs a choice"),
        ("Start date", "2030-01", "cannot answer"),
        ("Favourite colour?", "Blue", "no question"),
    ],
)
def test_answers_are_checked_against_each_question(make_jobs, form, key, value, match):
    _, jobs = make_jobs(lambda request: None)
    with pytest.raises(ValueError, match=match):
        jobs.submission(form, dict(ANSWERS, **{key: value}), files={"Resume": UPLOAD})


def test_one_question_cannot_be_answered_twice(make_jobs, form):
    _, jobs = make_jobs(lambda request: None)
    phone = form.question("Mobile phone number").id
    with pytest.raises(ValueError, match="twice"):
        jobs.submission(form, dict(ANSWERS, **{phone: "5550101"}), files={"Resume": UPLOAD})


@pytest.mark.parametrize(
    "attached",
    [
        UploadedFile("urn:li:fsd_resume:/x.pdf", "cv.pdf", "application/pdf", 2001),
        UploadedFile("urn:li:fsd_resume:/x.txt", "cv.txt", "text/plain", 10),
        "not-a-urn",
    ],
)
def test_file_slots_check_type_and_size(make_jobs, form, attached):
    _, jobs = make_jobs(lambda request: None)
    with pytest.raises(ValueError):
        jobs.submission(form, ANSWERS, files={"Resume": attached})


def test_unsupported_forms_and_mismatched_jobs_are_refused(make_jobs, form_payload, job):
    _, jobs = make_jobs(lambda request: None)
    other = ApplicationForm.from_json("42", form_payload)
    with pytest.raises(ValueError, match="different jobs"):
        jobs.submission(other, ANSWERS, files={"Resume": UPLOAD}, job=job)
    form_payload["jobApplicationForms"].append(
        {"questionGroupings": [{"questionGroupingType": "DATA_CONSENT"}]}
    )
    consent = ApplicationForm.from_json(JOB_ID, form_payload)
    with pytest.raises(ValueError, match="consent"):
        jobs.submission(consent, ANSWERS, files={"Resume": UPLOAD})


async def test_submit_posts_the_built_body_once(make_jobs, form):
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(200, json={"value": {"applied": True, "appliedAt": 1700000000000}})

    client, jobs = make_jobs(handle)
    submission = jobs.submission(form, ANSWERS, files={"Resume": UPLOAD})
    async with client:
        status = await jobs.submit(submission)
    (request,) = seen
    assert request.method == "POST"
    assert request.url.raw_path.decode() == (
        "/voyager/api/voyagerJobsDashOnsiteApplyApplication?action=submitApplication"
    )
    assert request.headers["accept"] == "application/json"
    assert json.loads(request.content) == submission.body
    assert status.applied is True and status.applied_at.year == 2023


async def test_submit_failures_are_not_retried(make_jobs, form):
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(400, json={"message": "Application form is invalid"})

    client, jobs = make_jobs(handle)
    submission = jobs.submission(form, ANSWERS, files={"Resume": UPLOAD})
    async with client:
        with pytest.raises(Exception, match="Application form is invalid"):
            await jobs.submit(submission)
        with pytest.raises(ValueError):
            await jobs.submit(submission.body)
        with pytest.raises(ValueError):
            await jobs.submit(Submission("not-a-job", {}))
    assert len(seen) == 1


@pytest.mark.parametrize("value", ["1_000", "1e3", "+5", "5.", "0x10"])
def test_number_text_must_be_a_plain_decimal(make_jobs, form, value):
    _, jobs = make_jobs(lambda request: None)
    with pytest.raises(ValueError, match="plain decimal"):
        jobs.submission(
            form, dict(ANSWERS, **{"Years of experience?": value}), files={"Resume": UPLOAD}
        )


def test_numbers_are_sent_normalised(make_jobs, form):
    _, jobs = make_jobs(lambda request: None)
    answers = dict(ANSWERS, **{"Years of experience?": " 07 "})
    submission = jobs.submission(form, answers, files={"Resume": UPLOAD})
    assert ("Years of experience?", ("7",)) in submission.answers
