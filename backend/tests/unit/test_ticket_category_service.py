"""Unit tests for TicketCategoryService query behavior."""

from unittest.mock import AsyncMock, MagicMock

from app.services.ticket_category_service import TicketCategoryService


class TestListByLevel:
    async def test_level2_without_parent_omits_parent_filter(self):
        """Omitted parent_id must not trap to parent_id IS NULL orphans."""
        db = AsyncMock()
        captured: list = []

        async def capture_execute(stmt):
            captured.append(stmt)
            result = MagicMock()
            result.scalars.return_value.all.return_value = []
            return result

        db.execute = capture_execute
        svc = TicketCategoryService(db)
        await svc.list_by_level(2, parent_id=None)

        compiled = str(captured[0].compile(compile_kwargs={"literal_binds": True}))
        assert "parent_id IS NULL" not in compiled.upper()
        assert "level" in compiled.lower()
