import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONFIG_PATH = Path.home() / '.config' / 'opencode-sess-sync' / 'config.json'


@dataclass
class Config:
    local_url: str
    hub_url: str
    local_token: str | None
    hub_token: str | None
    state_path: Path
    directories: dict[str, str]


def load_config(path: str) -> Config:
    path = Path(path).expanduser()
    data = json.loads(path.read_text())
    return Config(
        local_url=data['local']['url'],
        hub_url=data['hub']['url'],
        local_token=data['local'].get('token'),
        hub_token=data['hub'].get('token'),
        state_path=Path(data.get('state', path.parent / 'state.json')).expanduser(),
        directories=data.get('directories', {}),
    )
