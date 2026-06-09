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

def test_repo_blurb_preserved_roundtrip():
    src = new_journal_text()
    # build a journal with a repo that has a blurb + one entry, via raw text
    body = (
        "# Work\n\n"
        "## acme\n\n"
        "> Solo-built thing.\n>\n> **Authorship:** all Josh.\n\n"
        "### 2026-02-01 — did a thing\n\n"
        "**Tags:** domain: backend · activity: design\n"
    )
    # splice the body after the timeline marker of an empty journal
    from server.journal import TL_END
    text = src.split(TL_END)[0] + TL_END + "\n\n" + body
    j = parse(text)
    assert j.repo_blurb.get("acme", "").startswith("> Solo-built thing.")
    assert "**Authorship:** all Josh." in j.repo_blurb["acme"]
    assert len(j.entries) == 1 and j.entries[0].repo == "acme"
    out = render(j, VOCAB)
    assert "> Solo-built thing." in out and "**Authorship:** all Josh." in out
    # blurb appears after the ## acme heading and before the entry
    assert out.index("## acme") < out.index("Solo-built thing") < out.index("### 2026-02-01")
    # round-trip stable
    j2 = parse(out)
    assert j2.repo_blurb.get("acme", "").startswith("> Solo-built thing.")
    assert len(j2.entries) == 1
