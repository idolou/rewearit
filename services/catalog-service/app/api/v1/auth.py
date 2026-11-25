"""Authentication endpoints: register, login, and current user profile."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.auth import (
    AuthenticatedUser,
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.core.database import get_session
from app.models.user import AuthTokenResponse, LoginRequest, RegisterRequest, User, UserPublic

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _normalize_email(email: str) -> str:
    cleaned = email.strip().lower()
    if "@" not in cleaned or "." not in cleaned.split("@", 1)[1]:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid email address")
    return cleaned


@router.post("/register", response_model=AuthTokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    req: RegisterRequest,
    session: AsyncSession = Depends(get_session),
) -> AuthTokenResponse:
    """Register a new marketplace account (can both buy and sell)."""
    email = _normalize_email(req.email)
    existing = await session.execute(select(User).where(col(User.email) == email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists")

    user = User(
        email=email,
        display_name=req.display_name.strip(),
        password_hash=hash_password(req.password),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    token = create_access_token(user.id, user.email, user.display_name)
    return AuthTokenResponse(
        access_token=token,
        user=UserPublic.model_validate(user, from_attributes=True),
    )


@router.post("/login", response_model=AuthTokenResponse)
async def login(
    req: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> AuthTokenResponse:
    """Authenticate an existing account and issue a signed JWT."""
    email = req.email.strip().lower()
    result = await session.execute(select(User).where(col(User.email) == email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    token = create_access_token(user.id, user.email, user.display_name)
    return AuthTokenResponse(
        access_token=token,
        user=UserPublic.model_validate(user, from_attributes=True),
    )


@router.get("/me", response_model=UserPublic)
async def me(
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UserPublic:
    """Return the currently authenticated user's profile."""
    result = await session.execute(select(User).where(col(User.id) == current_user.id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account no longer exists")
    return UserPublic.model_validate(user, from_attributes=True)
