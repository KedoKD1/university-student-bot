"""
LabBase / University Student Bot
Comprehensive diagnostic for quiz leaderboard points.

SAFE MODE:
- Does NOT modify production Supabase data.
- Uses a fake Supabase client for the INSERT test.
- Executes the real award_quiz_points() function.
- Checks scoring.
- Checks user resolution.
- Checks quiz_id.
- Checks the exact INSERT payload.
- Simulates the PostgreSQL NOT NULL failure.

Run:
    python tests/diagnose_leaderboard_points.py
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import os
import sys
from pathlib import Path


# ============================================================
# Project root
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"


# ============================================================
# Fake Supabase response
# ============================================================

class FakeResponse:

    def __init__(self, data=None):
        self.data = data if data is not None else []


# ============================================================
# Fake Supabase query
# ============================================================

class FakeQuery:

    def __init__(
        self,
        table_name: str,
        client: "FakeSupabase",
    ):
        self.table_name = table_name
        self.client = client
        self.operation = None
        self.payload = None

    def select(self, *columns):
        self.operation = "select"
        return self

    def insert(self, payload):
        self.operation = "insert"
        self.payload = payload

        self.client.last_insert_payload = payload

        return self

    def eq(self, column, value):
        return self

    def gte(self, column, value):
        return self

    def limit(self, value):
        return self

    def execute(self):

        # ----------------------------------------------------
        # SELECT
        # ----------------------------------------------------

        if self.operation == "select":

            if self.table_name == "leaderboard_points":
                return FakeResponse([])

            if self.table_name == "users":
                return FakeResponse([
                    {
                        "id": 1,
                    }
                ])

            return FakeResponse([])

        # ----------------------------------------------------
        # INSERT
        # ----------------------------------------------------

        if self.operation == "insert":

            payload = self.payload or {}

            # Simulate the exact database error
            # currently appearing in Railway.
            if payload.get("quiz_id") is None:

                raise RuntimeError(
                    'null value in column "quiz_id" '
                    'of relation "leaderboard_points" '
                    'violates not-null constraint'
                )

            return FakeResponse([
                {
                    "id": 999,
                    **payload,
                }
            ])

        raise RuntimeError(
            f"Unsupported fake Supabase operation: "
            f"{self.operation}"
        )


# ============================================================
# Fake Supabase client
# ============================================================

class FakeSupabase:

    def __init__(self):

        self.last_insert_payload = None

    def table(self, table_name):

        return FakeQuery(
            table_name,
            self,
        )


# ============================================================
# Result helper
# ============================================================

def print_result(
    name: str,
    status: str,
    detail: str = "",
):

    suffix = ""

    if detail:
        suffix = f" — {detail}"

    print(
        f"[{status}] {name}{suffix}"
    )


# ============================================================
# Source-code audit
# ============================================================

def audit_payload_source(
    leaderboard_module,
):

    try:

        source = inspect.getsource(
            leaderboard_module.award_quiz_points
        )

        tree = ast.parse(source)

    except Exception as exc:

        return (
            False,
            (
                "Could not inspect award_quiz_points(): "
                f"{type(exc).__name__}: {exc}"
            ),
        )

    payload_found = False
    quiz_id_added = False

    # --------------------------------------------------------
    # Search payload construction
    # --------------------------------------------------------

    for node in ast.walk(tree):

        if not isinstance(
            node,
            ast.Assign,
        ):
            continue

        for target in node.targets:

            # payload = {...}
            if (
                isinstance(
                    target,
                    ast.Name,
                )
                and target.id == "payload"
            ):

                payload_found = True

                if isinstance(
                    node.value,
                    ast.Dict,
                ):

                    for key in node.value.keys:

                        if (
                            isinstance(
                                key,
                                ast.Constant,
                            )
                            and key.value == "quiz_id"
                        ):

                            quiz_id_added = True

            # payload["quiz_id"] = ...
            if isinstance(
                target,
                ast.Subscript,
            ):

                if (
                    isinstance(
                        target.value,
                        ast.Name,
                    )
                    and target.value.id == "payload"
                ):

                    if (
                        isinstance(
                            target.slice,
                            ast.Constant,
                        )
                        and target.slice.value == "quiz_id"
                    ):

                        quiz_id_added = True

    if not payload_found:

        return (
            False,
            "No payload construction found.",
        )

    if not quiz_id_added:

        return (
            False,
            (
                "CRITICAL: quiz_id is NOT added "
                "to payload before INSERT."
            ),
        )

    return (
        True,
        (
            "quiz_id is included in the INSERT "
            "payload construction."
        ),
    )


# ============================================================
# Scoring audit
# ============================================================

def audit_scoring(
    leaderboard_module,
):

    cases = [

        # difficulty, questions, correct, expected
        (
            "easy",
            5,
            3,
            5,
        ),

        (
            "medium",
            5,
            2,
            6,
        ),

        (
            "hard",
            10,
            10,
            35,
        ),

        (
            "easy",
            5,
            0,
            0,
        ),

        (
            "medium",
            1,
            1,
            2,
        ),
    ]

    failures = []

    for (
        difficulty,
        question_count,
        correct_count,
        expected,
    ) in cases:

        try:

            actual = (
                leaderboard_module
                .get_points_for_quiz(
                    difficulty,
                    question_count,
                    correct_count,
                )
            )

        except Exception as exc:

            failures.append(
                (
                    f"{difficulty}/"
                    f"{question_count}/"
                    f"{correct_count}: "
                    f"{type(exc).__name__}: {exc}"
                )
            )

            continue

        if actual != expected:

            failures.append(
                (
                    f"{difficulty}/"
                    f"{question_count}/"
                    f"{correct_count}: "
                    f"expected {expected}, "
                    f"got {actual}"
                )
            )

    if failures:

        return (
            False,
            "; ".join(failures),
        )

    return (
        True,
        "All known scoring cases passed.",
    )


# ============================================================
# Runtime INSERT test
# ============================================================

async def runtime_insert_test(
    leaderboard_module,
):

    fake_supabase = FakeSupabase()

    original_supabase = (
        leaderboard_module.supabase
    )

    original_resolver = (
        leaderboard_module.get_internal_user_id
    )

    # --------------------------------------------------------
    # Fake internal user resolver
    # --------------------------------------------------------

    async def fake_resolver(
        telegram_id,
    ):

        return 1

    leaderboard_module.supabase = (
        fake_supabase
    )

    leaderboard_module.get_internal_user_id = (
        fake_resolver
    )

    try:

        # ----------------------------------------------------
        # Execute REAL production function
        # ----------------------------------------------------

        result = (
            await leaderboard_module
            .award_quiz_points(
                telegram_id=8521349569,
                difficulty="easy",
                question_count=5,
                correct_count=3,
                user_id=1,
                quiz_id=30,
            )
        )

        payload = (
            fake_supabase.last_insert_payload
        )

        print()
        print(
            "================================================"
        )
        print(
            "CAPTURED INSERT PAYLOAD"
        )
        print(
            "================================================"
        )

        print(payload)

        print()
        print(
            "================================================"
        )
        print(
            "FUNCTION RESULT"
        )
        print(
            "================================================"
        )

        print(result)

        print()

        # ----------------------------------------------------
        # Verify INSERT happened
        # ----------------------------------------------------

        if payload is None:

            return (
                False,
                (
                    "award_quiz_points() "
                    "never attempted an INSERT."
                ),
            )

        # ----------------------------------------------------
        # Verify quiz_id
        # ----------------------------------------------------

        if payload.get(
            "quiz_id"
        ) != 30:

            return (
                False,
                (
                    "CRITICAL: quiz_id is missing "
                    "from INSERT payload. "
                    f"Expected 30, got "
                    f"{payload.get('quiz_id')!r}."
                ),
            )

        # ----------------------------------------------------
        # Verify user_id
        # ----------------------------------------------------

        if payload.get(
            "user_id"
        ) != 1:

            return (
                False,
                (
                    "user_id is incorrect. "
                    f"Expected 1, got "
                    f"{payload.get('user_id')!r}."
                ),
            )

        # ----------------------------------------------------
        # Verify points
        # ----------------------------------------------------

        if payload.get(
            "points"
        ) != 5:

            return (
                False,
                (
                    "points are incorrect. "
                    f"Expected 5, got "
                    f"{payload.get('points')!r}."
                ),
            )

        # ----------------------------------------------------
        # Verify reason
        # ----------------------------------------------------

        if payload.get(
            "reason"
        ) != "quiz:easy:5:3":

            return (
                False,
                (
                    "reason is incorrect. "
                    f"Expected "
                    "'quiz:easy:5:3', got "
                    f"{payload.get('reason')!r}."
                ),
            )

        # ----------------------------------------------------
        # Verify result
        # ----------------------------------------------------

        if result.get(
            "awarded_points"
        ) != 5:

            return (
                False,
                (
                    "awarded_points is incorrect. "
                    f"Expected 5, got "
                    f"{result.get('awarded_points')!r}."
                ),
            )

        if result.get(
            "error"
        ) is not None:

            return (
                False,
                (
                    "Function returned an error: "
                    f"{result.get('error')!r}"
                ),
            )

        return (
            True,
            (
                "Real award_quiz_points() generated "
                "a valid payload and the fake "
                "Supabase INSERT succeeded."
            ),
        )

    finally:

        # Restore real objects
        leaderboard_module.supabase = (
            original_supabase
        )

        leaderboard_module.get_internal_user_id = (
            original_resolver
        )


# ============================================================
# Environment audit
# ============================================================

def audit_environment():

    required = [
        "SUPABASE_URL",
        "SUPABASE_KEY",
    ]

    missing = []

    for variable in required:

        if not os.getenv(variable):

            missing.append(
                variable
            )

    if missing:

        return (
            False,
            (
                "Missing environment variables: "
                + ", ".join(missing)
            ),
        )

    return (
        True,
        "Required Supabase variables are present.",
    )


# ============================================================
# Main diagnostic
# ============================================================

async def main():

    print()
    print(
        "=" * 72
    )
    print(
        "LABBASE — LEADERBOARD POINTS FULL DIAGNOSTIC"
    )
    print(
        "=" * 72
    )

    print()
    print(
        "SAFE MODE:"
    )
    print(
        "This test DOES NOT modify production Supabase."
    )

    print()

    # --------------------------------------------------------
    # Environment
    # --------------------------------------------------------

    environment_ok, environment_detail = (
        audit_environment()
    )

    print_result(
        "Environment",
        (
            PASS
            if environment_ok
            else WARN
        ),
        environment_detail,
    )

    # --------------------------------------------------------
    # Import leaderboard
    # --------------------------------------------------------

    try:

        from bot.handlers import leaderboard

    except Exception as exc:

        print_result(
            "Leaderboard import",
            FAIL,
            (
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        )

        print()
        print(
            "FINAL RESULT: FAIL"
        )
        print(
            "The leaderboard module cannot be imported."
        )

        return 1

    print_result(
        "Leaderboard import",
        PASS,
        "bot.handlers.leaderboard imported successfully.",
    )

    # --------------------------------------------------------
    # Source audit
    # --------------------------------------------------------

    source_ok, source_detail = (
        audit_payload_source(
            leaderboard
        )
    )

    print_result(
        "INSERT payload source audit",
        (
            PASS
            if source_ok
            else FAIL
        ),
        source_detail,
    )

    # --------------------------------------------------------
    # Scoring
    # --------------------------------------------------------

    scoring_ok, scoring_detail = (
        audit_scoring(
            leaderboard
        )
    )

    print_result(
        "Quiz scoring audit",
        (
            PASS
            if scoring_ok
            else FAIL
        ),
        scoring_detail,
    )

    # --------------------------------------------------------
    # Runtime
    # --------------------------------------------------------

    runtime_ok, runtime_detail = (
        await runtime_insert_test(
            leaderboard
        )
    )

    print_result(
        "Runtime INSERT audit",
        (
            PASS
            if runtime_ok
            else FAIL
        ),
        runtime_detail,
    )

    # --------------------------------------------------------
    # Final result
    # --------------------------------------------------------

    print()
    print(
        "=" * 72
    )

    if (
        source_ok
        and scoring_ok
        and runtime_ok
    ):

        print(
            "FINAL RESULT: PASS"
        )

        print()
        print(
            "The currently executed Python code "
            "correctly puts quiz_id inside the "
            "INSERT payload."
        )

        print()
        print(
            "If Railway still shows:"
        )

        print(
            "  'payload': {'user_id': 1, "
            "'points': 5, 'reason': ...}, "
            "'quiz_id': 30"
        )

        print()
        print(
            "then Railway is NOT running the same "
            "source version tested here."
        )

        print()
        print(
            "Check Railway deployment commit, "
            "branch, replicas, and duplicate "
            "bot instances."
        )

        return 0

    print(
        "FINAL RESULT: FAIL"
    )

    print()
    print(
        "A real failure was detected above."
    )

    print(
        "Use the first FAIL message as the "
        "root-cause indicator."
    )

    print(
        "Do NOT change the scoring formula blindly."
    )

    return 1


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":

    raise SystemExit(
        asyncio.run(
            main()
        )
    )
