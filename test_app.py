"""Offline end-to-end check with Gemini stubbed out. Run: python test_app.py"""

import os
import tempfile

tmp = tempfile.mkdtemp()
os.environ.update(GEMINI_API_KEY="test", DB_PATH=f"{tmp}/test.db", UPLOAD_DIR=f"{tmp}/uploads")

from fastapi.testclient import TestClient  # noqa: E402

import app as web  # noqa: E402
import llm  # noqa: E402

seen_avoid = []
llm.summarize = lambda pdf: llm.DocumentSummary(
    overview="Visão geral", topics=[llm.Topic(title="Tópico A", summary="s", key_points=["k1"], pages=[2, 3])]
)


def fake_generate(pdf, topic, n_mc, n_open, difficulty, avoid):
    seen_avoid.append(list(avoid))
    return llm.QuestionSet(
        multiple_choice=[
            llm.MultipleChoice(statement="Qual a capital?", options=["a", "b", "c", "d"], correct_index=2,
                               explanation="porque c", source_page=2, source_quote="trecho")
        ],
        open_ended=[
            llm.OpenEnded(statement="Explique X.", rubric=["r1"], model_answer="ref", source_page=3, source_quote="t2")
        ],
    )


llm.generate_questions = fake_generate
llm.grade_answer = lambda q, answer: llm.Grade(score=6, feedback="ok", missing=["r1"])

c = TestClient(web.app)

assert c.post("/documents", data={"subject": "Eng"}, files={"file": ("x.pdf", b"not a pdf")}).status_code == 400

r = c.post("/documents", data={"subject": "Eng"}, files={"file": ("Aula 1.pdf", b"%PDF-1.4 fake")})
assert r.status_code == 200 and "Tópico A" in r.text and "Aula 1" in r.text, r.text
assert c.get("/documents/1/pdf").content == b"%PDF-1.4 fake"
assert "Eng" in c.get("/").text

r = c.post("/topics/1/questions", data={"difficulty": "hard", "n_multiple_choice": 1, "n_open_ended": 1})
assert "Qual a capital?" in r.text and "Explique X." in r.text
assert c.post("/topics/1/questions", data={"difficulty": "bogus"}).status_code == 422
c.post("/topics/1/questions", data={})
assert seen_avoid == [[], ["Qual a capital?", "Explique X."]], seen_avoid

assert "Errado" in c.post("/questions/1/answer", data={"answer": "0"}).text
assert "Correto" in c.post("/questions/1/answer", data={"answer": "2"}).text
assert c.post("/questions/1/answer", data={"answer": "9"}).status_code == 400
assert "Nota: 6/10" in c.post("/questions/2/answer", data={"answer": "minha resposta"}).text
assert c.post("/questions/2/answer", data={"answer": "   "}).status_code == 400
assert c.get("/topics/999").status_code == 404

assert "3 respostas, média 5.3/10" in c.get("/documents/1").text

print("ok")
