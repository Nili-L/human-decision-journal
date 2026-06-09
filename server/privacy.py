from __future__ import annotations
import re
from dataclasses import dataclass

@dataclass(frozen=True)
class Finding:
    kind: str
    value: str
    start: int
    end: int

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_URL = re.compile(r"\bhttps?://([\w.-]+)(?:/\S*)?", re.I)
_BARE_DOMAIN = re.compile(r"\b([a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)*\.[a-z]{2,})\b", re.I)

# Known code/doc file extensions — a bare-domain match whose final label is one
# of these is almost certainly a filename, not a real domain.  We skip it.
# Residual gap: a customer domain whose TLD collides with a code extension
# (e.g. acme.sh, acme.rs) may be skipped — acceptable per design.
_CODE_EXTENSIONS = frozenset(
    "py md toml js ts tsx jsx mjs cjs css scss go rb rs java cpp cc hpp h "
    "json yaml yml sh bash txt ini cfg lock sql html xml csv svg png jpg "
    "jpeg gif pdf kt swift php pl lua vue tf env".split()
)

# IPv4: not preceded or followed by additional dotted-number segments,
# to avoid matching prefixes of version strings like 1.2.3.4.5.
_IPV4 = re.compile(r"(?<!\d)(?<!\d\.)(?:\d{1,3}\.){3}\d{1,3}(?!\.\d)(?!\d)")

# IPv6: only match when the candidate contains '::' (compressed notation) OR
# is a full 8-group address.  This prevents ordinary colon-delimited tokens
# like "12:34:56" or "feed:face:1234:5678" from being flagged.
_IPV6 = re.compile(
    r"\b(?:"
    r"(?:[0-9a-f]{1,4}:){7}[0-9a-f]{1,4}"     # full 8-group
    r"|(?:[0-9a-f]{0,4}::(?:[0-9a-f]{1,4}:)*[0-9a-f]{0,4})"  # :: compressed
    r"|(?:[0-9a-f]{1,4}(?::[0-9a-f]{1,4})*::(?:[0-9a-f]{1,4}:)*[0-9a-f]{0,4})"
    r")\b",
    re.I,
)

# Ticket: exclude well-known dev/standards prefixes so RFC-2616, PR-12,
# CVE-2021-1234 are not caught.  Real support IDs like ZD-9981 still match.
_TICKET = re.compile(r"(?:#\d{3,})|(?:\b(?!RFC-|PR-|CVE-)(?:[A-Z]{2,5})-\d{2,}\b)")
_PHONE = re.compile(r"\b(?:\+?\d{1,2}[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CARD = re.compile(r"\b(?:\d[ -]?){13,16}\b")
_SECRETS = [
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{36}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b"),
    re.compile(r"\b\w+://[^\s:@/]+:[^\s:@/]+@[\w.-]+", re.I),
]

def _luhn_ok(digits: str) -> bool:
    nums = [int(c) for c in digits if c.isdigit()]
    if not (13 <= len(nums) <= 16):
        return False
    total, parity = 0, len(nums) % 2
    for i, n in enumerate(nums):
        if i % 2 == parity:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0

def scan(text: str, owner_identities: list[str], dev_domains: list[str]) -> list[Finding]:
    owners = {o.lower() for o in owner_identities}
    dev = {d.lower() for d in dev_domains}
    out: list[Finding] = []

    def add(kind, m, value=None):
        out.append(Finding(kind, value if value is not None else m.group(0), m.start(), m.end()))

    # Collect all email spans first so bare-domain scan can skip them.
    email_spans = []
    for m in _EMAIL.finditer(text):
        email_spans.append((m.start(), m.end()))
        if m.group(0).lower() not in owners:
            add("email", m)

    # Collect URL spans; add domain findings for non-allowlisted hosts.
    url_spans = []
    for m in _URL.finditer(text):
        url_spans.append((m.start(), m.end()))
        if m.group(1).lower() not in dev:
            add("domain", m, m.group(1))

    for m in _BARE_DOMAIN.finditer(text):
        host = m.group(1).lower()
        # Skip if the final label (TLD) is a known code/doc file extension.
        tld = host.rsplit(".", 1)[-1]
        if tld in _CODE_EXTENSIONS:
            continue
        # Skip if this token is fully contained within an email address.
        in_email = any(es <= m.start() and m.end() <= ee for es, ee in email_spans)
        if in_email:
            continue
        # Skip if this token is contained within an already-matched URL span
        # (prevents duplicates like acme.com being found both via _URL and here).
        in_url = any(us <= m.start() and m.end() <= ue for us, ue in url_spans)
        if in_url:
            continue
        if host not in dev:
            add("domain", m, host)

    for m in _IPV4.finditer(text):
        if all(0 <= int(p) <= 255 for p in m.group(0).split(".")):
            add("ipv4", m)
    for m in _IPV6.finditer(text):
        add("ipv6", m)
    for m in _TICKET.finditer(text):
        add("ticket", m)
    for m in _PHONE.finditer(text):
        add("phone", m)
    for m in _SSN.finditer(text):
        add("ssn", m)
    for m in _CARD.finditer(text):
        if _luhn_ok(m.group(0)):
            add("card", m)

    # Collect secret spans to suppress email/domain findings inside them
    # (e.g. connection strings contain both a domain and credentials).
    secret_spans = []
    for rx in _SECRETS:
        for m in rx.finditer(text):
            add("secret", m)
            secret_spans.append((m.start(), m.end()))

    # Deduplicate by (kind, value, start, end) and suppress email/domain
    # findings that are fully contained within a secret span.
    seen: set[tuple] = set()
    deduped: list[Finding] = []
    for f in out:
        key = (f.kind, f.value, f.start, f.end)
        if key in seen:
            continue
        seen.add(key)
        if f.kind in ("email", "domain"):
            in_secret = any(ss <= f.start and f.end <= se for ss, se in secret_spans)
            if in_secret:
                continue
        deduped.append(f)
    return deduped
