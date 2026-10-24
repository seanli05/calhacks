"""Writes owned by the relay: ask_user questions (C10).

Answering and timing out are conditional on the question still being open, so when
a reply and the timeout race, exactly one wins. The loser gets None back.
"""

from sqlalchemy import update

from app.contracts import AskUserRequest, QuestionStatus
from app.contracts.common import QuestionId, UserId
from app.db import tables
from app.db.engine import session
from app.db.errors import must_get
from app.db.tables import utcnow


async def create_question(request: AskUserRequest, user_id: UserId) -> tables.Question:
    question = tables.Question(
        id=request.question_id,
        call_id=request.call_id,
        user_id=user_id,
        template=request.template,
        options_en=request.options_en,
        default_option=request.default_option,
        timeout_s=request.timeout_s,
    )
    async with session() as db:
        db.add(question)
        await db.commit()
        return question


async def _close_if_open(
    question_id: QuestionId, **values: object
) -> tables.Question | None:
    async with session() as db:
        result = await db.execute(
            update(tables.Question)
            .where(
                tables.Question.id == question_id,
                tables.Question.status == QuestionStatus.OPEN,
            )
            .values(**values)
            .returning(tables.Question)
        )
        question = result.scalar_one_or_none()
        await db.commit()
        return question


async def answer_question(
    question_id: QuestionId, choice: int
) -> tables.Question | None:
    """None means the question had already timed out: treat the reply as late (C24)."""
    return await _close_if_open(
        question_id,
        status=QuestionStatus.ANSWERED,
        choice=choice,
        answered_at=utcnow(),
    )


async def time_out_question(question_id: QuestionId) -> tables.Question | None:
    """None means the user answered first."""
    return await _close_if_open(question_id, status=QuestionStatus.TIMED_OUT)


async def record_late_reply(question_id: QuestionId) -> tables.Question:
    async with session() as db:
        question = await must_get(db, tables.Question, question_id)
        question.late_reply_at = utcnow()
        await db.commit()
        return question
