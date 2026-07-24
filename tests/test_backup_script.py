from pathlib import Path


def test_backup_script_uses_unix_line_endings() -> None:
    script = Path("backup/backup_db.sh").read_bytes()

    assert script.startswith(b"#!/bin/bash\n")
    assert b"\r\n" not in script
