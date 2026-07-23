from pydantic import BaseModel

class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str

class ChatRequest(BaseModel):
    message: str
    chat_history: list[ChatMessage] = []

class ChatResponse(BaseModel):
    reply: str