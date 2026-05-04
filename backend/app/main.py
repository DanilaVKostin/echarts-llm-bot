from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.routers import chart, rag, search
from app.services.database import db_service

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chart.router)
app.include_router(rag.router)
app.include_router(search.router)


class EchoRequest(BaseModel):
    message: str


class EchoResponse(BaseModel):
    reply: str


@app.post("/api/echo")
async def echo(body: EchoRequest) -> EchoResponse:
    return EchoResponse(reply=f"Echo: {body.message}")


_TEST_QUERY = """
SELECT DISTINCT hcode_name, hcode_unit_name
FROM dm_rep.dm_all_indicators_v
WHERE org = 96
  AND date_type = 2
  AND metric_type = '1'
  AND val_type = '1'
  AND nod IS NULL AND duch IS NULL AND dir IS NULL
  AND vids IS NULL AND kato IS NULL AND dep IS NULL
  AND depo IS NULL AND cargo_type IS NULL
ORDER BY hcode_name
"""


@app.get("/api/db/test-query", responses={500: {"description": "Database error"}})
async def db_test_query() -> list[dict[str, Any]]:
    try:
        return await db_service.execute_query(_TEST_QUERY)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
