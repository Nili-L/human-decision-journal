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

def test_categorization_defaults_off(tmp_path):
    (tmp_path / "config.toml").write_text(
        'owner_name="Jo"\nowner_identities=["jo@x.com"]\n'
        'journal_path="J.md"\nrepo_roots=[]\ndev_domains=["github.com"]\n'
    )
    cfg = load_config(tmp_path / "config.toml")
    assert cfg.categorization_enabled is False
    assert cfg.state_dir is not None  # defaulted

def test_categorization_enabled_with_state_dir(tmp_path):
    (tmp_path / "config.toml").write_text(
        'owner_name="Jo"\nowner_identities=["jo@x.com"]\n'
        'journal_path="J.md"\nrepo_roots=[]\ndev_domains=["github.com"]\n'
        '[categorization]\nenabled=true\nstate_dir="~/somewhere/state"\n'
    )
    cfg = load_config(tmp_path / "config.toml")
    assert cfg.categorization_enabled is True
    assert cfg.state_dir == Path("~/somewhere/state").expanduser()
