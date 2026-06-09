import subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def run(text, tmp_path):
    f = tmp_path / "f.md"
    f.write_text(text)
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "scan.py"), str(f)],
                          capture_output=True, text=True)

def test_clean_passes(tmp_path):
    assert run("Chose to split modules.", tmp_path).returncode == 0

def test_customer_email_fails(tmp_path):
    r = run("email alice@acme.com", tmp_path)
    assert r.returncode == 1
    assert "email" in r.stdout
