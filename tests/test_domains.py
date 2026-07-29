import pytest

from mulchd.domains import _load_domain_descriptions, expertise_path, list_domain_names


def test_load_domain_descriptions_logs_on_malformed_yaml(tmp_path, caplog):
    """A malformed mulch.config.yaml must be visible in logs, not silently
    treated the same as 'no descriptions configured'."""
    (tmp_path / "mulch.config.yaml").write_text("not: valid: yaml: [")

    with caplog.at_level("WARNING"):
        descriptions = _load_domain_descriptions(tmp_path)

    assert descriptions == {}
    assert "mulch.config.yaml" in caplog.text


def test_list_domain_names_returns_stems_without_reading_content(tmp_path, monkeypatch):
    from mulchd.config import settings

    monkeypatch.setattr(settings, "data_path", tmp_path)
    expertise_dir = tmp_path / "acme" / "infra" / ".mulch" / "expertise"
    expertise_dir.mkdir(parents=True)
    (expertise_dir / "infra.jsonl").write_text("not valid json\n")
    (expertise_dir / "policies.jsonl").write_text("{}\n")

    assert list_domain_names("acme", "infra") == ["infra", "policies"]


def test_list_domain_names_missing_project_returns_empty(tmp_path, monkeypatch):
    from mulchd.config import settings

    monkeypatch.setattr(settings, "data_path", tmp_path)
    assert list_domain_names("acme", "nope") == []


def test_expertise_path_accepts_normal_slug():
    path = expertise_path("acme", "infra", "infra-domain_1")
    assert path.name == "infra-domain_1.jsonl"


@pytest.mark.parametrize(
    "domain",
    [
        "../../other-org/other-project/.mulch/expertise/secrets",
        "..",
        "a/b",
        "a b",
        "",
    ],
)
def test_expertise_path_rejects_traversal_and_invalid_domains(domain):
    with pytest.raises(ValueError, match="invalid domain"):
        expertise_path("acme", "infra", domain)
