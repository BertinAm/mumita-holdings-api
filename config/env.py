"""Environment helpers.

Settings come from process environment variables (cPanel "Setup Python App"
sets these per app). For convenience a `.env` file next to manage.py is also
read if it exists; values already present in the environment win. `.env` is
git-ignored; `.env.example` documents every variable with placeholders.
"""

import os
from pathlib import Path


def load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        if line.startswith('export '):
            line = line[len('export '):]
        key, _, value = line.partition('=')
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
            value = value[1:-1]
        os.environ.setdefault(key, value)


def env_str(name, default=''):
    return os.environ.get(name, default)


def env_list(name, default=''):
    return [item.strip() for item in os.environ.get(name, default).split(',') if item.strip()]


def env_bool(name, default):
    value = os.environ.get(name)
    return default if value in (None, '') else value.lower() in ('1', 'true', 'yes', 'on')


def env_int(name, default):
    value = os.environ.get(name)
    return default if value in (None, '') else int(value)
