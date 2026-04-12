"""Pydantic schemas for request validation and response serialization.

Defines create/update/response DTOs for users, categories and transactions,
along with the ``TransactionType`` enum shared across endpoints.
"""

# pylint: disable=cyclic-import
# The database <-> models cycle is structural to SQLAlchemy's declarative
# pattern and is resolved at runtime via a deferred import in database.init_db.

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# --- Enums ---

class TransactionType(str, Enum):
    """Allowed transaction types: income or expense."""

    # pylint: disable=invalid-name
    # Enum members mirror the literal string values stored in the database.
    income = "income"
    expense = "expense"


# --- User ---

class UserCreate(BaseModel):
    """Payload for registering a new user."""

    username: str = Field(min_length=1, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8)


class UserUpdate(BaseModel):
    """Payload for partially updating a user profile."""

    username: str | None = Field(None, min_length=1, max_length=50)
    email: EmailStr | None = None


class UserResponse(BaseModel):
    """Public user representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    created_at: datetime


# --- Category ---

class CategoryCreate(BaseModel):
    """Payload for creating a new category."""

    name: str = Field(min_length=1, max_length=100)


class CategoryUpdate(BaseModel):
    """Payload for partially updating a category."""

    name: str | None = Field(None, min_length=1, max_length=100)


class CategoryResponse(BaseModel):
    """Category representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    user_id: int


# --- Transaction ---

class TransactionCreate(BaseModel):
    """Payload for creating a new transaction."""

    amount: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    description: str | None = Field(None, max_length=255)
    type: TransactionType
    category_id: int


class TransactionUpdate(BaseModel):
    """Payload for partially updating a transaction."""

    amount: Decimal | None = Field(None, gt=0, max_digits=10, decimal_places=2)
    description: str | None = Field(None, max_length=255)
    type: TransactionType | None = None
    category_id: int | None = None


class TransactionResponse(BaseModel):
    """Transaction representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    amount: Decimal
    description: str | None
    type: TransactionType
    created_at: datetime
    user_id: int
    category_id: int
