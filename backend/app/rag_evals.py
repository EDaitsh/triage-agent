"""
RAG Evaluation module
=====================
Measures how well the RAG pipeline answers questions derived from the same
corpus it was built from.

Pipeline
--------
1. ``generate_qa_pairs``  – use GPT-4o to create ground-truth Q&A pairs
2. ``evaluate_single``    – LLM-as-judge: score one (expected, actual) pair
3. ``run_evals``          – orchestrate ingest → Q&A generation → RAG → scoring
"""

import json
from typing import List

from pydantic import BaseModel

from .llm import MODEL, client
from .rag import answer_question


# ── Pydantic schemas ─────────────────────────────────────────────────────────
class QAPair(BaseModel):
    question: str
    expected_answer: str


class _QAPairsResponse(BaseModel):
    pairs: List[QAPair]


class EvalResult(BaseModel):
    question: str
    expected_answer: str
    actual_answer: str
    score: float          # 0.0 – 1.0
    reasoning: str


class _ScoreResponse(BaseModel):
    score: float
    reasoning: str


# ── 1. generate_qa_pairs ─────────────────────────────────────────────────────
async def generate_qa_pairs(text: str, n: int = 5) -> List[QAPair]:
    """
    Ask GPT-4o to produce *n* question / expected-answer pairs from *text*.
    These will be used as ground truth when evaluating the RAG pipeline.
    """
    prompt = (
        f"קרא את הטקסט הבא וצור בדיוק {n} שאלות ותשובות מצופות.\n"
        "הנחיות לשאלות:\n"
        "- השאלות צריכות להיות כאלו שמשתמש אמיתי"
        "  היה שואל (טבעיות, לא ציטוט מהמסמך)\n"
        "- כל שאלה מכסה נושא אחר מהמסמך\n"
        "- התשובה המצופה צריכה להיות מלאה ומדויקת כפי שמופיע בטקסט\n"
        "- אל תיצור שאלות על מספרים ספציפיים בלבד — שאל על תהליכים ומדיניות\n"
        "החזר JSON בלבד עם המבנה:\n"
        '{"pairs": [{"question": "...", "expected_answer": "..."}]}'
        f"\n\nטקסט:\n{text}"
    )

    response = await client.responses.parse(
        model=MODEL,
        input=[{"role": "user", "content": prompt}],
        text_format=_QAPairsResponse,
    )
    return response.output_parsed.pairs


# ── 2. evaluate_single ───────────────────────────────────────────────────────
async def evaluate_single(
    question: str, expected: str, actual: str
) -> EvalResult:
    """
    Use the LLM as a judge to score *actual* against *expected*.

    Score scale
    -----------
    1.0 – answer is correct and complete
    0.5 – partially correct or missing minor details
    0.0 – wrong, irrelevant, or the model admitted it had no information
    """
    system_prompt = (
        "אתה שופט המעריך תשובות של מערכת RAG.\n"
        "כללי ניקוד:\n"
        "1.0 – התשובה מכילה את כל המידע העיקרי הדרוש, גם אם הניסוח שונה\n"
        "0.7 – התשובה נכונה אך חסר פרט אחד משני\n"
        "0.5 – חלק מהתשובה נכון אך חסר מידע מהותי\n"
        "0.0 – התשובה שגויה, לא רלוונטית, או שהמודל אמר שאין לו מידע\n"
        "חשוב: אל תנכה נקודות על הבדלי ניסוח, שפה או סגנון. "
        "בדוק רק אם המידע העובדתי נכון ומלא.\n"
        'החזר JSON בלבד: {"score": <float>, "reasoning": "<הסבר קצר>"}'
    )

    eval_input = json.dumps(
        {
            "question": question,
            "expected_answer": expected,
            "actual_answer": actual,
        },
        ensure_ascii=False,
    )

    response = await client.responses.parse(
        model=MODEL,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": eval_input},
        ],
        text_format=_ScoreResponse,
    )
    scored = response.output_parsed

    return EvalResult(
        question=question,
        expected_answer=expected,
        actual_answer=actual,
        score=max(0.0, min(1.0, scored.score)),
        reasoning=scored.reasoning,
    )


# ── 3. run_evals ─────────────────────────────────────────────────────────────
async def run_evals(
    text: str, n_questions: int = 5, source: str = "eval_doc"
) -> dict:
    """
    Full evaluation pipeline:
    1. Generate *n_questions* ground-truth Q&A pairs from *text*
    2. Run each question through the RAG pipeline (uses existing DB)
    3. Score each answer with LLM-as-judge
    4. Return aggregated results

    NOTE: does NOT ingest *text* into the DB — run ingest first via
    /rag/ingest (or /rag/clear + /rag/ingest for a clean run).

    Returns
    -------
    dict with keys:
      - ``n_questions`` : number of evaluated questions
      - ``avg_score``   : mean score across all questions (0.0 – 1.0)
      - ``results``     : list of per-question EvalResult dicts
    """
    # 1. Generate ground truth from the supplied text
    qa_pairs = await generate_qa_pairs(text, n=n_questions)

    # 2 & 3. RAG + judge
    results: List[dict] = []
    for pair in qa_pairs:
        rag_result = await answer_question(pair.question)
        eval_result = await evaluate_single(
            pair.question,
            pair.expected_answer,
            rag_result["answer"],
        )
        results.append(eval_result.model_dump())

    avg_score = (
        sum(r["score"] for r in results) / len(results)
        if results
        else 0.0
    )

    return {
        "n_questions": len(results),
        "avg_score": round(avg_score, 3),
        "results": results,
    }
