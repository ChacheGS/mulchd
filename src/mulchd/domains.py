from pathlib import Path

import yaml

from .config import settings
from .records import get_file_mod_time, read_domain_records

def mulch_dir(org: str, project: str) -> Path:
    return settings.data_path / org / project / ".mulch"


def expertise_path(org: str, project: str, domain: str) -> Path:
    return mulch_dir(org, project) / "expertise" / f"{domain}.jsonl"


def _load_domain_descriptions(m_dir: Path) -> dict[str, str]:
    """Read domain descriptions from mulch.config.yaml."""
    config_path = m_dir / "mulch.config.yaml"
    descriptions: dict[str, str] = {}
    if config_path.exists():
        try:
            data = yaml.safe_load(config_path.read_text()) or {}
            for name, meta in (data.get("domains") or {}).items():
                if isinstance(meta, dict):
                    descriptions[name] = meta.get("description", "")
                elif isinstance(meta, str):
                    descriptions[name] = meta
        except Exception:
            pass
    return descriptions


async def list_available_domains(org: str, project: str) -> list[dict]:
    m_dir = mulch_dir(org, project)
    expertise_dir = m_dir / "expertise"
    descriptions = _load_domain_descriptions(m_dir)

    domain_names: list[str] = []
    if expertise_dir.exists():
        domain_names = sorted(p.stem for p in expertise_dir.glob("*.jsonl"))

    results = []
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
            }
        )
    return results
