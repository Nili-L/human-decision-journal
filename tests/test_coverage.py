from server.coverage import RepoCoverage, build_report


def _rc(repo, cat, active, logged, subjects=None):
    return RepoCoverage(repo=repo, category=cat, active=set(active),
                        logged=set(logged), subjects=subjects or {})


def test_repo_coverage_math():
    rc = _rc("a", "Work", {"2026-06-01", "2026-06-02", "2026-06-03"}, {"2026-06-01"})
    assert rc.active_days == 3
    assert rc.documented_days == 1
    assert rc.coverage == 33
    assert rc.gap_days == ["2026-06-02", "2026-06-03"]


def test_headline_hides_repo_names():
    repos = [_rc("secret-client", "Work", {"2026-06-01", "2026-06-02"}, {"2026-06-01"})]
    md, stats = build_report("Jo", repos, scope="work", level="headline")
    assert "secret-client" not in md
    assert "overall:" in md
    assert stats["coverage_pct"] == 50


def test_summary_shows_repo_no_dates():
    repos = [_rc("proj", "Work", {"2026-06-01", "2026-06-02"}, {"2026-06-01"})]
    md, _ = build_report("Jo", repos, scope="work", level="summary")
    assert "proj" in md and "coverage: 50%" in md
    assert "gap days:" not in md           # gap detail not shown at summary
    assert "2026-06-02" not in md.split("## proj")[1]   # no per-repo gap dates


def test_detailed_shows_gap_dates_full_shows_subjects():
    repos = [_rc("proj", "Work", {"2026-06-01", "2026-06-02"}, {"2026-06-01"},
                 subjects={"2026-06-02": ["refactor nav"]})]
    md_d, _ = build_report("Jo", repos, scope="work", level="detailed")
    assert "2026-06-02" in md_d and "refactor nav" not in md_d
    md_f, _ = build_report("Jo", repos, scope="work", level="full")
    assert "2026-06-02" in md_f and "refactor nav" in md_f
