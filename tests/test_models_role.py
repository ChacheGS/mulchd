import pytest

pytestmark = pytest.mark.no_db


def test_min_role_picks_more_restrictive():
    from mulchd.models import Role, min_role

    assert min_role(Role.ADMIN, Role.WRITER) == Role.WRITER
    assert min_role(Role.WRITER, Role.ADMIN) == Role.WRITER
    assert min_role(Role.READER, Role.ADMIN) == Role.READER
    assert min_role(Role.ADMIN, Role.ADMIN) == Role.ADMIN


def test_roles_up_to_orders_most_to_least_privileged():
    from mulchd.models import Role, roles_up_to

    assert roles_up_to(Role.ADMIN) == [Role.ADMIN, Role.WRITER, Role.READER]
    assert roles_up_to(Role.WRITER) == [Role.WRITER, Role.READER]
    assert roles_up_to(Role.READER) == [Role.READER]
