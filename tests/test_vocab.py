from pathlib import Path
from server.vocab import load_vocab, add_local_tag, TAGGING_GUIDANCE

SEED = Path(__file__).resolve().parents[1] / "work-vocab.toml"

def test_loads_seed():
    v = load_vocab(SEED, None)
    assert "backend" in v.domains and "debugging" in v.activities
    assert v.validate(["backend"], ["debugging"]) == []

def test_unknown_tags_reported():
    v = load_vocab(SEED, None)
    assert v.validate(["nope"], ["debugging"]) == ["domain:nope"]
    assert v.validate(["backend"], ["zzz"]) == ["activity:zzz"]

def test_local_merge_and_add(tmp_path):
    local = tmp_path / "work-vocab.local.toml"
    add_local_tag(local, "domain", "browser-extension", "browser extensions")
    v = load_vocab(SEED, local)
    assert "browser-extension" in v.domains
    assert v.validate(["browser-extension"], ["debugging"]) == []

def test_guidance_is_nonempty():
    assert "domain" in TAGGING_GUIDANCE and "activity" in TAGGING_GUIDANCE
