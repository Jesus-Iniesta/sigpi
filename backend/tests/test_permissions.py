from app.core.permissions import Permission, RoleName, has_permission, permissions_for_role


def test_requester_can_create_requests_but_cannot_manage_sla() -> None:
    assert has_permission(RoleName.REQUESTER, Permission.REQUESTS_CREATE)
    assert not has_permission(RoleName.REQUESTER, Permission.SLA_MANAGE)


def test_service_manager_can_manage_sla() -> None:
    assert has_permission("service_manager", "sla.manage")
    assert has_permission("service_manager", Permission.REQUESTS_ASSIGN)


def test_unknown_roles_and_permissions_are_denied() -> None:
    assert permissions_for_role("unknown") == frozenset()
    assert not has_permission("unknown", Permission.REQUESTS_READ)
    assert not has_permission(RoleName.ADMINISTRATOR, "unknown.permission")
