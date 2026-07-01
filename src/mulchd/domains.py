from pathlib import Path

from .config import settings
from .records import get_file_mod_time, read_domain_records

STARTER_DOMAINS: dict[str, str] = {
    "infra": "AWS accounts, networking, IAM, environment boundaries",
    "data-platform": "Databricks, Snowflake, Confluent, pipeline patterns",
    "governance": "Metadata model, data contracts, ownership",
    "sources": "Per data source quirks and decisions",
    "cross-cutting": "Decisions spanning multiple domains",
}


def mulch_dir(org: str, project: str) -> Path:
    return settings.data_path / org / project / ".mulch"


def expertise_path(org: str, project: str, domain: str) -> Path:
    return mulch_dir(org, project) / "expertise" / f"{domain}.jsonl"


async def list_available_domains(org: str, project: str) -> list[dict]:
    results = []
    for name, description in STARTER_DOMAINS.items():
        path = expertise_path(org, project, name)
        records = await read_domain_records(path)
        mod_time = await get_file_mod_time(path)
        results.append(
            {
                "name": name,
                "description": description,
                "record_count": len(records),
                "last_updated": mod_time.isoformat() if mod_time else None,
            }
        )
    return results
