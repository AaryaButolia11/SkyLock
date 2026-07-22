from pydantic import BaseModel, EmailStr
from datetime import datetime

class UserCreate(BaseModel):
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: int
    email: EmailStr
    created_at: datetime

    class Config:
        from_attributes = True   # lets Pydantic read SQLAlchemy objects directly

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    
    
'''
User (the SQLAlchemy model) has hashed_password — you never want to accidentally return that in an API response. UserOut deliberately excludes it. This separation (DB model vs API schema) is a core FastAPI pattern interviewers specifically look for.
'''
