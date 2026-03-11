from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.asyncio


class TestGetDb:
    async def test_get_db_commits_on_success(self):
        """get_db yields a session and commits when no exception is raised."""
        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.db.session.AsyncSessionLocal", return_value=mock_cm):
            from app.db.session import get_db

            gen = get_db()
            session = await gen.__anext__()
            assert session is mock_session
            try:
                await gen.__anext__()
            except StopAsyncIteration:
                pass

        mock_session.commit.assert_awaited_once()
        mock_session.close.assert_awaited_once()

    async def test_get_db_rolls_back_on_exception(self):
        """get_db rolls back and re-raises when an exception is thrown into it."""
        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.db.session.AsyncSessionLocal", return_value=mock_cm):
            from app.db.session import get_db

            gen = get_db()
            await gen.__anext__()  # get the session
            with pytest.raises(RuntimeError, match="test rollback"):
                await gen.athrow(RuntimeError("test rollback"))

        mock_session.rollback.assert_awaited_once()
        mock_session.close.assert_awaited_once()
