import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def test_build_snippets_code_contains_env_var():
    from mulchd.connect import build_connect_snippets
    s = build_connect_snippets("https://example.com", "acme", "demo", "tok-abc")
    assert "MULCHD_TOKEN_ACME_DEMO" in s["mcp_json"]
    assert "${MULCHD_TOKEN_ACME_DEMO}" in s["mcp_json"]
    assert "mulchd" in s["mcp_json"]
    assert "https://example.com/mcp" in s["mcp_json"]


def test_build_snippets_settings_local_contains_token():
    from mulchd.connect import build_connect_snippets
    s = build_connect_snippets("https://example.com", "acme", "demo", "tok-abc")
    assert "MULCHD_TOKEN_ACME_DEMO" in s["settings_local"]
    assert "tok-abc" in s["settings_local"]
    assert "enabledMcpServersJson" in s["settings_local"]


def test_build_snippets_desktop_contains_mcp_remote():
    from mulchd.connect import build_connect_snippets
    s = build_connect_snippets("https://example.com", "acme", "demo", "tok-abc")
    assert "mcp-remote" in s["desktop"]
    assert "mulchd-acme-demo" in s["desktop"]
    assert "tok-abc" in s["desktop"]
    assert "MULCHD_TOKEN_ACME_DEMO" in s["desktop"]


def test_build_snippets_hyphens_become_underscores():
    from mulchd.connect import build_connect_snippets
    s = build_connect_snippets("https://x.com", "my-org", "my-project", "t")
    assert "MULCHD_TOKEN_MY_ORG_MY_PROJECT" in s["mcp_json"]
    assert "MULCHD_TOKEN_MY_ORG_MY_PROJECT" in s["settings_local"]
    assert "MULCHD_TOKEN_MY_ORG_MY_PROJECT" in s["desktop"]
