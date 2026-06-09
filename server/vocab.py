from __future__ import annotations
import tomllib
from dataclasses import dataclass
from pathlib import Path

TAGGING_GUIDANCE = """Tag the OWNER's contribution, not the AI's.
Provide >=1 domain and >=1 activity, using the fewest true tags (usually 1-2 per axis).
Use tags ONLY from list_tags; read a tag's gloss if unsure.
Never invent a synonym. If nothing fits, propose one via propose_tag (owner confirms).
Do NOT assign 'collaboration' — the server applies it from repo ownership."""

@dataclass
class Vocab:
    domains: dict[str, str]
    activities: dict[str, str]

    def validate(self, domains: list[str], activities: list[str]) -> list[str]:
        unknown = [f"domain:{d}" for d in domains if d not in self.domains]
        unknown += [f"activity:{a}" for a in activities if a not in self.activities]
        return unknown

def load_vocab(seed_path: Path, local_path: Path | None) -> Vocab:
    seed = tomllib.loads(Path(seed_path).read_text())
    domains = dict(seed.get("domains", {}))
    activities = dict(seed.get("activities", {}))
    if local_path and Path(local_path).exists():
        local = tomllib.loads(Path(local_path).read_text())
        domains.update(local.get("domains", {}))
        activities.update(local.get("activities", {}))
    return Vocab(domains=domains, activities=activities)

def add_local_tag(local_path: Path, axis: str, name: str, gloss: str) -> None:
    if axis not in ("domain", "activity"):
        raise ValueError("axis must be 'domain' or 'activity'")
    section = "domains" if axis == "domain" else "activities"
    path = Path(local_path)
    data = tomllib.loads(path.read_text()) if path.exists() else {}
    data.setdefault(section, {})[name] = gloss
    lines = []
    for sec in ("domains", "activities"):
        if data.get(sec):
            lines.append(f"[{sec}]")
            for k, val in data[sec].items():
                escaped = val.replace('"', '\\"')
                lines.append(f'{k} = "{escaped}"')
            lines.append("")
    path.write_text("\n".join(lines))
