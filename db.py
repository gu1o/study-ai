"""SQLite storage. LLM objects (topics, questions) are stored as JSON in a `data` column."""

import json
import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get("DB_PATH") or "study.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    subject TEXT NOT NULL,
    title TEXT NOT NULL,
    overview TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    data TEXT NOT NULL -- llm.Topic
);
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY,
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('multiple_choice', 'open_ended')),
    difficulty TEXT NOT NULL,
    data TEXT NOT NULL, -- llm.MultipleChoice | llm.OpenEnded
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY,
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    answer TEXT NOT NULL,
    score INTEGER NOT NULL CHECK (score BETWEEN 0 AND 10),
    result TEXT NOT NULL, -- grading details
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

QUESTION_SELECT = "SELECT q.*, t.document_id FROM questions q JOIN topics t ON t.id = q.topic_id"


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        with conn:  # commits on success, rolls back on error
            yield conn
    finally:
        conn.close()


def _row(row: sqlite3.Row | None) -> dict | None:
    """Flatten a row into a dict, merging its JSON `data` column into the top level."""
    if row is None:
        return None
    d = dict(row)
    d.update(json.loads(d.pop("data", "{}")))
    return d


def init() -> None:
    with _conn() as c:
        c.executescript(SCHEMA)


def add_document(subject: str, title: str, summary) -> int:
    with _conn() as c:
        doc_id = c.execute(
            "INSERT INTO documents (subject, title, overview) VALUES (?, ?, ?)",
            (subject, title, summary.overview),
        ).lastrowid
        c.executemany(
            "INSERT INTO topics (document_id, position, data) VALUES (?, ?, ?)",
            [(doc_id, i, t.model_dump_json()) for i, t in enumerate(summary.topics)],
        )
    return doc_id


def list_documents() -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM documents ORDER BY created_at DESC, id DESC").fetchall()
    return [dict(r) for r in rows]


def get_document(doc_id: int) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    return dict(row) if row else None


def list_topics(doc_id: int) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM topics WHERE document_id = ? ORDER BY position", (doc_id,)
        ).fetchall()
    return [_row(r) for r in rows]


def get_topic(topic_id: int) -> dict | None:
    with _conn() as c:
        return _row(c.execute("SELECT * FROM topics WHERE id = ?", (topic_id,)).fetchone())


def add_questions(topic_id: int, difficulty: str, question_set) -> None:
    rows = [(topic_id, "multiple_choice", difficulty, q.model_dump_json()) for q in question_set.multiple_choice]
    rows += [(topic_id, "open_ended", difficulty, q.model_dump_json()) for q in question_set.open_ended]
    with _conn() as c:
        c.executemany(
            "INSERT INTO questions (topic_id, kind, difficulty, data) VALUES (?, ?, ?, ?)", rows
        )


def list_questions(topic_id: int) -> list[dict]:
    with _conn() as c:
        rows = c.execute(f"{QUESTION_SELECT} WHERE q.topic_id = ? ORDER BY q.id", (topic_id,)).fetchall()
    return [_row(r) for r in rows]


def get_question(question_id: int) -> dict | None:
    with _conn() as c:
        return _row(c.execute(f"{QUESTION_SELECT} WHERE q.id = ?", (question_id,)).fetchone())


def add_attempt(question_id: int, answer: str, score: int, result: dict) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO attempts (question_id, answer, score, result) VALUES (?, ?, ?, ?)",
            (question_id, answer, score, json.dumps(result, ensure_ascii=False)),
        )


def topic_stats(doc_id: int) -> dict[int, dict]:
    """Attempt count and average score (0-10) per topic of a document."""
    with _conn() as c:
        rows = c.execute(
            """SELECT t.id, COUNT(a.id) AS attempts, AVG(a.score) AS avg_score
               FROM topics t JOIN questions q ON q.topic_id = t.id JOIN attempts a ON a.question_id = q.id
               WHERE t.document_id = ? GROUP BY t.id""",
            (doc_id,),
        ).fetchall()
    return {r["id"]: {"attempts": r["attempts"], "avg_score": r["avg_score"]} for r in rows}
