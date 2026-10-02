import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError

_comprehend = None
_bedrock = None


def _comprehend_client():
    global _comprehend
    _comprehend = _comprehend or boto3.client("comprehend")
    return _comprehend


def _bedrock_client():
    global _bedrock
    _bedrock = _bedrock or boto3.client("bedrock-runtime")
    return _bedrock


# allow-list: the SMS vendor gets a payload built from scratch
# out of named fields. A new field added to the record later (e.g. date of birth)
# is excluded by default instead of leaking until someone remembers to block it
PARTNER_FIELDS = {"phone"}
# Record fields the message body may still mention (where to collect a hold).
BODY_MAY_MENTION = {"branch"}


def _record_values(value) -> list[str]:
    if isinstance(value, dict):
        return [s for k, v in value.items() if k not in BODY_MAY_MENTION
                for s in _record_values(v)]
    if isinstance(value, list):
        return [s for v in value for s in _record_values(v)]
    return [str(value)]


def for_partner(record: dict, message: str) -> dict:
    """Build the payload for the SMS vendor. The vendor needs a number to text
    and a body to send; it does not need to know who the member is or what they
    borrowed. Raises PermissionError rather than sending anything doubtful."""
    payload = {k: record[k] for k in PARTNER_FIELDS}

    # The body is written by the model, so it is the one place PII can ride
    # along. First: no value from this record outside the allow-list may appear
    # in it (catches the book title, which no PII detector would flag).
    for value in _record_values({k: v for k, v in record.items() if k not in PARTNER_FIELDS}):
        if value and value.lower() in message.lower():
            raise PermissionError("message repeats a field the vendor may not see")

    # Second: ApplyGuardrail is a decision API, and this is a yes/no question:
    # may this text leave the building? Unavailable guardrail => do not send.
    guardrail_id = os.environ.get("GUARDRAIL_ID")
    if not guardrail_id:
        raise PermissionError("no guardrail configured")
    try:
        resp = _bedrock_client().apply_guardrail(
            guardrailIdentifier=guardrail_id,
            guardrailVersion=os.environ.get("GUARDRAIL_VERSION", "DRAFT"),
            source="OUTPUT",
            content=[{"text": {"text": message}}],
        )
    except (BotoCoreError, ClientError) as exc:
        raise PermissionError("guardrail unavailable") from exc
    if resp["action"] == "GUARDRAIL_INTERVENED":
        raise PermissionError("guardrail blocked outbound message")

    payload["body"] = message
    return payload


def _redact_text(text: str) -> str:
    # Comprehend is a transformation API: it returns offsets, so the log entry
    # survives with only the PII spans replaced by their type.
    entities = _comprehend_client().detect_pii_entities(
        Text=text, LanguageCode="en"
    )["Entities"]

    # Replace from the end so earlier offsets stay valid.
    for e in sorted(entities, key=lambda e: e["BeginOffset"], reverse=True):
        text = text[: e["BeginOffset"]] + f"[{e['Type']}]" + text[e["EndOffset"]:]
    return text


def for_storage(data):
    """Recursively redact every string before it is persisted. Fails closed."""
    if isinstance(data, dict):
        return {k: for_storage(v) for k, v in data.items()}
    if isinstance(data, list):
        return [for_storage(v) for v in data]
    if isinstance(data, str) and data:
        try:
            return _redact_text(data)
        except (BotoCoreError, ClientError):
            # Fail closed: if we can't redact, we don't write the raw value.
            return "[REDACTION_UNAVAILABLE]"
    return data
