import csv
import logging
import os
from pathlib import Path
from typing import Sequence

logger = logging.getLogger(__name__)

CSV_FIELDNAMES = ["cuit", "apellido", "nombre", "full_name"]


def export_to_csv(records: Sequence[dict], output_path: str | os.PathLike) -> Path:
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
