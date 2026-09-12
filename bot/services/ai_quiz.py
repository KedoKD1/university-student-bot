import asyncio
import json
import re

from openai import OpenAI

from bot.utils.config import (
    OPENAI_API_KEY,
    OPENAI_MODEL,
)


class AIQuizError(Exception):
    pass


def normalize(value):
    value = str(value or "").strip().lower()
    value = re.sub(r"\s+", " ", value)
    return value


def parse_ai_json(text):
    text = str(text or "").strip()

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

    try:
        return json.loads(text)
    except Exception as exc:
        raise AIQuizError(
            "تعذر قراءة نتيجة الذكاء الاصطناعي."
        ) from exc


def validate_questions(
    questions,
    question_type,
    difficulty,
    expected_count,
):
    if not isinstance(questions, list):
        raise AIQuizError(
            "الذكاء الاصطناعي لم يرجع قائمة أسئلة."
        )

    valid = []
    seen = set()

    for question in questions:
        if not isinstance(question, dict):
            continue

        question_text = str(
            question.get("question_text") or ""
        ).strip()

        if not question_text:
            continue

        normalized_question = normalize(
            question_text
        )

        if normalized_question in seen:
            continue

        if question.get("question_type") != question_type:
            continue

        if question.get("difficulty") != difficulty:
            continue

        options = question.get("options")
        correct_answer = question.get(
            "correct_answer"
        )

        if question_type == "multiple_choice":
            if not isinstance(options, dict):
                continue

            if len(options) != 4:
                continue

            if not isinstance(
                correct_answer,
                str,
            ):
                continue

            if correct_answer not in options:
                continue

        elif question_type == "true_false":
            if not isinstance(options, dict):
                continue

            if len(options) != 2:
                continue

            if not isinstance(
                correct_answer,
                str,
            ):
                continue

            if normalize(correct_answer) not in {
                "صح",
                "خطأ",
            }:
                continue

        elif question_type == "enumeration":
            if not isinstance(
                correct_answer,
                list,
            ):
                continue

            if len(correct_answer) < 2:
                continue

        seen.add(normalized_question)
        valid.append(question)

        if len(valid) >= expected_count:
            break

    if len(valid) != expected_count:
        raise AIQuizError(
            f"تم إنشاء {len(valid)} أسئلة فقط "
            f"من أصل {expected_count}."
        )

    return valid


def _generate_questions_sync(
    source_text,
    question_type,
    difficulty,
    question_count,
):
    if not OPENAI_API_KEY:
        raise AIQuizError(
            "OPENAI_API_KEY غير مضاف في Railway."
        )

    client = OpenAI(
        api_key=OPENAI_API_KEY
    )

    type_rules = {
        "true_false": """
- question_type يجب أن يكون true_false.
- options يجب أن تكون:
  {"1": "صح", "2": "خطأ"}
- correct_answer يجب أن يكون "صح" أو "خطأ".
""",
        "multiple_choice": """
- question_type يجب أن يكون multiple_choice.
- options يجب أن تكون قاموساً يحتوي 4 خيارات.
- correct_answer يجب أن يساوي نص أحد الخيارات.
""",
        "enumeration": """
- question_type يجب أن يكون enumeration.
- السؤال يجب أن يطلب تعداد عناصر أو نقاط موجودة في المصدر.
- correct_answer يجب أن يكون قائمة نصوص.
- لا تستخدم هذا النوع لسؤال لا يحتوي على إجابة تعداد واضحة.
""",
    }

    prompt = f"""
أنت مولّد اختبارات أكاديمية لمنصة LabBase
الخاصة بطلبة تقنيات المختبرات الطبية.

مهمتك إنشاء اختبار اعتماداً على SOURCE MATERIAL
الموجود أدناه فقط.

قواعد صارمة جداً:

1. ممنوع استخدام أي معلومة من خارج المصدر.
2. ممنوع اختراع معلومات غير موجودة في المصدر.
3. إذا كانت المعلومة غير موجودة بوضوح في المصدر فلا تستخدمها.
4. حافظ على المصطلحات العلمية الموجودة في المصدر.
5. الأسئلة يجب أن تكون مناسبة لطلبة الجامعة.
6. لا تجعل كل الأسئلة من نفس الفقرة.
7. غطِّ أجزاء مختلفة من المصدر قدر الإمكان.
8. لا تكرر نفس السؤال بصياغة مختلفة.
9. difficulty يجب أن تكون بالضبط:
   {difficulty}
10. question_type يجب أن تكون بالضبط:
   {question_type}
11. عدد الأسئلة يجب أن يكون:
   {question_count}

قواعد النوع:
{type_rules.get(question_type, "")}

أرجع JSON فقط بهذا الشكل:

{{
  "questions": [
    {{
      "question_type": "{question_type}",
      "difficulty": "{difficulty}",
      "question_text": "...",
      "options": {{}},
      "correct_answer": "...",
      "explanation": "..."
    }}
  ]
}}

explanation يجب أن يشرح الإجابة اعتماداً على المصدر
فقط، وباختصار.

SOURCE MATERIAL:
----------------
{source_text}
----------------
"""

    response = client.responses.create(
        model=OPENAI_MODEL,
        input=prompt,
    )

    output_text = response.output_text

    result = parse_ai_json(
        output_text
    )

    questions = result.get("questions")

    return validate_questions(
        questions=questions,
        question_type=question_type,
        difficulty=difficulty,
        expected_count=question_count,
    )


async def generate_questions(
    source_text,
    question_type,
    difficulty,
    question_count,
):
    return await asyncio.to_thread(
        _generate_questions_sync,
        source_text,
        question_type,
        difficulty,
        question_count,
    )
