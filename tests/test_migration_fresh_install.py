from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any


class RecordingOperations:
    def __init__(self) -> None:
        self.executed: list[str] = []
        self.added_columns: list[tuple[str, str]] = []
        self.dropped_tables: list[tuple[str, dict[str, Any]]] = []

    def execute(self, statement: str) -> None:
        self.executed.append(statement)

    def add_column(self, *args: Any, **kwargs: Any) -> None:
        self.added_columns.append((args[0], args[1].name))

    def create_foreign_key(self, *args: Any, **kwargs: Any) -> None:
        pass

    def create_table(self, *args: Any, **kwargs: Any) -> None:
        pass

    def create_index(self, *args: Any, **kwargs: Any) -> None:
        pass

    def drop_table(self, table_name: str, **kwargs: Any) -> None:
        self.dropped_tables.append((table_name, kwargs))

    def get_bind(self) -> object:
        return object()


def load_migration(filename: str) -> ModuleType:
    path = Path("migrations/versions") / filename
    spec = importlib.util.spec_from_file_location("summary_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_summary_migration_tolerates_absent_legacy_objects() -> None:
    migration = load_migration("20251030_2338_619d48a9dd9c_add_summary_fields_to_conversation.py")
    operations = RecordingOperations()
    migration.op = operations

    migration.upgrade()

    cleanup_sql = "\n".join(operations.executed)
    assert "DROP INDEX IF EXISTS llama_pg_vector_store_idx_1" in cleanup_sql
    assert "DROP TABLE IF EXISTS data_llama_pg_vector_store" in cleanup_sql
    assert "DROP INDEX IF EXISTS ix_messages_log_user_created" in cleanup_sql
    assert "DROP INDEX IF EXISTS ix_messages_user_user_created" in cleanup_sql
    assert "DROP CONSTRAINT IF EXISTS users_active_persona_id_fkey" in cleanup_sql
    assert "DROP COLUMN IF EXISTS active_persona_id" in cleanup_sql


def test_multibot_migration_skips_removed_memories_table(monkeypatch: Any) -> None:
    migration = load_migration("20260102_1645_add_multibot_tables.py")
    operations = RecordingOperations()
    migration.op = operations

    class Inspector:
        @staticmethod
        def has_table(table_name: str) -> bool:
            assert table_name == "memories"
            return False

    monkeypatch.setattr(migration.sa, "inspect", lambda bind: Inspector())

    migration.upgrade()

    assert ("conversations", "bot_id") in operations.added_columns
    assert ("memories", "bot_id") not in operations.added_columns


def test_message_history_migration_skips_absent_legacy_tables(monkeypatch: Any) -> None:
    migration = load_migration("20260302_2100_b7c8d9e0f1a2_add_bot_id_to_message_history.py")
    operations = RecordingOperations()
    migration.op = operations

    class Inspector:
        @staticmethod
        def has_table(table_name: str) -> bool:
            assert table_name in {"messages_log", "messages_user"}
            return False

    monkeypatch.setattr(migration.sa, "inspect", lambda bind: Inspector())

    migration.upgrade()

    assert operations.added_columns == []


def test_drop_messages_user_is_safe_when_table_is_already_absent() -> None:
    migration = load_migration("20260610_0003_e7f8a9b0c1d2_drop_messages_user_table.py")
    operations = RecordingOperations()
    migration.op = operations

    migration.upgrade()

    assert operations.dropped_tables == [("messages_user", {"if_exists": True})]
