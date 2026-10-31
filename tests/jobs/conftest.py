"""Synthetic Voyager payloads for the jobs tests; no captured names, IDs or URNs."""

import httpx
import pytest

from async_linkedinlib import LinkedIn
from async_linkedinlib.resources.jobs import Jobs
from async_linkedinlib.transport.voyager import Voyager

JOB_ID = "1234567890"
JOB_URN = f"urn:li:fsd_jobPosting:{JOB_ID}"
ELEMENT = "urn:li:fsd_formElement:urn:li:jobs_applyformcommon_easyApplyFormElement"
FILE_ELEMENT = (
    "urn:li:fsu_jobApplicationFileUploadFormElement:"
    f"urn:li:jobs_applyformcommon_easyApplyFormElement:({JOB_ID},5,document)"
)
# base64 of the 16 bytes 0x00..0x0f
TRACKING_ID = "AAECAwQFBgcICQoLDA0ODw=="


@pytest.fixture
def make_jobs(session):
    """Build a Jobs resource whose requests go to `handle`; returns (client, jobs)."""

    def build(handle):
        client = LinkedIn(session, transport=httpx.MockTransport(handle))
        return client, Jobs(Voyager(client._transport))

    return build


def element(number, kind, title, component, *, required=True, prefilled=None, **extra):
    data = {
        "urn": f"{ELEMENT}:({JOB_ID},{number},{kind})",
        "title": {"text": title},
        "required": required,
        "formComponentResolutionResult": {component[0]: component[1]},
    }
    if prefilled is not None:
        data["input"] = {
            "formElementUrn": data["urn"],
            "formElementInputValuesResolutionResults": prefilled,
        }
    data.update(extra)
    return data


def text_option(label, value=None, urn=None):
    option = {"optionText": {"text": label}, "option": {}}
    if value is not None:
        option["option"]["optionEnumString"] = value
    if urn is not None:
        option["option"]["optionUrn"] = urn
    return option


@pytest.fixture
def form_payload():
    """An Easy Apply form: contact page, resume page and a questions page."""
    contact = [
        element(
            1,
            "multipleChoice",
            "Email address",
            (
                "textEntityListFormComponent",
                {
                    "textSelectableOptions": [
                        text_option("person@example.com", "person@example.com")
                    ],
                    "preferredRenderingStyle": "DROPDOWN",
                },
            ),
            prefilled=[{"entityInputValue": {"inputEntityName": "person@example.com"}}],
        ),
        element(
            2,
            "phoneNumber~country",
            "Phone country code",
            (
                "textEntityListFormComponent",
                {
                    "textSelectableOptions": [
                        text_option("Testland (+99)", urn="urn:li:country:tl"),
                        text_option("Otherland (+98)", urn="urn:li:country:ol"),
                    ],
                },
            ),
            prefilled=[
                {
                    "entityInputValue": {
                        "inputEntityName": "Testland (+99)",
                        "inputEntityUrn": "urn:li:country:tl",
                        "inputEntityImage": None,
                    }
                }
            ],
        ),
        element(
            3,
            "phoneNumber~nationalNumber",
            "Mobile phone number",
            (
                "singleLineTextFormComponent",
                {
                    "validationMetadataResolutionResult": {
                        "string": {
                            "characterCountRangeValidation": {"validRange": {"start": 0, "end": 20}}
                        }
                    }
                },
            ),
            prefilled=[{"textInputValue": ""}],
        ),
    ]
    questions = [
        element(
            4,
            "multipleChoice",
            "Do you have a forklift licence?",
            (
                "radioButtonFormComponent",
                {
                    "selectableOptionsResolutionResults": [
                        {"textSelectableOption": text_option("Yes", "Yes")},
                        {"textSelectableOption": text_option("No", "No")},
                    ]
                },
            ),
        ),
        element(
            6,
            "numeric",
            "Years of experience?",
            (
                "singleLineTextFormComponent",
                {
                    "validationMetadataResolutionResult": {
                        "integer": {
                            "numericValueRangeValidation": {"validRange": {"start": 0, "end": 99}}
                        }
                    }
                },
            ),
        ),
        element(
            7,
            "multipleChoice",
            "Which shifts suit you?",
            (
                "checkboxFormComponent",
                {
                    "textSelectableOptions": [
                        text_option("Morning", "MORNING"),
                        text_option("Evening", "EVENING"),
                        text_option("Night", "NIGHT"),
                    ],
                    "selectionCountRangeValidation": {"validRange": {"start": 1, "end": 2}},
                },
            ),
            required=False,
        ),
        element(
            8,
            "text",
            "Anything else?",
            ("multilineTextFormComponent", {}),
            required=False,
        ),
        element(
            9,
            "date",
            "Start date",
            ("dateFormComponent", {"dateInputType": "YEAR_MONTH"}),
            required=False,
        ),
        element(
            10,
            "multipleChoice",
            "Which licence class?",
            ("dropdownFormComponent", {"textSelectableOptions": [text_option("B", "B")]}),
            prerequisiteFormElementInputs=[{"formElementUrn": "x"}],
        ),
    ]
    return {
        "entityUrn": f"urn:li:fsd_onsiteApplyApplication:{JOB_ID}",
        "jobSeekerApplicationDetail": {"applied": False, "onsiteApply": True},
        "jobPosting": {"entityUrn": JOB_URN, "companyDetails": {"name": "Example Foods"}},
        "jobApplicationForms": [
            {
                "questionGroupings": [
                    {
                        "prefilled": True,
                        "questionGroupingType": "CONTACT_INFO",
                        "formSection": {"formElementGroups": [{"formElements": contact}]},
                    }
                ]
            },
            {
                "questionGroupings": [
                    {
                        "prefilled": False,
                        "questionGroupingType": "RESUME",
                        "customizedFormSection": {
                            "fileUploadFormSection": {
                                "title": "Resume",
                                "fileUploadFormElement": {
                                    "formElementUrn": FILE_ELEMENT,
                                    "title": "Include an updated resume",
                                    "required": True,
                                    "mimeTypes": ["DOC", "DOCX", "PDF"],
                                    "maximumFileSizeSupported": 2000,
                                },
                            }
                        },
                        "usedResumesResolutionResults": [
                            {
                                "entityUrn": "urn:li:fsd_resume:old-1",
                                "fileName": "old.pdf",
                                "fileType": "PDF",
                                "fileSize": 900,
                                "createdAt": 1700000000000,
                                "lastUsedAt": 1700000500000,
                            }
                        ],
                    }
                ]
            },
            {
                "questionGroupings": [
                    {
                        "prefilled": False,
                        "questionGroupingType": "BASIC",
                        "formSection": {
                            "title": {"text": "Additional Questions"},
                            "formElementGroups": [{"formElements": questions}],
                        },
                    }
                ]
            },
        ],
    }
