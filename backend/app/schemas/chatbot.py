"""Pydantic models for the chatbot API."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    conversation_id: Optional[str] = Field(default=None, max_length=36)
    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    conversation_id: str
    message: str
    intent: Optional[str] = None
    data_sources: list = []
    tool_calls: list = []


class ChatMessageOut(BaseModel):
    role: str
    content: str
    intent: Optional[str] = None
    created_at: Optional[datetime] = None


class ConversationHistory(BaseModel):
    conversation_id: str
    messages: list[ChatMessageOut]
