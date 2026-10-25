import json
from pathlib import Path


def load_state(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text())['sessions']


def save_state(path: Path, sessions: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'sessions': sessions}, indent=1))
