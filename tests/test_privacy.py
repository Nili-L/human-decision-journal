from server.privacy import scan

OWNER = ["jo@ironscales.com", "Jo"]
DEV = ["github.com", "bitbucket.org", "localhost"]

def kinds(text):
    return sorted({f.kind for f in scan(text, OWNER, DEV)})

def test_blocks_customer_email_allows_owner():
    assert "email" in kinds("contact alice@acme.com about it")
    assert scan("ping jo@ironscales.com", OWNER, DEV) == []

def test_domain_allowlist():
    assert scan("see https://github.com/Jo/x", OWNER, DEV) == []
    assert "domain" in kinds("their portal at acme-corp.com is down")

def test_commit_sha_not_blocked():
    assert scan("fixed in 267feb6d a030 b941 ed85585ae79e", OWNER, DEV) == []

def test_card_luhn():
    assert "card" in kinds("card 4111 1111 1111 1111")
    assert "card" not in kinds("order 4111 1111 1111 1112")  # fails Luhn

def test_ssn_and_secret_and_ip():
    assert "ssn" in kinds("ssn 123-45-6789")
    assert "secret" in kinds("key AKIAIOSFODNN7EXAMPLE here")
    assert "secret" in kinds("token ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789")
    assert "ipv4" in kinds("host 203.0.113.7")

def test_ordinary_prose_passes():
    assert scan("Chose to split the parser into smaller modules for testability.", OWNER, DEV) == []


# --- Regression tests for false-positive fixes ---

BENIGN = [
    "Refactored server/privacy.py and config.toml for clarity.",
    "Updated README.md and DECISIONS_JOURNAL.md.",
    "Bumped to version 3.14.3 today, 2026-06-09.",
    "Fixed in commit 267feb6d after review.",
    "See https://github.com/Jo/human-decision-journal/blob/main/server/main.py",
    "Chose FastMCP over a hand-rolled server.",
    "Touched main.js, styles.css, routes.ts and utils.go.",
    "Build timing was 12:34:56 across feed:face nodes.",
    "Cited RFC-2616 and PR-12 in the notes.",
]

SENSITIVE = [
    ("email the customer at alice@acme-corp.com", "email"),
    ("their site acme-corp.com went down", "domain"),
    ("ticket #12345", "ticket"),
    ("ref ZD-9981 from support", "ticket"),
    ("call 415-555-0132", "phone"),
    ("card 4111 1111 1111 1111", "card"),
    ("ssn 123-45-6789", "ssn"),
    ("host 203.0.113.7", "ipv4"),
    ("key AKIAIOSFODNN7EXAMPLE", "secret"),
    ("token ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789", "secret"),
    ("db at fe80::1ff:fe23:4567:890a today", "ipv6"),
]

def test_benign_inputs_have_no_findings():
    for t in BENIGN:
        assert scan(t, OWNER, DEV) == [], f"false positive in {t!r}: {scan(t, OWNER, DEV)}"

def test_sensitive_inputs_are_flagged():
    for t, kind in SENSITIVE:
        ks = kinds(t)
        assert kind in ks, f"missed {kind} in {t!r}: {ks}"

def test_no_duplicate_findings():
    fs = scan("http://acme.com/path", OWNER, DEV)
    seen = [(f.kind, f.value, f.start, f.end) for f in fs]
    assert len(seen) == len(set(seen))
