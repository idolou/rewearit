"""API v1 routers."""
from fastapi import APIRouter

from app.api.v1.items import router as items_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(items_router)
