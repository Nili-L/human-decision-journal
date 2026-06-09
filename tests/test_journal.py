from server.journal import parse, render, Entry, DEFAULT_HEADER, new_journal_text
from server.vocab import load_vocab
from pathlib import Path

SEED = Path(__file__).resolve().parents[1] / "work-vocab.toml"
VOCAB = load_vocab(SEED, None)

def make_entry(repo="acme", cat="Work", date="2026-02-01", title="t"):
    return Entry(date=date, title=title, repo=repo, category=cat,
                 domains=["backend"], activities=["design"], tools=["fastmcp"],
                 raw="")

def test_roundtrip_empty_then_append():
    j = parse(new_journal_text())
    assert j.entries == []
    j.entries.append(make_entry())
    j.repo_category["acme"] = "Work"
    j.repo_order.setdefault("Work", []).append("acme")
    text = render(j, VOCAB)
    assert "## acme" in text and "### 2026-02-01 — t" in text
    assert "domain: backend" in text and "activity: design" in text
    assert "<!-- TOC:START -->" in text and "[acme](#acme)" in text
    assert "<!-- TIMELINE:START -->" in text

def test_parse_reads_back_tags_and_category():
    j = parse(new_journal_text())
    j.entries.append(make_entry(date="2026-03-01"))
    j.repo_category["acme"] = "Work"; j.repo_order.setdefault("Work", []).append("acme")
    j2 = parse(render(j, VOCAB))
    assert j2.repo_category["acme"] == "Work"
    e = j2.entries[0]
    assert e.domains == ["backend"] and e.activities == ["design"] and e.tools == ["fastmcp"]
    assert e.date == "2026-03-01"

def test_header_preserved_on_render():
    j = parse(new_journal_text())
    assert j.header.startswith("# Decisions Journal")
    j.header = j.header + "\nCUSTOM LINE\n"
    assert "CUSTOM LINE" in render(j, VOCAB)
