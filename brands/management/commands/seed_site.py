"""Load the real, documented reference data: brands, products, regions and
partners. Idempotent (update_or_create by slug/key); safe to re-run.

Every value is transcribed from a project source, cited per block. Nothing is
invented: no people, no posts, no figures. Unconfirmed items are seeded
unpublished or left blank, never guessed.
"""

from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction

from brands.models import Brand
from catalog.models import Product
from common.models import Status
from people.models import Partner, Region

PUBLISHED = Status.PUBLISHED

# Source: app/frontend/src/lib/data/brands.ts (keys, names, palette status,
# lines) and app/frontend/messages/en/companies.json (English copy).
BRANDS = [
    {
        'key': 'agro', 'name': 'Mumita Agro Consultancy', 'palette_status': 'provisional',
        'role': 'Consultancy and field services', 'short_name': 'Mumita Agro',
        'summary': 'Farm setup and management, capacity building, food processing infrastructure, and cold room storage. Most of what the group does day to day sits here.',
        'step_body': 'Farm setup and management, farmer training, and cold rooms and warehouses to rent.',
    },
    {
        'key': 'foods', 'name': 'Mumita Foods', 'palette_status': 'approved',
        'role': 'Food processing', 'short_name': 'Mumita Foods',
        'summary': 'Indigenous vegetables, snails and mushrooms, cleaned and packed for retail. Cook Easy, Eat Healthy.',
        'step_body': 'Indigenous leaves, plantain, snails and mushrooms, cleaned, dried or frozen and packed under LYDA and Mumi Chips.',
    },
    {
        'key': 'prais', 'name': 'Praïs', 'palette_status': 'approved',
        'role': 'Catering and nutrition', 'short_name': 'Praïs catering, Buea',
        'summary': 'Event catering, restaurant service and diet consultancy. Trains and employs young cooks and dieticians.',
        'step_body': 'Event catering, a restaurant serving students in Buea, and diet advice for people and institutions. Praïs trains and employs young cooks and dieticians.',
    },
    {
        'key': 'marketplace', 'name': 'Mumita Marketplace', 'palette_status': 'provisional',
        'role': 'Platform', 'short_name': 'Marketplace',
        'summary': 'A mobile app, web platform and USSD channel connecting farmers to buyers. Going live in phases from late 2026.',
        'step_body': 'An app, a website and a USSD line linking farmers to buyers.',
    },
]
# Lines of Mumita Foods (brands.ts `lines`; HANDOFF §5).
LINES = [('lyda', 'LYDA', 'foods'), ('mumi-chips', 'Mumi Chips', 'foods')]

# Source: app/frontend/src/lib/data/products.ts (slug, brand, media, cutout)
# and app/frontend/messages/en/products.json (name, blurb, alt).
# Weights are left blank: pack weights conflict across sources (SITEMAP §6 D21).
PRODUCTS = [
    {
        'slug': 'plantain-flour', 'brand': 'foods', 'media_key': '2025-05-img-8580', 'cutout': '',
        'name': 'Plantain Flour',
        'blurb': 'Naturally gluten-free, milled from organically grown plantain. For fufu, baking and baby food.',
        'alt': 'Mumita Foods plantain flour retail pack',
    },
    {
        'slug': 'dried-okong-obong', 'brand': 'foods', 'media_key': '2025-05-img-7073',
        'cutout': '/media/dried-okong-obong-cutout.webp',
        'name': 'Dried Okong Obong',
        'blurb': 'Indigenous leaf, cleaned and dried. Keeps for months without refrigeration.',
        'alt': 'Mumita Foods dried Okong Obong pack',
    },
    {
        'slug': 'amaranth', 'brand': 'foods', 'media_key': '2025-05-img-7077',
        'cutout': '/media/amaranth-cutout.webp',
        'name': 'Amaranth',
        'blurb': 'Dried green leaf, cleaned and sealed in a 650g pack. No additives, no colouring.',
        'alt': 'Mumita Foods dried amaranth packs',
    },
    {
        'slug': 'mumita-kukkeys', 'brand': 'foods', 'media_key': '2025-05-img-8576',
        'cutout': '/media/kukkeys-front-cutout.webp',
        'name': "Mumita Kuk'Keys",
        'blurb': 'Gluten-free plantain cookies. Low sugar, no additives, made for lunchboxes.',
        'alt': "Mumita Kuk'Keys plantain cookie packs",
    },
    {
        'slug': 'moringa-lemon-tea', 'brand': 'foods', 'media_key': '2025-05-img-9533', 'cutout': '',
        'name': 'Moringa Lemon Tea',
        'blurb': 'Twelve sealed bags per pouch. Moringa with lemon, grown and dried locally.',
        'alt': 'Moringa lemon tea pouch',
    },
    {
        # The pack carries "C-mile" branding (HANDOFF §8): seeded in review, not published.
        'slug': 'crispy-potato-chips', 'brand': 'foods', 'media_key': '2025-05-img-6779', 'cutout': '',
        'name': 'Crispy Potato Chips',
        'blurb': 'Fried and packed at Bonduma Gate.',
        'alt': 'Crispy potato chips pack',
        'status': Status.REVIEW,
    },
]

# Source: app/frontend/src/lib/data/regions.ts and messages/en/common.json.
# Only the Southwest has a documented note.
REGIONS = [
    ('southwest', 'Southwest', 'Southwest', 'Buea head office'),
    ('littoral', 'Littoral', 'Littoral', ''),
    ('west', 'West', 'West', ''),
    ('north', 'North', 'North', ''),
    ('centre', 'Centre', 'Centre', ''),
]

# Source: app/frontend/src/lib/data/backers.ts, 03-assets/logos/partners/SOURCES.md
# (logos downloaded with the client's approval) and the Review (brief-documents-
# extracted.txt, §1 and §9). UNDP's relationship is not stated in any document,
# so its note is blank (SITEMAP §6 E29).
PARTNERS = [
    ('gca', 'Global Center on Adaptation', 'institutional', 'https://gca.org/', 'gca-logo-white.svg',
     'YouthADAPT Challenge award, with the African Development Bank'),
    ('auf', 'Agence universitaire de la Francophonie', 'institutional', 'https://www.auf.org/', 'auf-logo.svg',
     'AUF-AFD grant relationship'),
    ('afdb', 'African Development Bank', 'institutional', 'https://www.afdb.org/', 'afdb-logo.svg',
     'YouthADAPT Challenge award'),
    ('fonds-pierre-castel', 'Fonds Pierre Castel', 'institutional', 'https://www.fonds-pierre-castel.org/',
     'fonds-pierre-castel-logo.png', 'Prix Pierre Castel award'),
    ('undp', 'UNDP', 'institutional', 'https://www.undp.org/', 'undp-logo.svg', ''),
    ('carrefour', 'Carrefour', 'buyer', 'https://www.carrefour.com/', 'carrefour-mark.svg',
     'Stockist: continuous supply in Cameroon'),
]

LOGO_DIR = Path(settings.BASE_DIR).parent.parent / '03-assets' / 'logos' / 'partners'


class Command(BaseCommand):
    help = 'Seed brands, products, regions and partners from the documented sources.'

    @transaction.atomic
    def handle(self, *args, **options):
        for order, b in enumerate(BRANDS):
            Brand.objects.update_or_create(
                key=b['key'],
                defaults={
                    'slug': b['key'], 'name': b['name'], 'kind': Brand.Kind.COMPANY,
                    'palette_status': b['palette_status'], 'status': PUBLISHED, 'sort_order': order,
                    'role_en': b['role'], 'short_name_en': b['short_name'],
                    'summary_en': b['summary'], 'step_body_en': b['step_body'],
                    'signoff_en': 'A Mumita Company',
                },
            )
        for order, (key, name, parent) in enumerate(LINES):
            Brand.objects.update_or_create(
                key=key,
                defaults={
                    'slug': key, 'name': name, 'kind': Brand.Kind.LINE,
                    'parent': Brand.objects.get(key=parent), 'status': PUBLISHED,
                    'sort_order': 100 + order, 'signoff_en': 'A Mumita Company',
                },
            )

        for order, p in enumerate(PRODUCTS):
            Product.objects.update_or_create(
                slug=p['slug'],
                defaults={
                    'brand': Brand.objects.get(key=p['brand']), 'category': Product.Category.PROCESSED,
                    'media_key': p['media_key'], 'cutout': p['cutout'],
                    'name_en': p['name'], 'blurb_en': p['blurb'], 'alt_en': p['alt'],
                    'status': p.get('status', PUBLISHED), 'sort_order': order,
                },
            )

        for order, (key, name, geo, note) in enumerate(REGIONS):
            Region.objects.update_or_create(
                key=key,
                defaults={'name_en': name, 'geo_key': geo, 'note_en': note, 'status': PUBLISHED, 'sort_order': order},
            )

        logos = 0
        for order, (slug, name, tier, url, logo, note) in enumerate(PARTNERS):
            partner, _ = Partner.objects.update_or_create(
                slug=slug,
                defaults={
                    'name': name, 'tier': tier, 'url': url, 'relationship_en': note,
                    'permission_to_display': True, 'status': PUBLISHED, 'sort_order': order,
                },
            )
            source = LOGO_DIR / logo
            if not partner.logo and source.exists():
                with source.open('rb') as fh:
                    partner.logo.save(logo, File(fh), save=True)
                logos += 1

        self.stdout.write(self.style.SUCCESS(
            f'Seeded {Brand.objects.count()} brands, {Product.objects.count()} products, '
            f'{Region.objects.count()} regions, {Partner.objects.count()} partners ({logos} logos attached).'
        ))
