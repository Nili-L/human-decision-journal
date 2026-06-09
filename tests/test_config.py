import pytest
from pathlib import Path
from server.config import load_config, Config

def test_loads_and_expands(tmp_path):
    (tmp_path / "config.toml").write_text(
        'owner_name = "Jo"\n'
        'owner_identities = ["jo@x.com", "Jo"]\n'
        'journal_path = "DECISIONS_JOURNAL.md"\n'
        'repo_roots = ["~/code"]\n'
        'dev_domains = ["github.com"]\n'
    )
    cfg = load_config(tmp_path / "config.toml")
    assert isinstance(cfg, Config)
    assert cfg.owner_name == "Jo"
    assert cfg.owner_identities == ["jo@x.com", "Jo"]
    assert cfg.journal_path == (tmp_path / "DECISIONS_JOURNAL.md")
    assert cfg.repo_roots[0] == Path("~/code").expanduser()
    assert cfg.dev_domains == ["github.com"]

def test_missing_file_raises_with_hint(tmp_path):
    with pytest.raises(FileNotFoundError) as e:
        load_config(tmp_path / "config.toml")
    assert "config.example.toml" in str(e.value)
