from pydantic import BaseModel, Field, validator
from typing import Optional, Any
from datetime import datetime
import re


class RecordCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, description="Заголовок записи")
    content: Optional[str] = Field(None, max_length=10000, description="Содержимое записи")

    @validator('title')
    def validate_title(cls, v):
        if not v or not v.strip():
            raise ValueError("Title cannot be empty or whitespace only")
        if re.search(r'[<>;\'"\\]', v):
            raise ValueError("Title contains invalid characters")
        return v.strip()

    @validator('content')
    def validate_content(cls, v):
        if v and not v.strip():
            return None
        return v


class RecordUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    content: Optional[str] = Field(None, max_length=10000)

    @validator('title')
    def validate_title(cls, v):
        if v is not None:
            if not v.strip():
                raise ValueError("Title cannot be empty or whitespace only")
            if re.search(r'[<>;\'"\\]', v):
                raise ValueError("Title contains invalid characters")
            return v.strip()
        return v

    @validator('content')
    def validate_content(cls, v):
        if v and not v.strip():
            return None
        return v


class RecordResponse(BaseModel):
    id: int
    title: str
    content: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AuditEvent(BaseModel):
    event_id: str
    record_id: int
    action: str
    old_data: Optional[dict] = None
    new_data: Optional[dict] = None
    timestamp: datetime
    user_id: Optional[str] = "system"
    ip_address: Optional[str] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }