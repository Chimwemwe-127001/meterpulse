"""
User Schemas
Pydantic models for user request/response validation.
"""
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    """Shared user fields."""
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=100)


class UserCreate(UserBase):
    """Schema for user registration."""
    password: str = Field(..., min_length=8, max_length=100)
    role: str = Field(default="operator", pattern="^(admin|operator)$")


class UserResponse(UserBase):
    """Schema for user response (excludes password)."""
    id: UUID
    role: str
    created_at: datetime

    class Config:
        from_attributes = True


class UserLogin(BaseModel):
    """Schema for login request."""
    email: EmailStr
    password: str


class Token(BaseModel):
    """Schema for JWT token response."""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class TokenData(BaseModel):
    """Schema for decoded JWT payload."""
    user_id: str | None = None
    email: str | None = None
