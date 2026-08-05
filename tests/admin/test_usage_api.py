async def test_usage_data_includes_breakdowns(admin_client):
    """usage_data() returns by_tool, by_user, and by_protocol_version breakdowns
    reflecting the ToolCall rows for the project."""
    from unittest.mock import AsyncMock, patch

    from mulchd.auth import create_user
    from mulchd.models import Organization, Project, ToolCall

    org = await Organization.create(slug="acme", display_name="Acme Corp")
    project = await Project.create(slug="infra", display_name="Infrastructure", org=org)
    author, _ = await create_user("alice", "Alice")

    await ToolCall.create(
        project=project,
        author=author,
        tool="search_records",
        client="claude-code",
        protocol_version="2025-11-25",
    )
    await ToolCall.create(
        project=project,
        author=author,
        tool="write_pattern",
        client="claude-code",
        protocol_version="2026-06-18",
    )

    # chart_rows uses a raw date_trunc(...) query, Postgres-only syntax that
    # doesn't run against the test suite's sqlite backend — stub just that,
    # the by_tool/by_user/by_protocol_version breakdowns below run for real.
    with patch("mulchd.admin.usage_api.connections") as mock_connections:
        mock_connections.get.return_value.execute_query_dict = AsyncMock(return_value=[])
        resp = await admin_client.get(f"/admin/api/usage/{org.slug}/{project.slug}")
    assert resp.status_code == 200
    data = resp.json()

    assert "by_protocol_version" in data
    versions = dict(data["by_protocol_version"])
    assert versions == {"2025-11-25": 1, "2026-06-18": 1}

    assert dict(data["by_tool"]) == {"search_records": 1, "write_pattern": 1}
    assert dict(data["by_user"]) == {"alice": 2}
