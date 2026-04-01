"""
Processor module.

Validates and normalises raw UserInfo objects before export.
Keeping this layer separate allows adding enrichment logic (e.g. CUIT
checksum validation, name normalisation) without touching the scraper.
"""

import logging
import re
from dataclasses import asdict

from src.scraper import UserInfo

logger = logging.getLogger(__name__)

_CUIT_RE = re.compile(r"^\d{11}$")


def validate_cuit(cuit: str) -> bool:
    """Verify CUIT/CUIL format and check digit."""
    cuit = cuit.replace("-", "").strip()
    if not _CUIT_RE.match(cuit):
        return False

    multipliers = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    total = sum(int(d) * m for d, m in zip(cuit[:10], multipliers))
    remainder = total % 11
    check = 0 if remainder == 0 else (11 - remainder if remainder != 1 else 9)
    return check == int(cuit[10])


def process(user_info: UserInfo) -> dict:
    """
    Validate and normalise a UserInfo instance.

    Returns a plain dict ready for CSV export.
    Raises ValueError if validation fails.
    """
    if not validate_cuit(user_info.cuit):
        raise ValueError(f"Invalid CUIT: {user_info.cuit}")

    if not user_info.nombre or not user_info.apellido:
        raise ValueError(
            f"Incomplete name data for CUIT {user_info.cuit}: "
            f"nombre='{user_info.nombre}', apellido='{user_info.apellido}'"
        )

    normalised = UserInfo(
        cuit=_format_cuit(user_info.cuit),
        nombre=user_info.nombre.strip().title(),
        apellido=user_info.apellido.strip().title(),
        full_name=f"{user_info.apellido.strip().title()}, {user_info.nombre.strip().title()}",
    )

    logger.info("Processed record: %s", normalised.full_name)
    return asdict(normalised)


def _format_cuit(raw: str) -> str:
    """Format raw 11-digit CUIT as XX-XXXXXXXX-X."""
    digits = raw.replace("-", "").strip()
    return f"{digits[:2]}-{digits[2:10]}-{digits[10]}"
