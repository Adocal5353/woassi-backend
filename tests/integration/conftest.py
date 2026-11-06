from collections.abc import AsyncIterator, Iterator

import pytest
from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import LogMessageWaitStrategy

from woassi.shared.infrastructure.db.base import Base
from woassi.shared.infrastructure.db.models import metadata
from woassi.shared.infrastructure.db.session import create_engine, create_session_factory


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    with PostgresContainer("postgres:16", driver="asyncpg") as postgres:
        yield postgres.get_connection_url()


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(engine)


@pytest.fixture(scope="session")
def redis_settings() -> Iterator[RedisSettings]:
    container = (
        DockerContainer("redis:7")
        .with_exposed_ports(6379)
        .waiting_for(LogMessageWaitStrategy("Ready to accept connections"))
    )
    with container:
        yield RedisSettings(
            host=container.get_container_host_ip(),
            port=int(container.get_exposed_port(6379)),
        )


@pytest.fixture
async def pool(redis_settings: RedisSettings) -> AsyncIterator[ArqRedis]:
    pool = await create_pool(redis_settings)
    await pool.flushall()
    yield pool
    await pool.aclose()
