"""
chatbot.py

POST /api/chatbot/query     -- send a message, get a data-grounded answer (see orchestrator.py).
GET  /api/chatbot/history/{conversation_id} -- recent turns for a conversation the user owns.

Role authorization: any authenticated user (ADMIN, PHARMACIST, BLOOD_STAFF) can talk to the
chatbot; which TOOLS it may actually invoke on their behalf is enforced per-call inside
app/chatbot/tools.py, not here -- so a crafted prompt can never grant a Pharmacist blood data
or vice versa.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.chatbot import conversation
from app.chatbot.orchestrator import handle_message
from app.dependencies import get_current_user
from app.schemas.auth import Role
from app.schemas.chatbot import ChatRequest, ChatResponse, ConversationHistory
from app.utils.errors import ServiceError

router = APIRouter(prefix="/api/chatbot", tags=["chatbot"])


@router.post("/query", response_model=ChatResponse)
def query(body: ChatRequest, user: dict = Depends(get_current_user)):
    try:
        return handle_message(user, body.conversation_id, body.message)
    except ServiceError as e:
        raise HTTPException(e.status_code, e.message)


@router.get("/history/{conversation_id}", response_model=ConversationHistory)
def history(conversation_id: str, user: dict = Depends(get_current_user)):
    conv = conversation.get_conversation(conversation_id, user["id"])
    if not conv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
    msgs = conversation.recent_messages(conversation_id, limit=50)
    return {"conversation_id": conversation_id, "messages": msgs}
