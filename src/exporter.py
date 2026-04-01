"""
CSV exporter module.

Writes processed UserInfo dicts to a CSV file.
Supports both single-record writes and bulk appends.
"""

import csv
import logging
import os
from pathlib import Path
from typing import Sequence

logger = logging.getLogger(__name__)

CSV_FIELDNAMES = ["cuit", "apellido", "nombre", "full_name"]


def export_to_csv(records: Sequence[dict], output_path: str | os.PathLike) -> Path:
    """
    Write *records* to *output_path* as CSV.

    Creates the file (and parent directories) if they don't exist.
    Overwrites any existing file at that path.

    Returns the resolved Path of the written file.
    """
    path = Path(output_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=CSV_FIELDNAMES,
            extrasaction="ignore",
            quoting=csv.QUOTE_ALL,
        )
        writer.writeheader()
        writer.writerows(records)

    logger.info("Exported %d record(s) to %s", len(records), path)
    return path


def append_to_csv(record: dict, output_path: str | os.PathLike) -> Path:
    """
    Append a single *record* to *output_path*.

    Creates the file with a header row if it doesn't exist yet;
    otherwise appends without re-writing the header.
    """
    path = Path(output_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    write_header = not path.exists() or path.stat().st_size == 0

    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=CSV_FIELDNAMES,
            extrasaction="ignore",
            quoting=csv.QUOTE_ALL,
        )
        if write_header:
            writer.writeheader()
        writer.writerow(record)

    logger.info("Appended record to %s", path)
    return path
