# backend/ai — Dory's brain (Person A)

Everything Dory says, and why it is safe. Runs on NVIDIA Nemotron models through Nebius Token Factory.

## Setup

```bash
pip install -r backend/ai/requirements.txt
export NEBIUS_API_KEY=...                     # from the Token Factory console
python -m backend.ai.scripts.list_models      # find the exact Nemotron model IDs
export DORY_MODEL_NANO=...  DORY_MODEL_SUPER=...  DORY_MODEL_ULTRA=...
python -m backend.ai.scripts.smoke_test       # one call per tier, prints latency
```

Run commands from the repo root (`dory-hackathon/`). All settings are in `config.py` and can be set as environment variables (see `.env.example`).

## Functions for Person B

```python
from backend.ai import chat, extract_facts, briefing, summary

r = chat("mary", "Did anyone visit me?", person_name="Mary", family_names=["Anu", "Ravi"])
r.reply               # what Dory says aloud (only checked or fixed text)
r.status              # "answered" | "unknown" | "refused"
r.route               # "memory" | "medication" | "override" | "error"
r.blocked             # True if the lie-catcher replaced the model's answer
r.draft_answer        # the blocked answer, for the dashboard badge
r.fact_ids_used       # receipts
r.pending_question_id # set when the question was sent to the family
r.notify_family       # bot should message family/caregiver now

report = extract_facts(turns, date(2026, 10, 18), "mary", "Mary")   # evening chat -> saved facts
report.kept, report.rejected     # rejected facts come with a reason (good for the demo)

briefing("mary", person_name="Mary").text      # morning reminder
s = summary("mary", person_name="Mary")        # daily family update
s.text, s.alerts, s.stats                      # alerts like "Asked about medicines 3 times today"
```

### Things Mary tells Dory during the day

`chat()` also records statements, not only questions ("Ravi phoned me this morning"). Each one goes through the extraction checks, then is cross-checked against confirmed facts:

| Result in `r.noted[i]["outcome"]` | What happened |
|---|---|
| `already_known` | Matches a confirmed fact. Nothing stored. |
| `already_recorded` | Same as a fact already saved (pending, confirmed or rejected). Nothing stored or asked again. |
| `pending_family_check` | New, or contradicts a confirmed fact. Saved with `verification="pending"` and a family question (`reason="verify_statement"`) is created. |

Pending facts are never used in answers, briefings or summaries. When the family replies to a `verify_statement` question, the bot calls this instead of `record_family_answer`:

```python
from backend.ai import confirm_statement
confirm_statement("mary", question_id, is_true=True, answered_by="Anu")   # True -> confirmed, False -> rejected
```

A message with only statements gets the fixed reply "Thank you for telling me." (Dory never says Mary is wrong). A mixed message ("Ravi phoned. Did Anu visit?") records the statement and answers the question. Health talk is never recorded.

`turns` is a list of `{"speaker": "Dory" | "<name>", "text": "..."}` or plain text with one `Speaker: words` line per turn.

## Functions needed from Person C

Defined in `db_interface.py`: `add_fact`, `get_facts`, `create_pending_question`, `record_family_answer`, `update_fact`, `close_question`, `get_med_log`, `log_event`, `get_events`. Facts have two new fields: `verification` (`confirmed` | `pending` | `rejected`, default `confirmed`) and `verify_question_id`. Before calling `add_fact`, extraction checks `get_facts` and skips a fact already stored for the same date. Until the real database is ready, `fake_db.py` provides them in memory. Plug the real one in at startup:

```python
from backend.ai import set_db
from db import crud
set_db(crud)
```

Field names for facts are in `schemas.py` (`Fact`). Agree them with Person C and change them in that one file if needed.

## How each answer is made safe

1. **Health first.** Medicine, symptom, urgent and "take double" messages are caught by keyword rules (plus a Nano classifier for borderline ones like "I feel off"). They get fixed template replies filled from the caregiver's med log, and the caregiver is notified. No model writes or sees these replies.
2. **Grounded answer.** Nano answers using only stored facts (never "do not share" ones) and must list the fact ids it used.
3. **Lie-catcher, code part.** The answer must cite real fact ids, and every name, number, weekday, month, "today/yesterday/tomorrow" in it must match the cited facts.
4. **Lie-catcher, model part.** Super judges "supported" or "unsupported". If it is down, the answer is blocked (fail closed).
5. **Unknown, refused or blocked** answers become a fixed "I'm not sure, I've asked your family" reply, and the question goes to `create_pending_question()`.

Extraction has its own checks: the quote must appear word-for-word in what the person said (not Dory), names Dory mentioned aren't credited to the person, health statements are never stored, and dates are worked out in code (`dates.py`).

## Logs for the scorecard (Person C)

Every model call is appended to `backend/ai/logs/model_calls.jsonl`: tier, model, purpose (`answer`, `check`, `extract`, ...), latency, tokens, errors, and whether it was over the 3-second target. Every answer is also sent to `log_event(..., "answer", {...})` with a `badge` of `passed`, `blocked by checker`, `unknown` or `refused`.

## Tests

```bash
python -m pytest backend/ai/tests -q                 # offline, uses a scripted fake model
python -m backend.ai.scripts.eval_extraction         # real model on the 10 sample conversations
python -m backend.ai.scripts.demo_chat               # talk to Dory in the terminal
```

The offline tests cover the "done when" goals: correct facts with verified quotes from 10 sample conversations, unknown questions never answered, and medication questions never answered from memory.

## Tuning

- Too slow? Set `DORY_MODEL_CHECK=0` to skip the model check (code checks still run), or move `DORY_TIER_CHECK` to `nano`.
- Model IDs wrong? Only `DORY_MODEL_*` need changing.
- Prompts and tone rules are all in `prompts.py`. Update them with the caregiver interview notes.
