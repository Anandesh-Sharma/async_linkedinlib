"""Easy Apply forms, their questions and file slots, uploads and the submission to send.

The form is the app's `OnsiteApplyApplication`: pages (question groupings) of form elements
whose `formComponent` decides how they are answered, plus file slots for a resume or cover
letter. Prefilled answers keep the server's own input values, which the app sends back.
"""

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from enum import StrEnum
from typing import Any
from typing import TypeVar

from ._json import boolean
from ._json import dig
from ._json import epoch_ms
from ._json import integer
from ._json import items
from ._json import obj
from ._json import string
from ._json import text

T = TypeVar("T")


class QuestionKind(StrEnum):
    """How a question is answered; OTHER covers components this client cannot answer."""

    TEXT = "TEXT"
    MULTILINE_TEXT = "MULTILINE_TEXT"
    NUMBER = "NUMBER"
    SINGLE_CHOICE = "SINGLE_CHOICE"
    DROPDOWN = "DROPDOWN"
    CHECKBOX = "CHECKBOX"
    OTHER = "OTHER"


_KINDS = {
    "singleLineTextFormComponent": QuestionKind.TEXT,
    "multilineTextFormComponent": QuestionKind.MULTILINE_TEXT,
    "numberInputFormComponent": QuestionKind.NUMBER,
    "radioButtonFormComponent": QuestionKind.SINGLE_CHOICE,
    "dropdownFormComponent": QuestionKind.DROPDOWN,
    "textEntityListFormComponent": QuestionKind.DROPDOWN,
    "checkboxFormComponent": QuestionKind.CHECKBOX,
}


@dataclass(frozen=True, slots=True)
class Option:
    """One choice: its shown label and the enum string or URN the app answers with."""

    label: str | None
    value: str | None = None
    urn: str | None = None


@dataclass(frozen=True, slots=True)
class Question:
    """One form element.

    `id` is the form element URN that answers address. `prefilled` shows the answer LinkedIn
    filled in (text or option names). `min_length`/`max_length` bound text, `minimum`/
    `maximum` bound numbers and `min_choices`/`max_choices` bound checkbox selections when
    the form says so. `whole_number` marks numbers without decimals. A `conditional`
    question is only shown after certain answers elsewhere; it is never treated as required.
    """

    id: str
    label: str | None
    kind: QuestionKind
    component: str | None
    required: bool
    section: str | None = None
    options: tuple[Option, ...] = ()
    prefilled: tuple[str, ...] = field(default=(), repr=False)
    min_length: int | None = None
    max_length: int | None = None
    minimum: float | None = None
    maximum: float | None = None
    whole_number: bool = False
    min_choices: int | None = None
    max_choices: int | None = None
    conditional: bool = False
    repeatable: bool = False
    # The server's input values, sent back unchanged when the question keeps its prefill.
    input_values: tuple[dict[str, Any], ...] = field(default=(), repr=False, compare=False)
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_element(
        cls, element: dict[str, Any], section: str | None, repeatable: bool
    ) -> "Question | None":
        urn = string(element, "urn") or string(element, "entityUrn")
        if not urn:
            return None
        components = obj(element.get("formComponentResolutionResult")) or obj(
            element.get("formComponent")
        )
        name = next((key for key, value in components.items() if isinstance(value, dict)), None)
        component = obj(components.get(name)) if name else {}
        kind = _KINDS.get(name or "", QuestionKind.OTHER)
        validation = obj(component.get("validationMetadataResolutionResult")) or obj(
            component.get("validationMetadata")
        )
        numeric = obj(validation.get("integer")) or obj(validation.get("decimal"))
        if kind is QuestionKind.TEXT and numeric:
            kind = QuestionKind.NUMBER
        characters = obj(dig(validation, "string", "characterCountRangeValidation")) or obj(
            dig(validation, "url", "characterCountRangeValidation")
        )
        number_range = obj(numeric.get("numericValueRangeValidation")) or obj(
            component.get("numericRangeValidation")
        )
        choices = obj(component.get("selectionCountRangeValidation"))
        values = tuple(
            _clean(value)
            for value in items(dig(element, "input", "formElementInputValuesResolutionResults"))
        )
        digits = integer(component, "numFractionalDigits")
        return cls(
            id=urn,
            label=text(element, "title"),
            kind=kind,
            component=name,
            required=boolean(element, "required") is True,
            section=section,
            options=_options(component),
            prefilled=tuple(shown for value in values if (shown := _shown(value))),
            min_length=integer(characters, "validRange", "start"),
            max_length=integer(characters, "validRange", "end"),
            minimum=_number(dig(number_range, "validRange", "start")),
            maximum=_number(dig(number_range, "validRange", "end")),
            whole_number=bool(validation.get("integer"))
            or (name == "numberInputFormComponent" and not digits),
            min_choices=integer(choices, "validRange", "start"),
            max_choices=integer(choices, "validRange", "end"),
            conditional=any(
                element.get(key)
                for key in (
                    "prerequisiteFormElementInputs",
                    "prerequisiteInputEvaluationStrategy",
                    "prerequisiteInputEvaluationStrategyUnion",
                )
            ),
            repeatable=repeatable,
            input_values=values,
            raw=deepcopy(element),
        )


@dataclass(frozen=True, slots=True)
class FileQuestion:
    """A file slot such as the resume; `id` is the upload form element URN it answers.

    `prefilled` is the resume URN LinkedIn preselected, if any. `mime_types` are the app's
    names (PDF, DOC, DOCX) and `max_size` is in bytes.
    """

    id: str
    label: str | None
    section: str | None
    required: bool
    mime_types: tuple[str, ...]
    max_size: int | None
    prefilled: str | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class Resume:
    """A resume LinkedIn offers from earlier applications; `urn` answers a file slot."""

    urn: str
    file_name: str | None
    file_type: str | None
    size: int | None
    created_at: datetime | None
    last_used_at: datetime | None
    download_url: str | None = field(default=None, repr=False)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Resume | None":
        urn = string(data, "entityUrn")
        if not urn:
            return None
        # The app answers with an fsd_resume URN built from the resume's own ID.
        resume_id = urn.split(":", 3)[3] if urn.count(":") >= 3 else urn
        return cls(
            urn=f"urn:li:fsd_resume:{resume_id}",
            file_name=string(data, "fileName"),
            file_type=string(data, "fileType"),
            size=integer(data, "fileSize"),
            created_at=epoch_ms(integer(data, "createdAt")),
            last_used_at=epoch_ms(integer(data, "lastUsedAt")),
            download_url=string(data, "downloadUrl"),
        )


@dataclass(frozen=True, slots=True)
class UploadedFile:
    """A file stored for an application; its `urn` answers a file slot.

    Uploading attaches the file to nothing: it is used only when a submission names it.
    LinkedIn's app offers no way to delete an uploaded file.
    """

    urn: str
    file_name: str
    content_type: str
    size: int


@dataclass(frozen=True, slots=True)
class FormPage:
    """One page of the form (a question grouping such as CONTACT_INFO, RESUME or BASIC)."""

    section: str | None
    title: str | None
    questions: tuple[Question, ...]
    files: tuple[FileQuestion, ...]
    prefilled: bool | None = None


@dataclass(frozen=True, slots=True)
class ApplicationForm:
    """The Easy Apply form of one job, read without starting or submitting anything.

    `resumes` are resumes from earlier applications that LinkedIn offers again.
    `needs_data_consent` and `has_repeatable_sections` mark forms whose extra steps this
    client does not build, so a submission for them is refused.
    """

    job_id: str
    company: str | None
    applied: bool | None
    pages: tuple[FormPage, ...]
    resumes: tuple[Resume, ...]
    needs_data_consent: bool = False
    has_repeatable_sections: bool = False
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def questions(self) -> tuple[Question, ...]:
        return tuple(question for page in self.pages for question in page.questions)

    @property
    def files(self) -> tuple[FileQuestion, ...]:
        return tuple(slot for page in self.pages for slot in page.files)

    def question(self, key: str) -> Question:
        """Find a question by its URN, or by its exact label when that label is unique."""
        return _find(self.questions, key, "question", lambda entry: (entry.label,))

    def file(self, key: str) -> FileQuestion:
        """Find a file slot by its URN, its section (RESUME) or its exact label."""
        return _find(self.files, key, "file slot", lambda entry: (entry.label, entry.section))

    @classmethod
    def from_json(cls, job_id: str, application: dict[str, Any]) -> "ApplicationForm":
        pages: list[FormPage] = []
        resumes: dict[str, Resume] = {}
        repeatable_seen = False
        for form in items(application.get("jobApplicationForms")):
            for grouping in items(form.get("questionGroupings")):
                section = string(grouping, "questionGroupingType")
                form_section = obj(grouping.get("formSection"))
                repeatable = bool(form_section.get("repeatableSectionData"))
                repeatable_seen = repeatable_seen or repeatable
                questions = [
                    question
                    for element in _elements(form_section)
                    if (question := Question.from_element(element, section, repeatable))
                ]
                upload = obj(grouping.get("fileUploadFormSection")) or obj(
                    dig(grouping, "customizedFormSection", "fileUploadFormSection")
                )
                slot = _file_question(upload, section)
                for data in items(grouping.get("usedResumesResolutionResults")):
                    if resume := Resume.from_json(data):
                        resumes.setdefault(resume.urn, resume)
                pages.append(
                    FormPage(
                        section=section,
                        title=text(form_section, "title") or string(upload, "title"),
                        questions=tuple(questions),
                        files=(slot,) if slot else (),
                        prefilled=boolean(grouping, "prefilled"),
                    )
                )
        return cls(
            job_id=job_id,
            company=string(application, "jobPosting", "companyDetails", "name"),
            applied=boolean(application, "jobSeekerApplicationDetail", "applied"),
            pages=tuple(pages),
            resumes=tuple(resumes.values()),
            needs_data_consent=any(page.section == "DATA_CONSENT" for page in pages),
            has_repeatable_sections=repeatable_seen,
            raw=deepcopy(application),
        )


@dataclass(frozen=True, slots=True)
class Submission:
    """The exact `submitApplication` body for one job; building it sends nothing.

    `answers` lists every value sent, in form order, as (question or file slot label,
    values) pairs for review before submitting; two questions with the same label stay
    separate. Neither the body nor the answers appear in the repr.
    """

    job_id: str
    body: dict[str, Any] = field(repr=False)
    answers: tuple[tuple[str, tuple[str, ...]], ...] = field(default=(), repr=False)


@dataclass(frozen=True, slots=True)
class ApplicationStatus:
    """The viewer's application state for a job after a submission."""

    applied: bool | None
    applied_at: datetime | None
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_json(cls, detail: dict[str, Any]) -> "ApplicationStatus":
        return cls(
            applied=boolean(detail, "applied"),
            applied_at=epoch_ms(integer(detail, "appliedAt")),
            raw=deepcopy(detail),
        )


def _elements(form_section: dict[str, Any]) -> list[dict[str, Any]]:
    found = items(form_section.get("formElements"))
    for group in items(form_section.get("formElementGroups")):
        found.extend(items(group.get("formElements")))
    return found


def _options(component: dict[str, Any]) -> tuple[Option, ...]:
    options = items(component.get("textSelectableOptions"))
    for entry in items(component.get("selectableOptionsResolutionResults")) + items(
        component.get("selectableOptions")
    ):
        options.append(
            obj(entry.get("textSelectableOption")) or obj(entry.get("entitySelectableOption"))
        )
    if exclusive := obj(component.get("exclusiveSelectableOption")):
        options.append(exclusive)
    return tuple(
        Option(
            label=text(option, "optionText"),
            value=string(option, "option", "optionEnumString")
            or string(option, "optionUnion", "optionEnumString")
            or string(option, "optionEnumString"),
            urn=string(option, "option", "optionUrn")
            or string(option, "optionUnion", "optionUrn")
            or string(option, "optionUrn"),
        )
        for option in options
        if option
    )


def _file_question(upload: dict[str, Any], section: str | None) -> FileQuestion | None:
    element = obj(upload.get("fileUploadFormElement"))
    urn = string(element, "formElementUrn")
    if not urn:
        return None
    return FileQuestion(
        id=urn,
        label=string(upload, "title") or string(element, "title"),
        section=section,
        required=boolean(element, "required") is True,
        mime_types=tuple(kind for kind in element.get("mimeTypes") or [] if isinstance(kind, str)),
        max_size=integer(element, "maximumFileSizeSupported"),
        prefilled=string(element, "input", "inputUrn"),
    )


def _find(
    entries: tuple[T, ...], key: str, what: str, names: Callable[[T], tuple[str | None, ...]]
) -> T:
    if not isinstance(key, str) or not key:
        raise ValueError(f"A {what} URN or label is required.")
    for entry in entries:
        if getattr(entry, "id", None) == key:
            return entry
    matches = [entry for entry in entries if key in names(entry)]
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise ValueError(f"Several entries match {key!r}; use the {what} URN.")
    raise ValueError(f"The form has no {what} {key!r}.")


def _clean(value: Any) -> Any:
    """Drop null members, as the app's serializer does when sending values back."""
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_clean(item) for item in value]
    return value


def _shown(value: dict[str, Any]) -> str | None:
    shown = value.get("textInputValue")
    if isinstance(shown, str):
        return shown or None
    entity = obj(value.get("entityInputValue"))
    name = entity.get("inputEntityName") or entity.get("inputEntityUrn")
    if isinstance(name, str):
        return name
    for key in ("integerInputValue", "floatInputValue", "booleanInputValue", "urnInputValue"):
        if value.get(key) is not None:
            return str(value[key])
    return None


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None
