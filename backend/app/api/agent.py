from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import AgentRun, User
from app.schemas import AgentChatRequest, AgentChatResponse, ToolCallRecord
from app.services.agent_service import run_agent

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/chat", response_model=AgentChatResponse)
def chat(
    payload: AgentChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AgentChatResponse:
    answer, run_id = run_agent(db, user.tenant_id, user.id, payload.message)
    return AgentChatResponse(
        run_id=run_id,
        answer=answer.answer,
        tool_calls=[
            ToolCallRecord(
                tool=call.tool,
                arguments=call.arguments,
                result_summary=call.result_summary,
                ok=call.ok,
            )
            for call in answer.tool_calls
        ],
        status=answer.status,
        pending_purchase_order_id=answer.pending_purchase_order_id,
        model=answer.model,
        latency_ms=answer.latency_ms,
    )


@router.get("/runs")
def list_runs(
    limit: int = 20,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    runs = (
        db.query(AgentRun)
        .filter(AgentRun.tenant_id == user.tenant_id)
        .order_by(AgentRun.created_at.desc())
        .limit(min(limit, 100))
        .all()
    )
    return [
        {
            "id": run.id,
            "question": run.question,
            "answer": run.answer,
            "status": run.status,
            "model": run.model,
            "latency_ms": run.latency_ms,
            "tool_calls": run.tool_calls,
            "created_at": run.created_at,
        }
        for run in runs
    ]
