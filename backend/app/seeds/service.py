from collections.abc import Iterable

from sqlalchemy import select

from app.models.catalog import AreaServicio, Categoria
from app.models.enums import Priority
from app.seeds.data import CATEGORY_SEEDS, PRIORITY_SEEDS


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


async def run_seed_priorities() -> tuple[Priority, ...]:
    """Return the supported priorities; priorities are persisted as an enum value."""
    return PRIORITY_SEEDS


async def run_all(area_name: str = "Soporte técnico") -> dict[str, int]:
    categories = await run_seed_categories(area_name)
    priorities = await run_seed_priorities()
    return {"categories": categories, "priorities": len(priorities)}


def supported_priorities(values: Iterable[Priority] = PRIORITY_SEEDS) -> tuple[str, ...]:
    return tuple(priority.value for priority in values)
