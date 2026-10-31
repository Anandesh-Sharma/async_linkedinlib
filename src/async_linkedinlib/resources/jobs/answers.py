"""Check answers against an Easy Apply form and encode the app's `submitApplication` body.

Encoding follows the app's FormsResponseBuilderUtils and JobApplyFeature:
- text and numbers are sent trimmed as `textInputValue`;
- a choice is an `entityInputValue` with the option's enum string as `inputEntityName`, or
  its label plus `inputEntityUrn` when it has no enum string;
- each response repeats its values as `formElementInputValues` and
  `formElementInputValuesResolutionResults`;
- a question left unanswered keeps LinkedIn's prefilled values when they are complete;
- file slots are answered with `{formElementUrn, inputUrn}` in `fileUploadResponses`.
The body starts with `followCompany`, `referenceId` and `trackingCode` (empty strings when
unknown, as the app sends them) and the job's tracking ID as a 16-character byte string.
Forms that need a data-consent step or repeatable sections are refused.
"""

import base64
import binascii
import math
import re
from collections.abc import Mapping
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from ...models.jobs_apply import ApplicationForm
from ...models.jobs_apply import FileQuestion
from ...models.jobs_apply import Option
from ...models.jobs_apply import Question
from ...models.jobs_apply import QuestionKind
from ...models.jobs_apply import Resume
from ...models.jobs_apply import Submission
from ...models.jobs_apply import UploadedFile
from .upload import DOCUMENT_TYPES

_DECIMAL = re.compile(r"-?[0-9]+(\.[0-9]+)?")

Answer = str | int | float | Sequence[str]
FileAnswer = str | UploadedFile | Resume

_TEXT = frozenset({QuestionKind.TEXT, QuestionKind.MULTILINE_TEXT, QuestionKind.NUMBER})
_CHOICE = frozenset({QuestionKind.SINGLE_CHOICE, QuestionKind.DROPDOWN, QuestionKind.CHECKBOX})


def build(
    form: ApplicationForm,
    answers: Mapping[str, Answer],
    files: Mapping[str, FileAnswer] | None = None,
    *,
    follow_company: bool = False,
    reference_id: str | None = None,
    tracking_id: str | None = None,
) -> Submission:
    if form.needs_data_consent:
        raise ValueError("This form asks for data consent first, which this client does not send.")
    if form.has_repeatable_sections:
        raise ValueError("This form has repeatable sections, which this client does not build.")
    chosen: dict[str, list[dict[str, Any]]] = {}
    for key, value in answers.items():
        question = form.question(key)
        if question.id in chosen:
            raise ValueError(f"{_name(question)} is answered twice.")
        chosen[question.id] = _values(question, value)
    responses: list[dict[str, Any]] = []
    shown: list[tuple[str, tuple[str, ...]]] = []
    missing: list[str] = []
    for question in form.questions:
        values = chosen.get(question.id) or _prefilled(question)
        if values:
            responses.append(_response(question.id, values))
            shown.append((question.label or question.id, tuple(_display(v) for v in values)))
        elif question.required and not question.conditional:
            missing.append(_name(question))
    picked = {}
    for key, attached in (files or {}).items():
        slot = form.file(key)
        picked[slot.id] = _file_urn(slot, attached)
    uploads = []
    for slot in form.files:
        urn = picked.get(slot.id) or slot.prefilled
        if urn:
            uploads.append({"formElementUrn": slot.id, "inputUrn": urn})
            shown.append((slot.label or slot.id, (urn,)))
        elif slot.required:
            missing.append(slot.label or slot.id)
    if missing:
        raise ValueError("Answer the required questions: " + "; ".join(missing))
    body: dict[str, Any] = {
        "followCompany": bool(follow_company),
        "referenceId": reference_id or "",
        # The app's `trk` code from the screen that opened the job; empty when none.
        "trackingCode": "",
    }
    if tracking := tracking_bytes(tracking_id):
        body["trackingId"] = tracking
    body["responses"] = responses
    body["fileUploadResponses"] = uploads
    return Submission(job_id=form.job_id, body=body, answers=tuple(shown))


def tracking_bytes(tracking_id: str | None) -> str | None:
    """The app's TrackingUtils: a base64 tracking ID as its 16 bytes, one char per byte."""
    if not tracking_id:
        return None
    try:
        raw = base64.b64decode(tracking_id, validate=True)
    except (binascii.Error, ValueError):
        return None
    return raw[:16].decode("latin-1") if len(raw) >= 16 else None


def _values(question: Question, value: Answer) -> list[dict[str, Any]]:
    if question.kind is QuestionKind.OTHER:
        raise ValueError(
            f"{_name(question)} uses {question.component}, which this client cannot answer."
        )
    if question.kind is QuestionKind.NUMBER:
        return [{"textInputValue": _number(question, value)}]
    if question.kind in _TEXT:
        if not isinstance(value, str):
            raise ValueError(f"{_name(question)} takes text.")
        answer = value.strip()
        if not answer:
            raise ValueError(f"{_name(question)} is empty.")
        # Android counts text in UTF-16 units, so an emoji uses two of the limit.
        length = len(answer.encode("utf-16-le")) // 2
        if question.max_length is not None and length > question.max_length:
            raise ValueError(f"{_name(question)} allows at most {question.max_length} characters.")
        if question.min_length is not None and length < question.min_length:
            raise ValueError(f"{_name(question)} needs at least {question.min_length} characters.")
        return [{"textInputValue": answer}]
    if isinstance(value, int | float):
        raise ValueError(f"{_name(question)} takes the label of one of its options.")
    picks = [value] if isinstance(value, str) else list(value)
    if not all(isinstance(pick, str) for pick in picks):
        raise ValueError(f"{_name(question)} takes the label of one of its options.")
    options = list(dict.fromkeys(_option(question, pick) for pick in picks))
    if not options:
        raise ValueError(f"{_name(question)} needs a choice.")
    if question.kind is not QuestionKind.CHECKBOX and len(options) > 1:
        raise ValueError(f"{_name(question)} takes one choice.")
    if question.max_choices is not None and len(options) > question.max_choices:
        raise ValueError(f"{_name(question)} allows at most {question.max_choices} choices.")
    if question.min_choices is not None and len(options) < question.min_choices:
        raise ValueError(f"{_name(question)} needs at least {question.min_choices} choices.")
    return [{"entityInputValue": _entity(option)} for option in options]


def _number(question: Question, value: Answer) -> str:
    """The number as the app sends it; text must be a plain decimal such as -12 or 3.5."""
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise ValueError(f"{_name(question)} takes a number.")
    if isinstance(value, str):
        if not _DECIMAL.fullmatch(value.strip()):
            raise ValueError(f"{_name(question)} takes a plain decimal number.")
        number = Decimal(value.strip())
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{_name(question)} takes a finite number.")
    else:
        number = Decimal(repr(value)) if isinstance(value, float) else Decimal(value)
    if question.whole_number and number != number.to_integral_value():
        raise ValueError(f"{_name(question)} takes a whole number.")
    if question.minimum is not None and number < Decimal(repr(question.minimum)):
        raise ValueError(f"{_name(question)} must be at least {question.minimum:g}.")
    if question.maximum is not None and number > Decimal(repr(question.maximum)):
        raise ValueError(f"{_name(question)} must be at most {question.maximum:g}.")
    return format(number.normalize(), "f")


def _option(question: Question, pick: str) -> Option:
    # A label wins over an enum string, which wins over a URN.
    for attribute in ("label", "value", "urn"):
        found = [option for option in question.options if getattr(option, attribute) == pick]
        if found:
            return found[0]
    labels = ", ".join(repr(option.label) for option in question.options[:10])
    raise ValueError(f"{_name(question)} has no option {pick!r}; options: {labels}")


def _entity(option: Option) -> dict[str, str]:
    if option.value is not None:
        return {"inputEntityName": option.value}
    entity = {}
    if option.label is not None:
        entity["inputEntityName"] = option.label
    if option.urn is not None:
        entity["inputEntityUrn"] = option.urn
    return entity


def _prefilled(question: Question) -> list[dict[str, Any]]:
    """LinkedIn's prefill when complete enough to send, as the app checks before sending."""
    values = list(question.input_values)
    if not values:
        return []
    if question.kind in _TEXT:
        first = values[0].get("textInputValue")
        if not isinstance(first, str) or not first:
            return []
        if question.max_length is not None and len(first) > question.max_length:
            return []
    elif question.kind in _CHOICE and not all(value.get("entityInputValue") for value in values):
        return []
    return values


def _file_urn(slot: FileQuestion, value: FileAnswer) -> str:
    if isinstance(value, Resume):
        return value.urn
    if isinstance(value, UploadedFile):
        kinds = [kind for kind, mime in DOCUMENT_TYPES.items() if mime == value.content_type]
        if slot.mime_types and not set(kinds) & set(slot.mime_types):
            raise ValueError(f"{slot.label or slot.id} accepts {', '.join(slot.mime_types)} files.")
        if slot.max_size is not None and value.size > slot.max_size:
            raise ValueError(f"{slot.label or slot.id} accepts files up to {slot.max_size} bytes.")
        return value.urn
    if isinstance(value, str) and value.startswith("urn:li:"):
        return value
    raise ValueError("A file slot takes an UploadedFile, a Resume or a resume URN.")


def _response(urn: str, values: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "formElementUrn": urn,
        "formElementInputValues": values,
        "formElementInputValuesResolutionResults": values,
    }


def _display(value: dict[str, Any]) -> str:
    if isinstance(value.get("textInputValue"), str):
        return str(value["textInputValue"])
    entity = value.get("entityInputValue")
    if isinstance(entity, dict):
        return str(entity.get("inputEntityName") or entity.get("inputEntityUrn") or "")
    return str(next(iter(value.values()), ""))


def _name(question: Question) -> str:
    return repr(question.label) if question.label else question.id
