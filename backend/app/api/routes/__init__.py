from fastapi import APIRouter

from . import documents, evaluation, query

router = APIRouter()
router.include_router(documents.router)
router.include_router(query.router)
router.include_router(evaluation.router)

__all__ = ["router"]
