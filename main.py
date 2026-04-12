"""FastAPI application entry point.

Wires the authentication, categories, transactions and analytics routers
into a single ``app`` instance that can be served with uvicorn:

    uvicorn main:app --reload
"""

from fastapi import FastAPI

from auth import router as auth_router
from routers_analytics import router as analytics_router
from routers_categories import router as categories_router
from routers_transactions import router as transactions_router

app = FastAPI(title="Finance Tracker")

app.include_router(auth_router)
app.include_router(categories_router)
app.include_router(transactions_router)
app.include_router(analytics_router)
