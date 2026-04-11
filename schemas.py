from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# --- Enums ---

class TransactionType(str, Enum):
    income = "income"
    expense = "expense"


# --- User ---

class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8)


class UserUpdate(BaseModel):
    username: str | None = Field(None, min_length=1, max_length=50)
    email: EmailStr | None = None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    created_at: datetime


# --- Category ---

class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class CategoryUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    user_id: int


# --- Transaction ---

class TransactionCreate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    description: str | None = Field(None, max_length=255)
    type: TransactionType
    category_id: int


class TransactionUpdate(BaseModel):
    amount: Decimal | None = Field(None, gt=0, max_digits=10, decimal_places=2)
    description: str | None = Field(None, max_length=255)
    type: TransactionType | None = None
    category_id: int | None = None


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    amount: Decimal
    description: str | None
    type: TransactionType
    created_at: datetime
    user_id: int
    category_id: int
