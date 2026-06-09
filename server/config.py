from __future__ import annotations
import tomllib
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class Config:
    owner_name: str
    owner_identities: list[str]
    journal_path: Path
    repo_roots: list[Path]
    dev_domains: list[str]

def load_config(path: Path) -> Config:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Copy config.example.toml to config.toml and fill it in."
        )
    data = tomllib.loads(path.read_text())
    base = path.parent
    jp = Path(data["journal_path"]).expanduser()
    if not jp.is_absolute():
        jp = base / jp
    return Config(
        owner_name=data["owner_name"],
        owner_identities=list(data["owner_identities"]),
        journal_path=jp,
        repo_roots=[Path(p).expanduser() for p in data["repo_roots"]],
        dev_domains=list(data["dev_domains"]),
    )
