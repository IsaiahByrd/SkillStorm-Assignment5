# Findings

The agent is a library help desk. `read_record` looks up a member account from a
fake backing store, and `send_contact_detail` texts the member through a
simulated SMS vendor to tell them a hold is ready.

| Leak | Where the data crossed | Where I closed it | What it still misses |
|---|---|---|---|
| OUT | `send_contact_detail` → `_sms_vendor_send` (the SMS vendor). The message body is written by the model, so anything in the model's context could ride along. The scaffolded Exa web-search MCP tools were a second outbound channel. | `controls.for_partner()`: an allow-list builds the payload from `phone` only, the body is rejected if it repeats any other value from the record (name, email, address, book title, notes), and `ApplyGuardrail` must approve the body. I removed the Exa MCP tools from `main.py`. | The record-value check is an exact-text match, so a paraphrase ("the first Harry Potter book") gets through, and the guardrail doesn't treat book titles as PII. The vendor still learns the phone number and that this person uses this branch. The guardrail only catches the entity types configured in `support-agent-pii`. Nothing stops the model texting the wrong `member_id`. |
| IN | `read_record` returns the whole account to the model, including `staff_notes`, where staff typed a full card number. It then sits in the model's context and the in-memory conversation history (`InMemorySaver`). | *(not closed)* | Closing it means a `for_model()` control in `read_record`: drop `staff_notes` or run it through Comprehend before returning. **Cost:** an extra Comprehend call on every read (latency and per-character charges). **What it breaks:** the notes also hold useful, non-sensitive information ("prefers texts over calls"), and the agent could no longer answer "did my lost-book fee go through?". Redacting name and email as well would stop the agent confirming who it is talking to. The real fix is upstream: stop staff typing card numbers into a free-text field. |
| STORED | `store.write_record` → `interactions.jsonl` (every tool call plus the agent's input and output). In the scaffold, `log.info(f"Agent input: {prompt}")` and the output line wrote raw text to the runtime logs, and the LangChain OpenTelemetry instrumentation records prompt and response text in traces. | `store.write_record()` calls `controls.for_storage()` at the moment of writing, which replaces every PII span Comprehend finds with its type (`[EMAIL]`, `[CREDIT_DEBIT_NUMBER]`, …). I replaced the raw `log.info` lines with `write_record`, and set `TRACELOOP_TRACE_CONTENT=false` to keep message text out of traces. | It is only as good as Comprehend's recall: unusual formats can slip through. Book titles aren't PII to Comprehend, so a member's reading history is written raw when `read_record` logs the account. `member_id` is stored unredacted and links straight back to the person, so the log is pseudonymous, not anonymous. The in-memory conversation history keeps raw text for the life of the process. I haven't confirmed in CloudWatch that the trace setting removes all message text. |

## Why each control uses the API it uses

- **`for_partner` uses `ApplyGuardrail` (a decision API)** because the question at
  that boundary is yes or no: may this text leave the building? If the answer is
  no, the right behaviour is not to send at all, rather than to send a rewritten
  version.
- **`for_storage` uses Comprehend `detect_pii_entities` (a transformation API)**
  because I want to keep the log entry, minus the personal data. Comprehend
  returns character offsets, so I can replace just those spans and keep the rest
  of the record useful for debugging and auditing.

## Fail open or fail closed?

Both controls fail closed, and that is what I intended. If Comprehend is
unavailable when a record is about to be written, `for_storage` replaces that
text value with `[REDACTION_UNAVAILABLE]` instead of writing it raw. The entry is
still written (timestamp, event type, field names), so the audit trail survives
but the personal data does not. Any other error stops the write completely, which
is also closed. On the way out, if `GUARDRAIL_ID` is not set or the guardrail
call fails, `for_partner` raises and nothing reaches the SMS vendor. The blocked
attempt is logged as `sms_blocked`. A missed "your hold is ready" text is cheap
and easy to retry. A leaked phone number, card number or reading history can't be
taken back.

## What I would do with another day

**I wasn't able to get to the `pytest` tests.** With another day I would write
them first:
- one asserting that nothing in the SMS vendor's outbox contains the member's
  name, email, address, book title or card number;
- one asserting that the log file written by `write_record` contains none of the
  raw values;
- a third covering the fail-closed paths.

They would use fake Comprehend and guardrail clients, so they run without AWS
credentials, and each would turn red if its control were deleted.

After that, I would:
- close the IN leak with a `for_model()` control that redacts `staff_notes` only;
- replace the exact-match title check with something that catches paraphrases;
- move persistence from a JSONL file to AgentCore Memory, with redaction still at
  the moment of writing;
- deploy, and check in CloudWatch that no raw message text appears in the logs or
  traces.
