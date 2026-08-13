from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlmodel import Session

from app.core.database import get_session
from app.schemas.word_collection import (
    WordCollectionCreate,
    WordCollectionDeleteResponse,
    WordCollectionRead,
)
from app.services.word_collection_service import (
    EmptyWordCollectionError,
    WordAlreadyCollectedError,
    collect_word,
    delete_word_collection,
    list_word_collections,
)

router = APIRouter(prefix="/api/words", tags=["words"])


@router.post("/collect", response_model=WordCollectionRead)
def collect_word_collection(
    payload: WordCollectionCreate,
    session: Session = Depends(get_session),
):
    try:
        return collect_word(session, payload)
    except WordAlreadyCollectedError:
        return JSONResponse(
            status_code=409,
            content={
                "detail": "WORD_ALREADY_COLLECTED",
                "message": "这个单词已经收藏过了",
            },
        )
    except EmptyWordCollectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/collections", response_model=list[WordCollectionRead])
def get_word_collections(
    sort: Literal[
        "collected_time_asc",
        "collected_time_desc",
        "alphabetical",
    ] = "collected_time_asc",
    language: str | None = Query(default=None),
    session: Session = Depends(get_session),
):
    try:
        return list_word_collections(session, sort=sort, language=language)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete(
    "/collections/{collection_id}",
    response_model=WordCollectionDeleteResponse,
)
def remove_word_collection(
    collection_id: int,
    session: Session = Depends(get_session),
):
    if not delete_word_collection(session, collection_id):
        raise HTTPException(status_code=404, detail="Word collection not found.")
    return WordCollectionDeleteResponse(deleted=True, id=collection_id)
