from fastapi import APIRouter, Depends

from app.api.deps.auth import require_auth
from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.transactions import router as transactions_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(transactions_router, dependencies=[Depends(require_auth)])
