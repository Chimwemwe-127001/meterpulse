"""
Authentication Router
Endpoints for user registration, login, and profile.

Endpoints are plain `def`, not `async def`: bcrypt hashing (~100ms) and
DB access are blocking, and sync handlers run in Starlette's threadpool
instead of stalling the event loop.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.rate_limit import limiter
from app.schemas.user import UserCreate, UserResponse, Token
from app.services.auth import (
    verify_password,
    get_password_hash,
    create_access_token,
    get_current_user,
    burn_password_check,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/hour")
def register(
    request: Request,
    user_data: UserCreate,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """
    Register a new user account.

    - **email**: Unique email address
    - **password**: 8-72 characters
    - **full_name**: Display name (2-100 characters)

    All new accounts are created as operators; admin promotion is a
    separate administrative action.
    """
    new_user = User(
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        role="operator",
    )
    db.add(new_user)
    try:
        db.commit()
    except IntegrityError:
        # Unique index on email is the authoritative check; a pre-query
        # would race with concurrent registrations (TOCTOU, CWE-367).
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    db.refresh(new_user)

    return new_user


@router.post("/login", response_model=Token)
@limiter.limit("10/minute")
def login(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """
    Authenticate and receive a JWT access token.

    Use the returned token in the Authorization header:
    `Authorization: Bearer <token>`

    - **username**: Email address
    - **password**: Account password
    """
    user = db.query(User).filter(User.email == form_data.username).first()

    if user:
        authenticated = verify_password(form_data.password, user.hashed_password)
    else:
        # Unknown email: burn one bcrypt verification anyway so response
        # timing doesn't reveal which emails are registered (CWE-208).
        burn_password_check(form_data.password)
        authenticated = False

    if not authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email}
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user,
    }


@router.get("/me", response_model=UserResponse)
def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """
    Get the current authenticated user's profile.

    Requires valid JWT token in Authorization header.
    """
    return current_user
