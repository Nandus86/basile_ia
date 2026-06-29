"""
Q&A Eval API — Evaluation and Training Data Curation
Endpoints for managing conversation pair evaluations and exporting curated training data.
"""
import uuid
import json
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()


# ─── Pydantic Schemas ─────────────────────────────────────────
class EvaluationCreate(BaseModel):
    message_id: str
    pair_message_id: Optional[str] = None
    agent_id: str
    session_id: str
    classification: str = Field(..., pattern="^(relevant|indifferent|irrelevant)$")
    score: Optional[int] = Field(None, ge=0, le=100)
    topic: Optional[str] = None
    expected_response: Optional[str] = None
    tool_instruction: Optional[str] = None
    original_question: str
    original_answer: str
    tool_trace: Optional[dict] = None


class EvaluationUpdate(BaseModel):
    classification: Optional[str] = Field(None, pattern="^(relevant|indifferent|irrelevant)$")
    score: Optional[int] = Field(None, ge=0, le=100)
    topic: Optional[str] = None
    expected_response: Optional[str] = None
    tool_instruction: Optional[str] = None


# ─── GET /pairs — List Q&A pairs from MTM ─────────────────────
@router.get("/pairs")
async def list_qa_pairs(
    agent_id: Optional[str] = None,
    session_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List conversation pairs (user→assistant) with evaluation status."""
    from app.database import AsyncSessionLocal
    from app.models.conversation_message import ConversationMessage
    from app.models.qa_evaluation import QAEvaluation
    from sqlalchemy import select, func, desc, and_

    async with AsyncSessionLocal() as db:
        # Build base filters
        base_filters = [ConversationMessage.role.in_(["user", "assistant"])]
        if agent_id:
            base_filters.append(ConversationMessage.agent_id == uuid.UUID(agent_id))
        if session_id:
            base_filters.append(ConversationMessage.session_id == session_id)

        # Get total count of assistant messages (each represents a pair)
        count_q = (
            select(func.count())
            .select_from(ConversationMessage)
            .where(
                ConversationMessage.role == "assistant",
                *([ConversationMessage.agent_id == uuid.UUID(agent_id)] if agent_id else []),
                *([ConversationMessage.session_id == session_id] if session_id else []),
            )
        )
        total_result = await db.execute(count_q)
        total = total_result.scalar_one() or 0

        # Get assistant messages with pagination (newest first)
        offset = (page - 1) * page_size
        assistant_q = (
            select(ConversationMessage)
            .where(
                ConversationMessage.role == "assistant",
                *([ConversationMessage.agent_id == uuid.UUID(agent_id)] if agent_id else []),
                *([ConversationMessage.session_id == session_id] if session_id else []),
            )
            .order_by(desc(ConversationMessage.created_at))
            .offset(offset)
            .limit(page_size)
        )
        result = await db.execute(assistant_q)
        assistant_msgs = result.scalars().all()

        pairs = []
        for assistant_msg in assistant_msgs:
            # Find the user message that came right before this assistant message
            user_q = (
                select(ConversationMessage)
                .where(
                    ConversationMessage.agent_id == assistant_msg.agent_id,
                    ConversationMessage.session_id == assistant_msg.session_id,
                    ConversationMessage.role == "user",
                    ConversationMessage.created_at < assistant_msg.created_at,
                )
                .order_by(desc(ConversationMessage.created_at))
                .limit(1)
            )
            user_result = await db.execute(user_q)
            user_msg = user_result.scalar_one_or_none()

            # Check if evaluation exists
            eval_q = select(QAEvaluation).where(QAEvaluation.message_id == assistant_msg.id)
            eval_result = await db.execute(eval_q)
            evaluation = eval_result.scalar_one_or_none()

            pairs.append({
                "assistant_message": {
                    "id": str(assistant_msg.id),
                    "content": assistant_msg.content,
                    "created_at": assistant_msg.created_at.isoformat() if assistant_msg.created_at else None,
                    "tool_trace": assistant_msg.tool_trace,
                },
                "user_message": {
                    "id": str(user_msg.id) if user_msg else None,
                    "content": user_msg.content if user_msg else "[Mensagem não encontrada]",
                    "created_at": user_msg.created_at.isoformat() if user_msg and user_msg.created_at else None,
                } if user_msg else None,
                "agent_id": str(assistant_msg.agent_id),
                "session_id": assistant_msg.session_id,
                "evaluation": {
                    "id": str(evaluation.id),
                    "classification": evaluation.classification,
                    "score": evaluation.score,
                    "topic": evaluation.topic,
                    "expected_response": evaluation.expected_response,
                    "tool_instruction": evaluation.tool_instruction,
                } if evaluation else None,
            })

        return {
            "pairs": pairs,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
        }


# ─── POST /evaluations — Create evaluation ─────────────────────
@router.post("/evaluations")
async def create_evaluation(data: EvaluationCreate):
    """Create or update an evaluation for a conversation pair."""
    from app.database import AsyncSessionLocal
    from app.models.qa_evaluation import QAEvaluation
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        # Check if evaluation already exists for this message
        existing_q = select(QAEvaluation).where(
            QAEvaluation.message_id == uuid.UUID(data.message_id)
        )
        result = await db.execute(existing_q)
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing
            existing.classification = data.classification
            if data.score is not None:
                existing.score = data.score
            if data.topic is not None:
                existing.topic = data.topic
            if data.expected_response is not None:
                existing.expected_response = data.expected_response
            if data.tool_instruction is not None:
                existing.tool_instruction = data.tool_instruction
            existing.updated_at = datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(existing)
            return {
                "status": "updated",
                "evaluation": _eval_to_dict(existing),
            }

        # Create new
        evaluation = QAEvaluation(
            id=uuid.uuid4(),
            message_id=uuid.UUID(data.message_id),
            pair_message_id=uuid.UUID(data.pair_message_id) if data.pair_message_id else None,
            agent_id=uuid.UUID(data.agent_id),
            session_id=data.session_id,
            classification=data.classification,
            score=data.score,
            topic=data.topic,
            expected_response=data.expected_response,
            tool_instruction=data.tool_instruction,
            original_question=data.original_question,
            original_answer=data.original_answer,
            tool_trace=data.tool_trace,
        )
        db.add(evaluation)
        await db.commit()
        await db.refresh(evaluation)
        return {
            "status": "created",
            "evaluation": _eval_to_dict(evaluation),
        }


# ─── GET /evaluations — List evaluations ─────────────────────
@router.get("/evaluations")
async def list_evaluations(
    agent_id: Optional[str] = None,
    classification: Optional[str] = None,
    min_score: Optional[int] = Query(None, ge=0, le=100),
    topic: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List evaluations with filters."""
    from app.database import AsyncSessionLocal
    from app.models.qa_evaluation import QAEvaluation
    from sqlalchemy import select, func, desc

    async with AsyncSessionLocal() as db:
        filters = []
        if agent_id:
            filters.append(QAEvaluation.agent_id == uuid.UUID(agent_id))
        if classification:
            filters.append(QAEvaluation.classification == classification)
        if min_score is not None:
            filters.append(QAEvaluation.score >= min_score)
        if topic:
            filters.append(QAEvaluation.topic.ilike(f"%{topic}%"))

        # Count
        count_q = select(func.count()).select_from(QAEvaluation)
        for f in filters:
            count_q = count_q.where(f)
        total_result = await db.execute(count_q)
        total = total_result.scalar_one() or 0

        # Fetch
        offset = (page - 1) * page_size
        q = (
            select(QAEvaluation)
            .order_by(desc(QAEvaluation.updated_at))
            .offset(offset)
            .limit(page_size)
        )
        for f in filters:
            q = q.where(f)

        result = await db.execute(q)
        evaluations = result.scalars().all()

        return {
            "evaluations": [_eval_to_dict(e) for e in evaluations],
            "total": total,
            "page": page,
            "page_size": page_size,
        }


# ─── PUT /evaluations/{id} — Update evaluation ─────────────────
@router.put("/evaluations/{evaluation_id}")
async def update_evaluation(evaluation_id: str, data: EvaluationUpdate):
    """Update an existing evaluation."""
    from app.database import AsyncSessionLocal
    from app.models.qa_evaluation import QAEvaluation
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        q = select(QAEvaluation).where(QAEvaluation.id == uuid.UUID(evaluation_id))
        result = await db.execute(q)
        evaluation = result.scalar_one_or_none()

        if not evaluation:
            raise HTTPException(status_code=404, detail="Evaluation not found")

        if data.classification is not None:
            evaluation.classification = data.classification
        if data.score is not None:
            evaluation.score = data.score
        if data.topic is not None:
            evaluation.topic = data.topic
        if data.expected_response is not None:
            evaluation.expected_response = data.expected_response
        if data.tool_instruction is not None:
            evaluation.tool_instruction = data.tool_instruction

        evaluation.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(evaluation)

        return {"status": "updated", "evaluation": _eval_to_dict(evaluation)}


# ─── DELETE /evaluations/{id} — Delete evaluation ──────────────
@router.delete("/evaluations/{evaluation_id}")
async def delete_evaluation(evaluation_id: str):
    """Delete an evaluation."""
    from app.database import AsyncSessionLocal
    from app.models.qa_evaluation import QAEvaluation
    from sqlalchemy import select, delete as sa_delete

    async with AsyncSessionLocal() as db:
        q = sa_delete(QAEvaluation).where(QAEvaluation.id == uuid.UUID(evaluation_id))
        result = await db.execute(q)
        await db.commit()
        return {"status": "deleted", "deleted_count": result.rowcount}


# ─── GET /stats — Evaluation statistics ────────────────────────
@router.get("/stats")
async def get_stats(agent_id: Optional[str] = None):
    """Get evaluation statistics."""
    from app.database import AsyncSessionLocal
    from app.models.qa_evaluation import QAEvaluation
    from app.models.conversation_message import ConversationMessage
    from sqlalchemy import select, func, case

    async with AsyncSessionLocal() as db:
        # Total conversation pairs
        pairs_q = select(func.count()).select_from(ConversationMessage).where(
            ConversationMessage.role == "assistant"
        )
        if agent_id:
            pairs_q = pairs_q.where(ConversationMessage.agent_id == uuid.UUID(agent_id))
        pairs_result = await db.execute(pairs_q)
        total_pairs = pairs_result.scalar_one() or 0

        # Evaluation filters
        eval_filters = []
        if agent_id:
            eval_filters.append(QAEvaluation.agent_id == uuid.UUID(agent_id))

        # Total evaluated
        eval_count_q = select(func.count()).select_from(QAEvaluation)
        for f in eval_filters:
            eval_count_q = eval_count_q.where(f)
        eval_result = await db.execute(eval_count_q)
        total_evaluated = eval_result.scalar_one() or 0

        # Average score
        avg_q = select(func.avg(QAEvaluation.score)).where(QAEvaluation.score.isnot(None))
        for f in eval_filters:
            avg_q = avg_q.where(f)
        avg_result = await db.execute(avg_q)
        avg_score = avg_result.scalar_one()

        # Classification distribution
        class_q = select(
            QAEvaluation.classification,
            func.count().label("count"),
        ).group_by(QAEvaluation.classification)
        for f in eval_filters:
            class_q = class_q.where(f)
        class_result = await db.execute(class_q)
        classification_dist = {row.classification: row.count for row in class_result.all()}

        # Top topics
        topics_q = (
            select(QAEvaluation.topic, func.count().label("count"))
            .where(QAEvaluation.topic.isnot(None), QAEvaluation.topic != "")
            .group_by(QAEvaluation.topic)
            .order_by(func.count().desc())
            .limit(20)
        )
        for f in eval_filters:
            topics_q = topics_q.where(f)
        topics_result = await db.execute(topics_q)
        top_topics = [{"topic": row.topic, "count": row.count} for row in topics_result.all()]

        # Messages with tool_trace
        trace_q = select(func.count()).select_from(ConversationMessage).where(
            ConversationMessage.role == "assistant",
            ConversationMessage.tool_trace.isnot(None),
        )
        if agent_id:
            trace_q = trace_q.where(ConversationMessage.agent_id == uuid.UUID(agent_id))
        trace_result = await db.execute(trace_q)
        total_with_trace = trace_result.scalar_one() or 0

        return {
            "total_pairs": total_pairs,
            "total_evaluated": total_evaluated,
            "evaluation_progress": round((total_evaluated / total_pairs * 100), 1) if total_pairs > 0 else 0,
            "average_score": round(float(avg_score), 1) if avg_score else None,
            "classification_distribution": classification_dist,
            "top_topics": top_topics,
            "total_with_tool_trace": total_with_trace,
        }


# ─── GET /topics — List existing topics ────────────────────────
@router.get("/topics")
async def list_topics():
    """List all unique topics used in evaluations (for autocomplete)."""
    from app.database import AsyncSessionLocal
    from app.models.qa_evaluation import QAEvaluation
    from sqlalchemy import select, func

    async with AsyncSessionLocal() as db:
        q = (
            select(QAEvaluation.topic, func.count().label("count"))
            .where(QAEvaluation.topic.isnot(None), QAEvaluation.topic != "")
            .group_by(QAEvaluation.topic)
            .order_by(func.count().desc())
        )
        result = await db.execute(q)
        topics = [{"topic": row.topic, "count": row.count} for row in result.all()]
        return {"topics": topics}


# ─── GET /export — Export curated data as JSONL ─────────────────
@router.get("/export")
async def export_training_data(
    min_score: int = Query(80, ge=0, le=100),
    classification: str = Query("relevant"),
    format: str = Query("jsonl"),
):
    """Export curated Q&A pairs for fine-tuning/training."""
    from app.database import AsyncSessionLocal
    from app.models.qa_evaluation import QAEvaluation
    from sqlalchemy import select
    from fastapi.responses import StreamingResponse
    import io

    async with AsyncSessionLocal() as db:
        q = (
            select(QAEvaluation)
            .where(
                QAEvaluation.classification == classification,
                QAEvaluation.score >= min_score,
            )
            .order_by(QAEvaluation.created_at)
        )
        result = await db.execute(q)
        evaluations = result.scalars().all()

        lines = []
        for e in evaluations:
            entry = {
                "instruction": e.original_question,
                "output": e.expected_response if e.expected_response else e.original_answer,
                "score": e.score,
                "topic": e.topic,
            }
            if e.tool_instruction:
                entry["tool_instruction"] = e.tool_instruction
            if e.tool_trace:
                entry["tool_trace"] = e.tool_trace

            lines.append(json.dumps(entry, ensure_ascii=False))

        content = "\n".join(lines)

        return StreamingResponse(
            io.BytesIO(content.encode("utf-8")),
            media_type="application/jsonl",
            headers={
                "Content-Disposition": f"attachment; filename=qa_eval_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
            },
        )


# ─── Helper ────────────────────────────────────────────────────
def _eval_to_dict(e) -> dict:
    return {
        "id": str(e.id),
        "message_id": str(e.message_id),
        "pair_message_id": str(e.pair_message_id) if e.pair_message_id else None,
        "agent_id": str(e.agent_id),
        "session_id": e.session_id,
        "classification": e.classification,
        "score": e.score,
        "topic": e.topic,
        "expected_response": e.expected_response,
        "tool_instruction": e.tool_instruction,
        "original_question": e.original_question,
        "original_answer": e.original_answer,
        "tool_trace": e.tool_trace,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }
