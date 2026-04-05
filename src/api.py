import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from src.exporter import append_to_csv
from src.processor import process
from src.scraper import ARCAScraper

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "output"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("ARCA API ready")
    yield


app = FastAPI(
    title="ARCA Scraper API",
    version="2.0.0",
    description="Automated ARCA/AFIP portal scraper – operates on your own authenticated data.",
    lifespan=lifespan,
)


class ScrapeRequest(BaseModel):
    cuit: Annotated[str, Field(examples=["20123456789"])]
    password: Annotated[str, Field(min_length=1)]
    headless: bool = True

    @field_validator("cuit")
    @classmethod
    def normalise_cuit(cls, v: str) -> str:
        return v.replace("-", "").strip()


class UserInfoResponse(BaseModel):
    cuit: str
    nombre: str
    apellido: str
    full_name: str


class ScrapeResponse(BaseModel):
    status: str
    data: UserInfoResponse | None = None
    error: str | None = None


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok"}


@app.post(
    "/scrape",
    response_model=ScrapeResponse,
    status_code=status.HTTP_200_OK,
    tags=["scraping"],
    summary="Scrape a single CUIT",
)
async def scrape_single(req: ScrapeRequest):
    csv_path = OUTPUT_DIR / f"{uuid.uuid4().hex}.csv"

    try:
        async with ARCAScraper(
            cuit=req.cuit,
            password=req.password,
            headless=req.headless,
        ) as scraper:
            user_info = await scraper.fetch_user_info()

        record = process(user_info)
        append_to_csv(record, csv_path)
    except Exception as exc:
        logger.error("Scrape failed for CUIT %s: %s", req.cuit, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return ScrapeResponse(
        status="completed",
        data=UserInfoResponse(**record),
    )
