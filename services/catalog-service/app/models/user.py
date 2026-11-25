"""User entity and authentication request/response schemas."""
import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field
from sqlmodel import Field as SQLField
from sqlmodel import SQLModel


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: uuid.UUID = SQLField(default_factory=uuid.uuid4, primary_key=True, index=True)
    email: str = SQLField(max_length=255, unique=True, index=True)
    display_name: str = SQLField(max_length=100)
    password_hash: str = SQLField(max_length=255)
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(UTC))


class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=100)


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class UserPublic(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    created_at: datetime


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic
