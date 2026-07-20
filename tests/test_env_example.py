import re
from pathlib import Path

from settings import AppSettings


def test_env_example_covers_every_app_setting_without_stale_keys():
    keys = {
        line.split("=", 1)[0]
        for line in Path("env_example.txt").read_text(encoding="utf-8").splitlines()
        if re.match(r"^[A-Z][A-Z0-9_]*=", line)
    }
    assert keys == set(AppSettings.model_fields)
