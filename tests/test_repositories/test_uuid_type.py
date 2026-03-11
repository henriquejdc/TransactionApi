import uuid
from unittest.mock import MagicMock

from app.models.transaction import UUIDType


class TestUUIDType:
    def setup_method(self):
        self.uuid_type = UUIDType()

    @staticmethod
    def _make_dialect(name: str):
        dialect = MagicMock()
        dialect.name = name
        dialect.type_descriptor = lambda x: x
        return dialect

    def test_load_dialect_impl_postgresql(self):
        dialect = self._make_dialect("postgresql")
        result = self.uuid_type.load_dialect_impl(dialect)
        assert result is not None

    def test_load_dialect_impl_sqlite(self):
        from sqlalchemy import types

        dialect = self._make_dialect("sqlite")
        dialect.type_descriptor = lambda x: x
        result = self.uuid_type.load_dialect_impl(dialect)
        assert isinstance(result, types.String)

    def test_process_bind_param_with_uuid(self):
        uid = uuid.uuid4()
        dialect = self._make_dialect("sqlite")
        result = self.uuid_type.process_bind_param(uid, dialect)
        assert result == str(uid)

    def test_process_bind_param_with_none(self):
        dialect = self._make_dialect("sqlite")
        assert self.uuid_type.process_bind_param(None, dialect) is None

    def test_process_result_value_with_string(self):
        uid = uuid.uuid4()
        dialect = self._make_dialect("sqlite")
        result = self.uuid_type.process_result_value(str(uid), dialect)
        assert result == uid
        assert isinstance(result, uuid.UUID)

    def test_process_result_value_with_uuid_object(self):
        uid = uuid.uuid4()
        dialect = self._make_dialect("postgresql")
        result = self.uuid_type.process_result_value(uid, dialect)
        assert result == uid

    def test_process_result_value_with_none(self):
        dialect = self._make_dialect("sqlite")
        assert self.uuid_type.process_result_value(None, dialect) is None
