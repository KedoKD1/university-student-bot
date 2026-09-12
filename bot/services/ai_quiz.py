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
    """
    Cleans common markdown wrapping around JSON.
    """
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
    """
    Parse AI JSON response safely.
    """
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

    # -------------------------
    # True / False
    # -------------------------
    if question_type == "true_false":

        required_keys = {"true", "false"}

        if set(options.keys()) != required_keys:
            return None

        answer = _normalize_text(correct_answer).lower()

        if answer not in {"true", "false"}:
            return None

        return {
            "question_type": "true_false",
            "question_text": question_text,
            "options": {
                "true": "صح",
                "false": "خطأ",
            },
            "correct_answer": answer,
            "explanation": explanation,
            "difficulty": difficulty,
        }

    # -------------------------
    # Multiple Choice
    # -------------------------
    if question_type == "multiple_choice":

        if len(options) != 4:
            return None

        option_keys = list(options.keys())

        if len(set(option_keys)) != 4:
            return None

        cleaned_options = {}

        for key in option_keys:
            value = _normalize_text(options.get(key))

            if not value:
                return None

            cleaned_options[str(key)] = value

        answer = _normalize_text(correct_answer)

        if answer not in cleaned_options:
            return None

        return {
            "question_type": "multiple_choice",
            "question_text": question_text,
            "options": cleaned_options,
            "correct_answer": answer,
            "explanation": explanation,
            "difficulty": difficulty,
        }

    # -------------------------
    # Enumeration
    # -------------------------
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
نوع الأسئلة: صح / خطأ.

كل سؤال يجب أن يحتوي على:
- options = {"true": "صح", "false": "خطأ"}
- correct_answer = "true" أو "false"
"""

    elif question_type == "multiple_choice":
        type_rules = """
نوع الأسئلة: اختيار من متعدد.

كل سؤال يجب أن يحتوي على:
- 4 خيارات بالضبط.
- مفاتيح الخيارات تكون A و B و C و D.
- correct_answer يجب أن يكون واحداً من A أو B أو C أو D.
"""

    elif question_type == "enumeration":
        type_rules = """
نوع الأسئلة: تعداد.

السؤال يجب أن يطلب من الطالب تعداد عناصر أو نقاط
موجودة بشكل واضح داخل المادة.

correct_answer يجب أن يكون قائمة تحتوي على جميع الإجابات الصحيحة،
وبحد أدنى عنصرين.
"""

    else:
        raise AIQuizError(
            "❌ نوع الاختبار غير مدعوم."
        )

    return f"""
أنت مولّد اختبارات أكاديمية لمنصة LabBase التعليمية
الخاصة بطلاب تقنيات المختبرات الطبية.

مهمتك إنشاء أسئلة اختبار اعتماداً على المادة المصدرية
الموجودة في نهاية هذا الطلب فقط.

قواعد صارمة جداً:

1. استخدم المعلومات الموجودة في المادة فقط.
2. ممنوع إضافة معلومات من خارج المادة.
3. ممنوع التخمين.
4. ممنوع اختراع معلومات غير موجودة.
5. إذا كانت المعلومة غير واضحة في المادة، لا تستخدمها.
6. الأسئلة يجب أن تكون أكاديمية وواضحة ومناسبة للطلاب.
7. لا تجعل السؤال يعتمد على معلومات خارج النص.
8. لا تكرر الأسئلة.
9. لا تجعل أكثر من إجابة صحيحة في سؤال الاختيار من متعدد.
10. يجب أن تكون الإجابة الصحيحة قابلة للإثبات من المادة.
11. لا تضع أي Markdown خارج JSON.
12. أرجع JSON فقط.
13. لغة السؤال والإجابة تكون عربية واضحة، مع إبقاء المصطلحات الطبية
    الإنجليزية كما تظهر في المادة عندما تكون مهمة.
14. مستوى الصعوبة المطلوب: {difficulty}.
15. عدد الأسئلة المطلوب: {count}.

{type_rules}

صيغة JSON المطلوبة:

{{
  "questions": [
    {{
      "question_type": "{question_type}",
      "question_text": "نص السؤال",
      "options": {{}},
      "correct_answer": "الإجابة",
      "explanation": "شرح مختصر مستند إلى المادة",
      "difficulty": "{difficulty}"
    }}
  ]
}}

المادة المصدرية:

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

    data = _parse_response(output_text)

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
