from collections.abc import Iterable

from sqlalchemy import select

from app.core.security import hash_password
from app.models.catalog import AreaServicio, Categoria
from app.models.enums import Priority
from app.models.identity import Role, User, UserRole
from app.models.organization import OrganizationalUnit
from app.seeds.data import CATEGORY_SEEDS, PRIORITY_SEEDS, USER_SEEDS


def _session_factory():
    from app.db.session import SessionLocal

    return SessionLocal


async def run_seed_categories(area_name: str = "Soporte técnico") -> int:
    """Create the default categories under an existing service area."""
    async with _session_factory()() as session:
        area = await session.scalar(select(AreaServicio).where(AreaServicio.name == area_name))
        if area is None:
            raise ValueError(
                f"Service area {area_name!r} does not exist; create it before seeding categories."
            )

        created = 0
        for name, description in CATEGORY_SEEDS:
            category = await session.scalar(select(Categoria).where(Categoria.name == name))
            if category is None:
                session.add(
                    Categoria(area_id=area.id, name=name, description=description, is_active=True)
                )
                created += 1

        await session.commit()
        return created


async def run_seed_organizational_units() -> int:
    """Create the default organizational unit used by the local catalog."""
    async with _session_factory()() as session:
        unit = await session.scalar(
            select(OrganizationalUnit).where(OrganizationalUnit.code == "SPT")
        )
        if unit is not None:
            return 0

        session.add(
            OrganizationalUnit(
                name="Soporte técnico",
                unit_type="department",
                code="SPT",
                is_active=True,
            )
        )
        await session.commit()
        return 1


async def run_seed_area(area_name: str = "Soporte técnico") -> int:
    """Create the default service area under the matching organizational unit."""
    async with _session_factory()() as session:
        area = await session.scalar(select(AreaServicio).where(AreaServicio.name == area_name))
        if area is not None:
            return 0

        unit = await session.scalar(
            select(OrganizationalUnit).where(OrganizationalUnit.code == "SPT")
        )
        if unit is None:
            raise ValueError("Organizational unit SPT does not exist; seed units first.")

        session.add(
            AreaServicio(
                unit_id=unit.id,
                name=area_name,
                description="Área de soporte técnico para el personal",
                is_active=True,
            )
        )
        await session.commit()
        return 1


async def run_seed_priorities() -> tuple[Priority, ...]:
    """Return the supported priorities; priorities are persisted as an enum value."""
    return PRIORITY_SEEDS


async def run_seed_users() -> int:
    """Create default user accounts for entering the system.

    Idempotent: skips users whose institutional_id already exists.
    Each seed user is assigned exactly one role via UserRole.
    """
    async with _session_factory()() as session:
        created = 0
        for data in USER_SEEDS:
            existing = await session.scalar(
                select(User).where(User.institutional_id == data["institutional_id"])
            )
            if existing is not None:
                continue

            user = User(
                institutional_id=data["institutional_id"],
                full_name=data["full_name"],
                email=data["email"],
                password_hash=hash_password(data["password"]),
                user_type=data["user_type"],
                support_level=data["support_level"],
                is_active=True,
            )
            session.add(user)
            await session.flush()

            role = await session.scalar(
                select(Role).where(Role.name == data["role"])
            )
            if role is None:
                raise ValueError(
                    f"Role {data['role']!r} does not exist; seed identity roles first."
                )

            session.add(
                UserRole(user_id=user.id, role_id=role.id)
            )
            created += 1

        await session.commit()
        return created


async def run_all(area_name: str = "Soporte técnico") -> dict[str, int]:
    units = await run_seed_organizational_units()
    areas = await run_seed_area(area_name)
    categories = await run_seed_categories(area_name)
    priorities = await run_seed_priorities()
    users = await run_seed_users()
    return {
        "organizational_units": units,
        "areas": areas,
        "categories": categories,
        "priorities": len(priorities),
        "users": users,
    }


def supported_priorities(values: Iterable[Priority] = PRIORITY_SEEDS) -> tuple[str, ...]:
    return tuple(priority.value for priority in values)
