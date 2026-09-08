from sqlalchemy import text

from app.core.db import BUSY_TIMEOUT_MS, create_engine, create_session_factory, session_scope


async def test_pragmas_are_applied(tmp_path):
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'nested' / 'test.sqlite3'}")
    try:
        async with engine.connect() as conn:
            journal = (await conn.execute(text("PRAGMA journal_mode"))).scalar_one()
            foreign_keys = (await conn.execute(text("PRAGMA foreign_keys"))).scalar_one()
            busy_timeout = (await conn.execute(text("PRAGMA busy_timeout"))).scalar_one()

        assert str(journal).lower() == "wal"
        assert int(foreign_keys) == 1
        assert int(busy_timeout) == BUSY_TIMEOUT_MS
    finally:
        await engine.dispose()


async def test_session_scope_rolls_back_on_error(tmp_path):
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.sqlite3'}")
    factory = create_session_factory(engine)
    try:
        async with session_scope(factory) as session:
            await session.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY)"))

        try:
            async with session_scope(factory) as session:
                await session.execute(text("INSERT INTO t (id) VALUES (1)"))
                raise RuntimeError("boom")
        except RuntimeError:
            pass

        async with session_scope(factory) as session:
            count = (await session.execute(text("SELECT COUNT(*) FROM t"))).scalar_one()
        assert count == 0
    finally:
        await engine.dispose()
