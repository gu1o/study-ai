"""Web app: upload class PDFs, browse topics, practice with generated questions."""

import os
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from google.genai import errors as genai_errors

import db
import llm

UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR") or "uploads")
MAX_PDF_BYTES = 20 * 1024 * 1024  # Gemini inline request limit
MAX_ANSWER_CHARS = 5000

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
db.init()

app = FastAPI()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def pdf_path(doc_id: int) -> Path:
    return UPLOAD_DIR / f"{doc_id}.pdf"  # never use the uploaded filename on disk


def found(item):
    if item is None:
        raise HTTPException(404, "Não encontrado.")
    return item


def render(request: Request, name: str, **context):
    return templates.TemplateResponse(request, name, context)


@app.exception_handler(genai_errors.APIError)
def gemini_error(request: Request, exc: genai_errors.APIError):
    return HTMLResponse(
        f"<p>O Gemini não respondeu (erro {exc.code}). Tente de novo em instantes.</p>",
        status_code=503,
    )


@app.get("/")
def index(request: Request):
    return render(request, "index.html", documents=db.list_documents())


@app.post("/documents")
def upload_document(file: UploadFile, subject: str = Form(max_length=100), title: str = Form("", max_length=200)):
    pdf = file.file.read(MAX_PDF_BYTES + 1)
    if len(pdf) > MAX_PDF_BYTES:
        raise HTTPException(413, "PDF maior que 20MB.")
    if not pdf.startswith(b"%PDF"):
        raise HTTPException(400, "O arquivo não é um PDF.")

    summary = llm.summarize(pdf)  # ponytail: synchronous (~1 min); move to a background task if it times out behind a proxy
    title = title.strip() or Path(file.filename or "aula").stem
    doc_id = db.add_document(subject.strip(), title, summary)
    pdf_path(doc_id).write_bytes(pdf)
    return RedirectResponse(f"/documents/{doc_id}", status_code=303)


@app.get("/documents/{doc_id}")
def show_document(request: Request, doc_id: int):
    doc = found(db.get_document(doc_id))
    return render(request, "document.html", doc=doc, topics=db.list_topics(doc_id), stats=db.topic_stats(doc_id))


@app.get("/documents/{doc_id}/pdf")
def document_pdf(doc_id: int):
    path = pdf_path(doc_id)
    if not path.exists():
        raise HTTPException(404, "PDF não encontrado.")
    return FileResponse(path, media_type="application/pdf")


@app.get("/topics/{topic_id}")
def show_topic(request: Request, topic_id: int):
    topic = found(db.get_topic(topic_id))
    return render(
        request,
        "topic.html",
        topic=topic,
        doc=db.get_document(topic["document_id"]),
        questions=db.list_questions(topic_id),
    )


@app.post("/topics/{topic_id}/questions")
def generate_questions(
    topic_id: int,
    difficulty: llm.Difficulty = Form("medium"),
    n_multiple_choice: int = Form(5, ge=0, le=10),
    n_open_ended: int = Form(2, ge=0, le=5),
):
    topic = found(db.get_topic(topic_id))
    existing = [q["statement"] for q in db.list_questions(topic_id)]
    question_set = llm.generate_questions(
        pdf_path(topic["document_id"]).read_bytes(),
        llm.Topic.model_validate(topic),
        n_multiple_choice,
        n_open_ended,
        difficulty,
        existing,
    )
    db.add_questions(topic_id, difficulty, question_set)
    return RedirectResponse(f"/topics/{topic_id}", status_code=303)


@app.post("/questions/{question_id}/answer")
def answer_question(request: Request, question_id: int, answer: str = Form(max_length=MAX_ANSWER_CHARS)):
    question = found(db.get_question(question_id))

    if question["kind"] == "multiple_choice":
        if not answer.isdigit() or int(answer) >= len(question["options"]):
            raise HTTPException(400, "Alternativa inválida.")
        choice = int(answer)
        score = 10 if choice == question["correct_index"] else 0
        result = {"choice": choice}
    else:
        if not answer.strip():
            raise HTTPException(400, "Resposta vazia.")
        grade = llm.grade_answer(llm.OpenEnded.model_validate(question), answer)
        score = grade.score
        result = grade.model_dump()

    db.add_attempt(question_id, answer, score, result)
    return render(request, "_result.html", q=question, score=score, result=result)
