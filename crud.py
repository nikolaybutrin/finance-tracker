from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Category, Transaction
from schemas import (
    CategoryCreate,
    CategoryUpdate,
    TransactionCreate,
    TransactionUpdate,
)


# --- Category CRUD ---


def create_category(db: Session, user_id: int, data: CategoryCreate) -> Category:
    category = Category(name=data.name, user_id=user_id)
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


def get_categories(db: Session, user_id: int) -> list[Category]:
    stmt = select(Category).where(Category.user_id == user_id)
    return list(db.scalars(stmt).all())


def get_category(db: Session, category_id: int, user_id: int) -> Category | None:
    stmt = select(Category).where(
        Category.id == category_id, Category.user_id == user_id
    )
    return db.scalars(stmt).first()


def update_category(
    db: Session, category_id: int, user_id: int, data: CategoryUpdate
) -> Category | None:
    category = get_category(db, category_id, user_id)
    if category is None:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(category, field, value)
    db.commit()
    db.refresh(category)
    return category


def delete_category(db: Session, category_id: int, user_id: int) -> bool:
    category = get_category(db, category_id, user_id)
    if category is None:
        return False
    db.delete(category)
    db.commit()
    return True


# --- Transaction CRUD ---


def create_transaction(
    db: Session, user_id: int, data: TransactionCreate
) -> Transaction:
    transaction = Transaction(
        amount=data.amount,
        description=data.description,
        type=data.type.value,
        user_id=user_id,
        category_id=data.category_id,
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


def get_transactions(db: Session, user_id: int) -> list[Transaction]:
    stmt = select(Transaction).where(Transaction.user_id == user_id)
    return list(db.scalars(stmt).all())


def get_transaction(
    db: Session, transaction_id: int, user_id: int
) -> Transaction | None:
    stmt = select(Transaction).where(
        Transaction.id == transaction_id, Transaction.user_id == user_id
    )
    return db.scalars(stmt).first()


def update_transaction(
    db: Session, transaction_id: int, user_id: int, data: TransactionUpdate
) -> Transaction | None:
    transaction = get_transaction(db, transaction_id, user_id)
    if transaction is None:
        return None
    updates = data.model_dump(exclude_unset=True)
    if "type" in updates and updates["type"] is not None:
        updates["type"] = updates["type"].value
    for field, value in updates.items():
        setattr(transaction, field, value)
    db.commit()
    db.refresh(transaction)
    return transaction


def delete_transaction(db: Session, transaction_id: int, user_id: int) -> bool:
    transaction = get_transaction(db, transaction_id, user_id)
    if transaction is None:
        return False
    db.delete(transaction)
    db.commit()
    return True
