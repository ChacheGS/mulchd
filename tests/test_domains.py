import pytest

from mulchd.domains import expertise_path


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
