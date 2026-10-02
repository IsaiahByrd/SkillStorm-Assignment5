# SkillStorm Assignment 5: Close the Leaks on AgentCore

A library help-desk agent on AgentCore Runtime (LangChain/LangGraph on Bedrock)
that handles member personal data and closes the OUT and STORED leaks. See
[FINDINGS.md](FINDINGS.md) for the leak table and design decisions.

**Run mode:** I ran this locally under `agentcore dev`; it was not deployed.

## Layout

```
IBPiiLab/
  agentcore/agentcore.json      AgentCore project config
  app/IBLabAgent/
    main.py                     BedrockAgentCoreApp entrypoint
    tools.py                    read_record, send_contact_detail + fake backing store
    controls.py                 for_partner(), for_storage()
    store.py                    write_record(): the only thing that writes to disk
    pyproject.toml              dependencies
FINDINGS.md
```

## Setup

Prerequisites: Python 3.10+, [uv](https://docs.astral.sh/uv/), Node.js 20+, the
`agentcore` CLI, and AWS credentials with `bedrock:InvokeModel`,
`bedrock:ApplyGuardrail` and `comprehend:DetectPiiEntities`.

```bash
git clone <this repo>
cd SkillStorm-Assignment5/IBPiiLab/app/IBLabAgent
uv sync                      # installs dependencies from pyproject.toml
```

Configure the guardrail by copying `.env.example` to `IBPiiLab/agentcore/.env.local`
and filling in:

```
AWS_REGION=us-east-1
GUARDRAIL_ID=<your Bedrock guardrail ID>
GUARDRAIL_VERSION=DRAFT
```

Without `GUARDRAIL_ID`, the agent still runs but refuses to send any text message
(the outbound control fails closed).

## Run

```bash
cd IBPiiLab
agentcore dev
```

In another terminal:

```bash
agentcore invoke "Hi, I'm member M-1001. Can you text me when my hold is ready?"
```

The fake accounts are `M-1001` and `M-1002` (all data is fabricated). Interaction
logs are written to `interactions.jsonl` in the agent's working directory, with
PII redacted at write time. This file is gitignored.

## Tests

Not included. I wasn't able to get to the `pytest` tests; see "What I would do
with another day" in [FINDINGS.md](FINDINGS.md).
