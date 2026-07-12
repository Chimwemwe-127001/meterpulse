"""
User Schemas
Pydantic models for user request/response validation.
"""
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, field_validator


class UserBase(BaseModel):
    """Shared user fields."""
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=100)


class UserCreate(UserBase):
    """
    Schema for user registration.

    Note: `role` is intentionally NOT accepted here. Trust levels must
    never be client-assigned (mass assignment, CWE-915); all new accounts
    are operators and promotion is a separate, admin-only action.
    """
    password: str = Field(..., min_length=8, max_length=100)

    @field_validator("password")
    @classmethod
    def password_within_bcrypt_limit(cls, v: str) -> str:
        # bcrypt silently truncates input at 72 bytes; reject anything
        # longer so no part of the password is ignored.
        if len(v.encode("utf-8")) > 72:
            raise ValueError("password must be at most 72 bytes")
        return v


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
