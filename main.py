"""
CLI entry point.

Usage
-----
  # Scrape a single account and write to output/result.csv
  python main.py --cuit 20123456789 --password s3cr3t

  # Custom output path
  python main.py --cuit 20123456789 --password s3cr3t --output data/me.csv

  # Show the browser window (non-headless)
  python main.py --cuit 20123456789 --password s3cr3t --no-headless

  # Start the API server
  python main.py --serve
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("arca")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="ARCA scraper – fetch your own name/surname from the ARCA portal."
    )
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--serve", action="store_true", help="Start the FastAPI server")
    group.add_argument("--cuit", metavar="CUIT", help="Your CUIT/CUIL (11 digits)")

    p.add_argument("--password", metavar="PWD", help="Your ARCA / Clave Fiscal password")
    p.add_argument(
        "--output",
        metavar="PATH",
        default="output/result.csv",
        help="Output CSV path (default: output/result.csv)",
    )
    p.add_argument(
        "--no-headless",
        dest="headless",
        action="store_false",
        default=True,
        help="Show the browser window",
    )
    p.add_argument("--retries", type=int, default=3, help="Max login retries (default: 3)")
    p.add_argument("--debug", action="store_true", help="Save screenshot + frame HTML to debug/")
    p.add_argument(
        "--host", default="0.0.0.0", help="API server host (default: 0.0.0.0)"
    )
    p.add_argument("--port", type=int, default=8000, help="API server port (default: 8000)")
    return p


async def _run_scrape(args: argparse.Namespace) -> None:
    from src.exporter import export_to_csv
    from src.processor import process
    from src.scraper import ARCAScraper

    password = args.password or os.getenv("ARCA_PASSWORD")
    if not password:
        logger.error("Password required: use --password or set ARCA_PASSWORD env var")
        sys.exit(1)

    logger.info("Starting scrape for CUIT %s", args.cuit)

    async with ARCAScraper(
        cuit=args.cuit,
        password=password,
        headless=args.headless,
        max_retries=args.retries,
        debug=getattr(args, "debug", False),
    ) as scraper:
        user_info = await scraper.fetch_user_info()

    record = process(user_info)
    output_path = export_to_csv([record], args.output)

    logger.info("Done!")
    logger.info("  Nombre:   %s", record["nombre"])
    logger.info("  Apellido: %s", record["apellido"])
    logger.info("  CUIT:     %s", record["cuit"])
    logger.info("  CSV:      %s", output_path)


def _run_server(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run(
        "src.api:app",
        host=args.host,
        port=args.port,
        reload=False,
        log_level="info",
    )


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.serve:
        _run_server(args)
    else:
        asyncio.run(_run_scrape(args))


if __name__ == "__main__":
    main()
