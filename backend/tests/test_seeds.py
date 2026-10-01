import uuid

import pytest

from app.models.catalog import AreaServicio
from app.models.enums import Priority
from app.seeds import service


class FakeSession:
    def __init__(self, area=None, categories=None):
        self.area = area
        self.categories = {category.name: category for category in (categories or [])}
        self.committed = False

    async def scalar(self, query):
        entity = query.column_descriptions[0]["entity"]
        if entity is AreaServicio:
            return self.area
        name = query.whereclause.right.value
        return self.categories.get(name)

    def add(self, entity):
        self.categories[entity.name] = entity

    async def commit(self):
        self.committed = True


class FakeSessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_):
        return False


@pytest.mark.asyncio
async def test_seed_categories_is_idempotent(monkeypatch):
    area = AreaServicio(id=uuid.uuid4(), unit_id=uuid.uuid4(), name="Soporte técnico")
    session = FakeSession(area)
    monkeypatch.setattr(service, "_session_factory", lambda: lambda: FakeSessionContext(session))

    assert await service.run_seed_categories() == 4
    assert await service.run_seed_categories() == 0
    assert session.committed is True


@pytest.mark.asyncio
async def test_seed_categories_requires_area(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr(service, "_session_factory", lambda: lambda: FakeSessionContext(session))

    with pytest.raises(ValueError, match="does not exist"):
        await service.run_seed_categories()


@pytest.mark.asyncio
async def test_seed_priorities_returns_enum_catalog():
    assert await service.run_seed_priorities() == tuple(Priority)