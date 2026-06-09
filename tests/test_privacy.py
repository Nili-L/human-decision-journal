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
