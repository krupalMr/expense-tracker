# Pocketwise API

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The first startup creates an empty `expenses.db`; add your own expense entries from the dashboard. Set `DATABASE_PATH` to persist the SQLite file elsewhere.
