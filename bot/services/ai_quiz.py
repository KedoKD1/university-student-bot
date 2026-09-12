import asyncio
import json
import os
import re
from typing import Any

from openai import OpenAI


class AIQuizError(Exception):
    """Error raised when AI quiz generation fails."""


def _get_api_key() -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()

    if not api_key:
        raise AIQuizError(
            "⚠️ خدمة الذكاء الاصطناعي غير مفعّلة حالياً.\n\n"
            "يرجى المحاولة لاحقاً."
        )

    return api_key


def _get_model() -> str:
    return os.getenv(
        "OPENAI_MODEL",
        "gpt-5.6-luna",
    ).strip()


def _clean_json_text(text: str) -> str:
    text = text.strip()

    if text.startswith("```"):
        text = re.sub(
            r"^```(?:json)?\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\s*```$",
            "",
            text,
        )

    return text.strip()


def _parse_response(text: str) -> dict[str, Any]:
    if not text:
        raise AIQuizError(
            "❌ الذكاء الاصطناعي لم يرجع نتيجة صالحة."
        )

    cleaned = _clean_json_text(text)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise AIQuizError(
            "❌ تعذر قراءة نتيجة الذكاء الاصطناعي."
        ) from exc

    if not isinstance(data, dict):
        raise AIQuizError(
            "❌ صيغة نتيجة الذكاء الاصطناعي غير صحيحة."
        )

    return data


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def _validate_question(
    question: Any,
    question_type: str,
    difficulty: str,
) -> dict[str, Any] | None:

    if not isinstance(question, dict):
        return None

    question_text = _normalize_text(
        question.get("question_text")
    )

    if not question_text:
        return None

    q_type = _normalize_text(
        question.get("question_type")
    ).lower()

    q_difficulty = _normalize_text(
        question.get("difficulty")
    ).lower()

    if q_type != question_type:
        return None

    if q_difficulty != difficulty:
        return None

    explanation = _normalize_text(
        question.get("explanation")
    )

    options = question.get("options", {})
    correct_answer = question.get("correct_answer")

    if not isinstance(options, dict):
        return None

    # ========================================================
    # TRUE / FALSE
    # ========================================================

    if question_type == "true_false":

        required_keys = {"true", "false"}

        if set(options.keys()) != required_keys:
            return None

        answer = _normalize_text(
            correct_answer
        ).lower()

        if answer not in {"true", "false"}:
            return None

        return {
            "question_type": "true_false",
            "question_text": question_text,
            "options": {
                "true": "True",
                "false": "False",
            },
            "correct_answer": answer,
            "explanation": explanation,
            "difficulty": difficulty,
        }

    # ========================================================
    # MULTIPLE CHOICE
    # ========================================================

    if question_type == "multiple_choice":

        required_keys = {"A", "B", "C", "D"}

        if set(options.keys()) != required_keys:
            return None

        cleaned_options = {}

        for key in ["A", "B", "C", "D"]:
            value = _normalize_text(
                options.get(key)
            )

            if not value:
                return None

            cleaned_options[key] = value

        answer = _normalize_text(
            correct_answer
        ).upper()

        if answer not in required_keys:
            return None

        return {
            "question_type": "multiple_choice",
            "question_text": question_text,
            "options": cleaned_options,
            "correct_answer": answer,
            "explanation": explanation,
            "difficulty": difficulty,
        }

    # ========================================================
    # ENUMERATION
    # ========================================================

    if question_type == "enumeration":

        if not isinstance(correct_answer, list):
            return None

        answers = []

        for item in correct_answer:
            value = _normalize_text(item)

            if value:
                answers.append(value)

        if len(answers) < 2:
            return None

        return {
            "question_type": "enumeration",
            "question_text": question_text,
            "options": {},
            "correct_answer": answers,
            "explanation": explanation,
            "difficulty": difficulty,
        }

    return None


def _validate_questions(
    data: dict[str, Any],
    question_type: str,
    difficulty: str,
    count: int,
) -> list[dict[str, Any]]:

    raw_questions = data.get("questions")

    if not isinstance(raw_questions, list):
        raise AIQuizError(
            "❌ الذكاء الاصطناعي لم يرجع أسئلة بالصيغة المطلوبة."
        )

    result = []
    seen = set()

    for raw_question in raw_questions:

        question = _validate_question(
            raw_question,
            question_type,
            difficulty,
        )

        if question is None:
            continue

        normalized_question = re.sub(
            r"\s+",
            " ",
            question["question_text"].lower(),
        ).strip()

        if normalized_question in seen:
            continue

        seen.add(normalized_question)
        result.append(question)

        if len(result) >= count:
            break

    if len(result) < count:
        raise AIQuizError(
            "❌ الذكاء الاصطناعي لم يستطع إنشاء العدد المطلوب "
            "من الأسئلة بجودة كافية."
        )

    return result


def _build_prompt(
    source_text: str,
    question_type: str,
    difficulty: str,
    count: int,
) -> str:

    if question_type == "true_false":

        type_rules = """
Question type: True / False.

Each question MUST contain:

- options = {"true": "True", "false": "False"}
- correct_answer = "true" OR "false"
"""

    elif question_type == "multiple_choice":

        type_rules = """
Question type: Multiple Choice.

Each question MUST contain:

- Exactly 4 options.
- Option keys MUST be A, B, C, D.
- correct_answer MUST be exactly one of A, B, C, or D.
"""

    elif question_type == "enumeration":

        type_rules = """
Question type: Enumeration.

The question must ask the student to list
items, elements, steps, components, classifications,
or points that are explicitly present in the source material.

correct_answer MUST be a list containing all correct answers.

There must be at least 2 correct answers.
"""

    else:
        raise AIQuizError(
            "❌ نوع الاختبار غير مدعوم."
        )

    return f"""
You are an academic quiz generator for LabBase,
an educational platform for Medical Laboratory Techniques students.

Your task is to generate quiz questions ONLY from the source
material provided at the end of this prompt.

============================================================
STRICT SOURCE RULES
============================================================

1. Use ONLY information explicitly found in the source material.

2. DO NOT use outside knowledge.

3. DO NOT guess.

4. DO NOT invent facts.

5. If information is unclear, incomplete, or ambiguous,
   DO NOT use it.

6. Every correct answer MUST be directly supported by the source.

7. Questions must be academically useful and clear.

8. Do not create duplicate questions.

9. For multiple choice questions, there MUST be exactly one
   correct answer.

10. Do not create misleading answers based on information
    that does not exist in the source.

============================================================
LANGUAGE RULE — VERY IMPORTANT
============================================================

ALL quiz content MUST be written in ENGLISH.

This includes:

- question_text
- multiple-choice options
- correct_answer
- explanation

DO NOT translate the source material into Arabic.

Use the English terminology exactly as it appears in the
source material whenever possible.

Medical terminology must remain in English.

If the source contains English medical terms,
preserve them accurately.

The quiz interface itself may remain Arabic,
but the actual questions and answers MUST be English.

============================================================
DIFFICULTY
============================================================

Required difficulty:
{difficulty}

============================================================
QUESTION COUNT
============================================================

Generate exactly:
{count}

questions.

============================================================
QUESTION TYPE
============================================================

{type_rules}

============================================================
OUTPUT FORMAT
============================================================

Return ONLY valid JSON.

Do NOT use Markdown.

Do NOT add explanations outside the JSON.

Required JSON structure:

{{
  "questions": [
    {{
      "question_type": "{question_type}",
      "question_text": "Question in English",
      "options": {{}},
      "correct_answer": "Correct answer",
      "explanation": "Short explanation in English based only on the source",
      "difficulty": "{difficulty}"
    }}
  ]
}}

============================================================
SOURCE MATERIAL
============================================================

---------------- BEGIN SOURCE ----------------

{source_text}

----------------- END SOURCE -----------------
"""


def _generate_sync(
    source_text: str,
    question_type: str,
    difficulty: str,
    count: int,
) -> list[dict[str, Any]]:

    api_key = _get_api_key()
    model = _get_model()

    client = OpenAI(
        api_key=api_key,
    )

    prompt = _build_prompt(
        source_text=source_text,
        question_type=question_type,
        difficulty=difficulty,
        count=count,
    )

    try:
        response = client.responses.create(
            model=model,
            input=prompt,
        )

    except Exception as exc:

        raise AIQuizError(
            "❌ حدث خطأ أثناء الاتصال بخدمة الذكاء الاصطناعي.\n"
            "حاول مرة أخرى لاحقاً."
        ) from exc

    output_text = getattr(
        response,
        "output_text",
        None,
    )

    if not output_text:
        raise AIQuizError(
            "❌ الذكاء الاصطناعي لم يرجع نتيجة."
        )

    data = _parse_response(
        output_text
    )

    return _validate_questions(
        data=data,
        question_type=question_type,
        difficulty=difficulty,
        count=count,
    )


async def generate_questions(
    source_text: str,
    question_type: str,
    difficulty: str,
    count: int,
) -> list[dict[str, Any]]:

    if not source_text or not source_text.strip():
        raise AIQuizError(
            "❌ لا توجد مادة نصية كافية لإنشاء الاختبار."
        )

    if question_type not in {
        "true_false",
        "multiple_choice",
        "enumeration",
    }:
        raise AIQuizError(
            "❌ نوع الأسئلة غير صالح."
        )

    if difficulty not in {
        "easy",
        "medium",
        "hard",
    }:
        raise AIQuizError(
            "❌ مستوى الصعوبة غير صالح."
        )

    if count not in {
        1,
        5,
        10,
    }:
        raise AIQuizError(
            "❌ عدد الأسئلة غير صالح."
        )

    return await asyncio.to_thread(
        _generate_sync,
        source_text,
        question_type,
        difficulty,
        count,
    )
