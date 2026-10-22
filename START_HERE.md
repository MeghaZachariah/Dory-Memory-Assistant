# Dory — Person A's code

| Folder | What it is | Guide |
|---|---|---|
| `backend/ai/` | Dory's brain: Nemotron on Token Factory, fact extraction, grounded answers, lie-catcher, medicine safety | `backend/ai/README.md` |
| `backend/api/` | Web server so the app, bot and dashboard can use the brain | `backend/api/README.md` |
| `mobile/dory_app/` | Android app that rings like a phone call, morning and evening | `mobile/dory_app/README.md` |

Quick start (from this folder):

```bash
pip install -r backend/ai/requirements.txt -r backend/api/requirements.txt
python -m pytest backend -q                                   # offline tests, no credits
uvicorn backend.api.main:app --host 0.0.0.0 --port 8000       # then open http://localhost:8000/docs
```

Put your Token Factory key in a `.env` file here (never commit it):

```
NEBIUS_API_KEY=...
```
