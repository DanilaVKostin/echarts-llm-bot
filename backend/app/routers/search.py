from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.prompts.indicator_extraction import INDICATOR_EXTRACTION_PROMPT
from app.services.indicator_search import indicator_search_service
from app.services.llm import (
    LLMModelChoice,
    llm_client,
    openrouter_key_configured,
    requires_openrouter_key,
    resolve_llm_runtime,
)

router = APIRouter(prefix="/api", tags=["search"])

_TABLE_KEYS = ["hcode", "org", "metric_type", "val_type", "date_type"]


class SmartSearchRequest(BaseModel):
    q: str
    top_k: int = 10
    llm_model: LLMModelChoice = LLMModelChoice.local_qwen25


class SmartSearchResponse(BaseModel):
    results: list[dict]
    extracted_terms: dict[str, list[str]]


@router.get("/search-indicators")
async def search_indicators(
    q: Annotated[str, Query(min_length=1)],
    top_k: Annotated[int, Query(ge=1, le=50)] = 10,
) -> list[dict]:
    return await indicator_search_service.search(q, top_k)


@router.get("/search-indicators/status")
async def indicator_search_status() -> dict:
    return indicator_search_service.get_status()


@router.post(
    "/search-indicators/smart",
    responses={
        400: {"description": "OpenRouter API key not configured"},
        502: {"description": "LLM entity extraction failed"},
    },
)
async def smart_search_indicators(body: SmartSearchRequest) -> SmartSearchResponse:
    if requires_openrouter_key(body.llm_model) and not openrouter_key_configured():
        raise HTTPException(
            status_code=400,
            detail="OpenRouter is not configured: set OPENROUTER_API_KEY in backend .env",
        )

    runtime = resolve_llm_runtime(body.llm_model)
    messages = [
        {"role": "system", "content": INDICATOR_EXTRACTION_PROMPT},
        {"role": "user", "content": body.q},
    ]

    try:
        extracted = await llm_client.call_llm_json(messages, runtime)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM extraction failed: {exc}") from exc

    terms_by_table: dict[str, list[str]] = {
        key: [str(t) for t in extracted.get(key, []) if t]
        for key in _TABLE_KEYS
    }

    results = await indicator_search_service.search_by_terms(terms_by_table, body.top_k)
    return SmartSearchResponse(results=results, extracted_terms=terms_by_table)
