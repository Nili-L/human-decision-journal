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
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_IPV6 = re.compile(r"\b(?:[0-9a-f]{1,4}:){2,7}[0-9a-f]{1,4}\b", re.I)
_TICKET = re.compile(r"(?:#\d{3,})|(?:\b[A-Z]{2,5}-\d{2,}\b)")
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
    for m in _URL.finditer(text):
        if m.group(1).lower() not in dev:
            add("domain", m, m.group(1))
    for m in _BARE_DOMAIN.finditer(text):
        host = m.group(1).lower()
        # Skip if this domain token is contained within an email address.
        in_email = any(es <= m.start() and m.end() <= ee for es, ee in email_spans)
        if host not in dev and not in_email:
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
    for rx in _SECRETS:
        for m in rx.finditer(text):
            add("secret", m)
    return out
