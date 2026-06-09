#!/usr/bin/env python3
"""CLI privacy scanner. Usage: scan.py FILE [FILE...]  (reads stdin if no files).
Exit 1 if any finding. Used by the pre-commit hook."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.privacy import scan  # noqa: E402

def _allowlists():
    cfg = Path(__file__).resolve().parents[1] / "config.toml"
    if cfg.exists():
        import tomllib
        d = tomllib.loads(cfg.read_text())
        return list(d.get("owner_identities", [])), list(d.get("dev_domains", []))
    return [], []

def main(argv):
    owners, dev = _allowlists()
    if not argv:
        texts = [("<stdin>", sys.stdin.read())]
    else:
        texts = []
        for p in argv:
            if p == "-":
                texts.append(("<stdin>", sys.stdin.read()))
            else:
                texts.append((p, Path(p).read_text()))
    findings = []
    for name, text in texts:
        for f in scan(text, owners, dev):
            findings.append((name, f))
    for name, f in findings:
        print(f"{name}: {f.kind}: {f.value!r}")
    return 1 if findings else 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
