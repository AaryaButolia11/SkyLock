from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.schemas.agent import ChatRequest, ChatResponse
from app.services.agent_service import run_agent

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        history = [{"role": m.role, "content": m.content} for m in req.chat_history]
        reply = await run_agent(req.message, history, db, current_user)
        return ChatResponse(reply=reply)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")