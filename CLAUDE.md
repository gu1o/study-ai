# study-ai

Personal study tool: upload class PDFs, get a structured summary of key topics, and practice with LLM-generated multiple-choice and open-ended questions (Gemini API).

## Stack

Python + FastAPI, SQLite (stdlib `sqlite3`, no ORM), Jinja templates + HTMX, Google Gemini via `google-genai`.

## Layout

- `llm.py`: the 3 Gemini calls (`summarize`, `generate_questions`, `grade_answer`) and their Pydantic schemas. `python llm.py some.pdf` is a live smoke test.
- `db.py`: SQLite schema and queries. Topics and questions are stored as JSON (`data` column) dumped from the `llm.py` models.
- `app.py` + `templates/`: FastAPI routes rendering Jinja pages; answers are submitted with HTMX.
- `test_app.py`: offline end-to-end test with Gemini stubbed. Run `python test_app.py` after changes.

## Running (Python not set up on host: use a container)

```bash
docker run -d --name study-ai-dev --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/app -w /app -p 8010:8000 \
  python:3.12-slim sh -c "pip install -q --user -r requirements.txt && python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload"
docker exec study-ai-dev python test_app.py
```

Port 8000 on the host is taken by another project; the app runs on http://localhost:8010.

## Project rules

1. **All code in English.** This covers identifiers, comments, commit messages, DB tables/columns, and file names. Only user-facing UI text and LLM prompts/outputs may be in Portuguese.
2. **Public repo: no secrets in code.** API keys, passwords, and any credentials come from environment variables only (`.env`, never committed). Every new variable gets an entry in `.env.example` with an empty or dummy value. Never hardcode a key, not even as a default value.
3. **Deploy files are not versioned.** `Dockerfile`, `docker-compose*.yml`, `Caddyfile`, and anything else under `deploy/` stay local and are listed in `.gitignore`.
4. **User data is not versioned.** Uploaded PDFs and the SQLite database are gitignored.
