from fastapi import APIRouter

from app.api.v1.routes.transactions import router as transactions_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(transactions_router)
