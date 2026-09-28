"""Seed the genuine journal posts from the live site (seven, as of 2026-09-28).

    python manage.py seed_posts                      # from seed_assets/posts.json
    python manage.py seed_posts --export-from ../frontend   # rebuild that file first

The text comes from the frontend's messages/en/blog.json (posts.<slug>:
headline, dek, excerpt, body blocks) and the dates and hero keys from
src/lib/data/posts.ts. The snapshot lives in seed_assets/posts.json so the
seed works when the backend is deployed on its own.

Dates are the TRUE original publication dates. No post names an author, so
the byline is "Mumita Holdings" (README rule 2). Re-running updates the
rows by slug and never touches posts created in the dashboard.
"""

import html
import json
import re
from datetime import datetime, time
from datetime import timezone as dt_timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import translation

from content.models import Post, PostStatus

SNAPSHOT = Path(settings.BASE_DIR) / 'seed_assets' / 'posts.json'
BYLINE = 'Mumita Holdings'
POST_RE = re.compile(r'slug:\s*"([^"]+)",\s*date:\s*"(\d{4}-\d{2}-\d{2})",\s*category:\s*"([^"]+)",\s*hero:\s*"([^"]+)"')


INLINE_MARK = re.compile(r'(<b>.*?</b>|<i>.*?</i>|<a href="https?://[^"]+">.*?</a>)')
LINK = re.compile(r'^<a href="(https?://[^"]+)">(.*)</a>$')


def inline(text):
    """Escape, then turn the blog.json inline marks into HTML: <b>…</b> lead-ins
    into <strong>, <i>…</i> into <em> (its contents marked up the same way), and <a href="https://…">…</a> links
    (http(s) only, as in the frontend's PostBody)."""
    out = []
    for part in INLINE_MARK.split(text):
        if part.startswith('<b>') and part.endswith('</b>'):
            out.append(f'<strong>{html.escape(part[3:-4], quote=False)}</strong>')
        elif part.startswith('<i>') and part.endswith('</i>'):
            out.append(f'<em>{inline(part[3:-4])}</em>')
        elif m := LINK.match(part):
            out.append(f'<a href="{html.escape(m[1])}">{html.escape(m[2], quote=False)}</a>')
        else:
            out.append(html.escape(part, quote=False))
    return ''.join(out)


def blocks_to_html(blocks):
    """Same rules as the frontend's PostBody: p paragraph, h heading (h2),
    s sub-heading (h3), q pull-quote, l list with one item per line."""
    out = []
    for key, text in blocks.items():
        if key.startswith('h'):
            out.append(f'<h2>{inline(text)}</h2>')
        elif key.startswith('s'):
            out.append(f'<h3>{inline(text)}</h3>')
        elif key.startswith('q'):
            out.append(f'<blockquote><p>{inline(text)}</p></blockquote>')
        elif key.startswith('l'):
            items = ''.join(f'<li>{inline(line)}</li>' for line in text.split('\n') if line.strip())
            out.append(f'<ul>{items}</ul>')
        else:
            out.append(f'<p>{inline(text)}</p>')
    return '\n'.join(out)


def export(frontend):
    frontend = Path(frontend)
    messages = json.loads((frontend / 'messages' / 'en' / 'blog.json').read_text(encoding='utf-8'))['posts']
    meta = POST_RE.findall((frontend / 'src' / 'lib' / 'data' / 'posts.ts').read_text(encoding='utf-8'))
    if not meta:
        raise CommandError('No posts found in src/lib/data/posts.ts')
    posts = []
    for slug, date, category, hero in meta:
        m = messages[slug]
        posts.append({
            'slug': slug, 'date': date, 'category': category, 'media_key': hero,
            'title': m['headline'], 'card_title': m['title'], 'dek': m['dek'], 'excerpt': m['excerpt'],
            'hero_alt': m.get('heroAlt', ''), 'body_html': blocks_to_html(m['body']),
        })
    SNAPSHOT.parent.mkdir(exist_ok=True)
    SNAPSHOT.write_text(json.dumps(posts, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return len(posts)


class Command(BaseCommand):
    help = 'Seed the original journal posts from the live site (true original dates).'

    def add_arguments(self, parser):
        parser.add_argument('--export-from', metavar='FRONTEND_DIR',
                            help='Rebuild seed_assets/posts.json from the frontend sources first.')

    def handle(self, *args, export_from=None, **options):
        if export_from:
            self.stdout.write(f'Exported {export(export_from)} posts to {SNAPSHOT.name}.')
        posts = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
        created = 0
        with translation.override('en'), transaction.atomic():
            for p in posts:
                published_at = datetime.combine(
                    datetime.strptime(p['date'], '%Y-%m-%d').date(), time(9, 0), tzinfo=dt_timezone.utc
                )
                _, was_created = Post.objects.update_or_create(
                    slug=p['slug'],
                    defaults={
                        'title_en': p['title'], 'dek_en': p['dek'], 'excerpt_en': p['excerpt'],
                        'body_en': p['body_html'], 'media_key': p['media_key'], 'byline': BYLINE,
                        'status': PostStatus.PUBLISHED, 'published_at': published_at,
                    },
                )
                created += was_created
        self.stdout.write(self.style.SUCCESS(f'Seeded {len(posts)} posts ({created} new).'))
