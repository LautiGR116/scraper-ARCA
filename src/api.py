"""
FastAPI REST API.

Exposes the ARCA scraper as an HTTP service.

Endpoints
---------
POST /scrape          – scrape a single CUIT and return JSON
POST /scrape/batch    – scrape multiple CUITs concurrently
GET  /download/{job}  – download the generated CSV for a job
GET  /health          – liveness check
"""

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from src.exporter import append_to_csv
from src.processor import process
from src.scraper import ARCAScraper

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "output"))
MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT_SCRAPERS", "5"))

# In-memory job registry  {job_id: {"status": ..., "records": [...], "path": ...}}
_jobs: dict[str, dict] = {}
_semaphore: asyncio.Semaphore | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _semaphore
    _semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("ARCA API ready (max_concurrent=%d)", MAX_CONCURRENT)
    yield


app = FastAPI(
    title="ARCA Scraper API",
    version="1.0.0",
    description="Automated ARCA/AFIP portal scraper – operates on your own authenticated data.",
    lifespan=lifespan,
)


# ── Request / Response models ─────────────────────────────────────────────────
class ScrapeRequest(BaseModel):
    cuit: Annotated[str, Field(examples=["20123456789"])]
    password: Annotated[str, Field(min_length=1)]
    headless: bool = True

    @field_validator("cuit")
    @classmethod
    def normalise_cuit(cls, v: str) -> str:
        return v.replace("-", "").strip()


class BatchScrapeRequest(BaseModel):
    credentials: list[ScrapeRequest] = Field(min_length=1, max_length=50)


class UserInfoResponse(BaseModel):
    cuit: str
    nombre: str
    apellido: str
    full_name: str


class ScrapeResponse(BaseModel):
    job_id: str
    status: str
    data: UserInfoResponse | None = None
    csv_path: str | None = None
    error: str | None = None


class BatchScrapeResponse(BaseModel):
    job_id: str
    status: str
    total: int
    completed: int = 0
    failed: int = 0


# ── Helpers ───────────────────────────────────────────────────────────────────
async def _scrape_one(req: ScrapeRequest, job_id: str) -> dict:
    assert _semaphore is not None
    async with _semaphore:
        async with ARCAScraper(
            cuit=req.cuit,
            password=req.password,
            headless=req.headless,
        ) as scraper:
            user_info = await scraper.fetch_user_info()

    record = process(user_info)
    csv_path = OUTPUT_DIR / f"{job_id}.csv"
    append_to_csv(record, csv_path)
    return record


# ── Endpoints ─────────────────────────────────────────────────────────────────
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
    """
    Login to ARCA with the provided credentials (your own CUIT and password),
    extract your name/surname, return JSON and save to CSV.
    """
    job_id = uuid.uuid4().hex

    try:
        record = await _scrape_one(req, job_id)
    except Exception as exc:
        logger.error("Scrape failed for CUIT %s: %s", req.cuit, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return ScrapeResponse(
        job_id=job_id,
        status="completed",
        data=UserInfoResponse(**record),
        csv_path=str(OUTPUT_DIR / f"{job_id}.csv"),
    )


@app.post(
    "/scrape/batch",
    response_model=BatchScrapeResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["scraping"],
    summary="Scrape multiple CUITs (async, background)",
)
async def scrape_batch(req: BatchScrapeRequest, background_tasks: BackgroundTasks):
    """
    Enqueue a batch of scrape jobs.  Returns a job_id immediately;
    use GET /download/{job_id} once the job is complete.
    """
    job_id = uuid.uuid4().hex
    _jobs[job_id] = {
        "status": "running",
        "total": len(req.credentials),
        "completed": 0,
        "failed": 0,
        "records": [],
    }
    background_tasks.add_task(_run_batch, job_id, req.credentials)
    return BatchScrapeResponse(
        job_id=job_id,
        status="running",
        total=len(req.credentials),
    )


@app.get(
    "/scrape/batch/{job_id}",
    response_model=BatchScrapeResponse,
    tags=["scraping"],
    summary="Check batch job status",
)
async def batch_status(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = _jobs[job_id]
    return BatchScrapeResponse(
        job_id=job_id,
        status=job["status"],
        total=job["total"],
        completed=job["completed"],
        failed=job["failed"],
    )


@app.get(
    "/download/{job_id}",
    tags=["export"],
    summary="Download the CSV for a completed job",
)
async def download_csv(job_id: str):
    csv_path = OUTPUT_DIR / f"{job_id}.csv"
    if not csv_path.exists():
        raise HTTPException(status_code=404, detail="CSV not found for this job")
    return FileResponse(
        path=str(csv_path),
        media_type="text/csv",
        filename=f"arca_{job_id}.csv",
    )


# ── Background task ───────────────────────────────────────────────────────────
async def _run_batch(job_id: str, credentials: list[ScrapeRequest]):
    csv_path = OUTPUT_DIR / f"{job_id}.csv"
    tasks = [_scrape_one(cred, job_id) for cred in credentials]

    for coro in asyncio.as_completed(tasks):
        try:
            record = await coro
            _jobs[job_id]["records"].append(record)
            _jobs[job_id]["completed"] += 1
        except Exception as exc:
            logger.error("Batch item failed: %s", exc)
            _jobs[job_id]["failed"] += 1

    _jobs[job_id]["status"] = "completed"
    logger.info(
        "Batch %s done: %d completed, %d failed",
        job_id,
        _jobs[job_id]["completed"],
        _jobs[job_id]["failed"],
    )
