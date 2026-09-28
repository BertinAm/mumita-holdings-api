#!/usr/bin/env python3
"""Fail if anything that must not be public is in the repository.

This backend is a PUBLIC repository (Namecheap pulls it from git). Run this
before every commit and in CI:

    python scripts/check_public.py            # tracked + untracked-not-ignored files
    python scripts/check_public.py --tracked  # tracked files only

It checks, for every file git would publish:
- forbidden files: .env (not .env.example), databases, dumps, keys,
  certificates, uploads under media/;
- binary files outside seed_assets/ (public logos only);
- secret-looking content: private keys, AWS/Google/Slack/GitHub/Stripe
  tokens, hard-coded SECRET_KEY / password / token assignments with a
  literal value that is not an obvious placeholder;
- personal email addresses: anything not on an example/placeholder domain
  or a company role address.

Exit code 1 lists every finding. Run from anywhere inside the repository.
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FORBIDDEN_NAME = re.compile(
    r'(^|/)(\.env(\..+)?|db\.sqlite3.*|.*\.(sqlite3?|db|sql|dump|bak|pem|key|p12|pfx|crt|cer|jks|keystore))$'
)
ALLOWED_NAMES = {'.env.example'}
FORBIDDEN_DIRS = ('media/', 'staticfiles/', 'tmp/')
BINARY_OK_DIR = 'seed_assets/'
TEXT_EXT = {
    '.py', '.md', '.txt', '.html', '.yml', '.yaml', '.json', '.toml', '.cfg', '.ini', '.example', '.svg',
    '.gitignore', '.css', '.js', '',
}

SECRET_PATTERNS = [
    ('private key', re.compile(r'-----BEGIN (RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY')),
    ('AWS access key', re.compile(r'\bAKIA[0-9A-Z]{16}\b')),
    ('Google API key', re.compile(r'\bAIza[0-9A-Za-z_-]{35}\b')),
    ('GitHub token', re.compile(r'\bgh[pousr]_[A-Za-z0-9]{36,}\b')),
    ('Slack token', re.compile(r'\bxox[abposr]-[A-Za-z0-9-]{10,}')),
    ('Stripe live key', re.compile(r'\b[sr]k_live_[A-Za-z0-9]{16,}')),
    ('SendGrid key', re.compile(r'\bSG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}')),
    ('JWT', re.compile(r'\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}')),
    ('URL with credentials', re.compile(r'\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s:@]{3,}@[^\s]+', re.I)),
]
# NAME = 'literal' / NAME=literal where NAME looks secret. Upper-case names
# (env files, settings) match any value; lower-case names (code) only when the
# value is a quoted string literal.
SECRET_WORDS = r'(SECRET|PASSWORD|PASSWD|TOKEN|API_KEY|PRIVATE_KEY|INGEST_KEY|REVALIDATE_KEY)'
ASSIGNMENT = re.compile(
    r'\b(?P<name>[A-Z0-9_]*' + SECRET_WORDS + r'[A-Z0-9_]*)[\'"]?\s*[:=]\s*'
    r'(?P<q>[\'"]?)(?P<value>[^\'"\s,)#]{6,})(?P=q)'
)
ASSIGNMENT_CODE = re.compile(
    r'(?i)\b(?P<name>\w*' + SECRET_WORDS + r'\w*)[\'"]?\s*[:=]\s*(?P<q>[\'"])(?P<value>[^\'"\s]{8,})(?P=q)'
)
PLACEHOLDER = re.compile(
    r'(?i)^(change-?me.*|example.*|placeholder|x{3,}|\*{3,}|<.*>|\$\{?\w+\}?|none|null|true|false|'
    r'os\.environ.*|env_\w+\(.*|settings\..*|django-insecure-local-dev-only|test-.*|dev-.*|'
    r'request\..*|self\..*|v\[.*|data\..*|password|new|current|options.*|kwargs.*|generate_password.*|'
    r'secrets\..*|\w+\(.*|[a-z_]+(\.[a-z_]+)*)$'
)
EMAIL = re.compile(r'\b[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+\.)+[A-Za-z]{2,}\b')
# RFC 2606 reserved names (example.com/.org/.net, .example, .test, .invalid, .localhost).
EMAIL_OK_DOMAINS = re.compile(
    r'(?i)@(([a-z0-9-]+\.)*(example\.(com|org|net)|example|localhost|invalid|test)|anthropic\.com)$'
)
COMPANY_DOMAIN = '@mumitaholdings.com'
ROLE_LOCALS = {'info', 'website', 'noreply', 'no-reply', 'contact', 'hello', 'admin', 'webmaster', 'name'}


def files(tracked_only):
    cmd = ['git', 'ls-files', '-z', '--cached']
    if not tracked_only:
        cmd += ['--others', '--exclude-standard']
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, check=True).stdout
    return sorted({p for p in out.decode().split('\0') if p and (ROOT / p).is_file()})


def email_ok(address):
    if EMAIL_OK_DOMAINS.search(address):
        return True
    domain = address.lower().split('@')[1]
    if domain == COMPANY_DOMAIN[1:] or domain.endswith('.' + COMPANY_DOMAIN[1:]):
        local = address.split('@')[0].lower()
        return local in ROLE_LOCALS or local.startswith('test')
    return False


def check_file(path):
    findings = []
    p = Path(path)
    if p.name not in ALLOWED_NAMES and FORBIDDEN_NAME.search(path):
        findings.append('forbidden file type')
    if path.startswith(FORBIDDEN_DIRS):
        findings.append('uploaded/generated files must not be committed')
    raw = (ROOT / path).read_bytes()
    is_text = p.suffix.lower() in TEXT_EXT or p.name in ALLOWED_NAMES or p.name.startswith('.')
    if b'\0' in raw[:8192] or not is_text:
        if not path.startswith(BINARY_OK_DIR):
            findings.append('binary file outside seed_assets/')
        return findings
    if path.startswith(BINARY_OK_DIR) and p.suffix.lower() == '.svg':
        return findings  # third-party logo markup: no secrets, only paths
    text = raw.decode('utf-8', errors='replace')
    for lineno, line in enumerate(text.splitlines(), 1):
        if 'check_public: ignore' in line:
            continue
        for label, rx in SECRET_PATTERNS:
            if rx.search(line):
                findings.append(f'line {lineno}: {label}')
        for rx in (ASSIGNMENT, ASSIGNMENT_CODE):
            for m in rx.finditer(line):
                if not PLACEHOLDER.match(m.group('value')):
                    findings.append(f'line {lineno}: literal value assigned to {m.group("name")}')
        for m in EMAIL.finditer(line):
            if not email_ok(m.group(0)):
                findings.append(f'line {lineno}: email address {m.group(0)!r} (use an example.com or role address)')
    return findings


def main(argv):
    tracked_only = '--tracked' in argv
    problems = {}
    for path in files(tracked_only):
        found = check_file(path)
        if found:
            problems[path] = found
    if problems:
        print('check_public: NOT safe to publish:')
        for path, found in problems.items():
            for item in found:
                print(f'  {path}: {item}')
        return 1
    print(f'check_public: OK ({len(files(tracked_only))} files checked)')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
