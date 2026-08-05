import logging
import re
from pathlib import Path
from typing import Any, cast

import yaml

from .config import settings
from .records import get_file_mod_time, read_domain_records

_log = logging.getLogger("mulchd")
_DOMAIN_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def validate_domain(domain: str) -> None:
    """Raise ValueError unless domain is a plain slug — callers build filesystem
    paths from this value, so anything else risks path traversal."""
    if not _DOMAIN_RE.match(domain):
        raise ValueError(f"invalid domain: {domain!r}")


def mulch_dir(org: str, project: str) -> Path:
    return settings.data_path / org / project / ".mulch"


def expertise_path(org: str, project: str, domain: str) -> Path:
    validate_domain(domain)
    return mulch_dir(org, project) / "expertise" / f"{domain}.jsonl"


def _load_domain_descriptions(m_dir: Path) -> dict[str, str]:
    """Read domain descriptions from mulch.config.yaml."""
    config_path = m_dir / "mulch.config.yaml"
    descriptions: dict[str, str] = {}
    if config_path.exists():
        try:
            data = cast("dict[str, Any]", yaml.safe_load(config_path.read_text()) or {})
            domains = cast("dict[str, Any]", data.get("domains") or {})
            for name, meta in domains.items():
                if isinstance(meta, dict):
                    descriptions[name] = cast(dict[str, Any], meta).get("description", "")
                elif isinstance(meta, str):
                    descriptions[name] = meta
        except Exception:
            _log.warning(
                "failed to parse %s — domain descriptions will be empty", config_path, exc_info=True
            )
    return descriptions


def list_domain_names(org: str, project: str) -> list[str]:
    """Domain names only, no record parsing — for callers that just need to
    validate/enumerate domains without paying for a full corpus read."""
    expertise_dir = mulch_dir(org, project) / "expertise"
    if not expertise_dir.exists():
        return []
    return sorted(p.stem for p in expertise_dir.glob("*.jsonl"))


async def list_available_domains(org: str, project: str) -> list[dict[str, Any]]:
    m_dir = mulch_dir(org, project)
    expertise_dir = m_dir / "expertise"
    descriptions = _load_domain_descriptions(m_dir)
    domain_names = list_domain_names(org, project)

    results: list[dict[str, Any]] = []
    for name in domain_names:
        path = expertise_dir / f"{name}.jsonl"
        records = await read_domain_records(path)
        mod_time = await get_file_mod_time(path)
        description = descriptions.get(name, "")
        results.append(
            {
                "name": name,
                "description": description,
                "record_count": len(records),
                "last_updated": mod_time.isoformat() if mod_time else None,
                "uri": f"mulchd://{org}/{project}/domain/{name}",
            }
        )
    return results
