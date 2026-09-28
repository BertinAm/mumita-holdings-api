# Mumita Holdings — website API and CMS

The backend for the **Mumita Holdings SARL** website: a Django 6.1 + Django
REST Framework 3.18 service. The Django admin is the CMS for the brands,
products, services, blog posts, team, partners, regions and gallery. The
public API is read-only, apart from one write endpoint: the website's
four-field enquiry form. The frontend is the Next.js site
(`mumita-holdings-web`).

## Stack

| | |
|---|---|
| Framework | Django 6.1, Django REST Framework 3.18 |
| Translations | django-modeltranslation: a column per locale (en, fr, sw, es, zh, pt), English fallback |
| Security | django-axes (admin login lock-out), django-cors-headers, CSP and hardened settings when DEBUG is off |
| Database | SQLite in development; PostgreSQL when `DJANGO_DB_NAME` is set (psycopg2) |

Python 3.12 or later (developed on 3.14).

## Project layout

```
config/        settings (all environment-driven), urls, wsgi/asgi
api/           DRF viewsets, serializers and the /api/v1/ routes
brands/        Brand: the four companies and the Foods lines (colours live in the frontend)
catalog/       Product and Service
content/       Post (true original publish dates), GalleryItem
people/        TeamMember (no photo field, by design), Partner, Region
engagement/    Enquiry: the form endpoint, notification email, retention purge
common/        abstract base models (status, ordering, timestamps), publish/draft admin
               actions, and locale negotiation (?lang= → Accept-Language → English)
tests/         the test suite (models, API filters, enquiry validation, locale fallback)
```

## Run it

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_site          # brands, products, regions, partners
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py runserver          # http://127.0.0.1:8000
```

- Admin (CMS): `http://127.0.0.1:8000/cms-admin/` in development (`DJANGO_ADMIN_URL`).
- API root: `http://127.0.0.1:8000/api/v1/`
- Tests: `.venv/bin/python manage.py test tests`
- Deploy check: `DJANGO_DEBUG=0 DJANGO_SECRET_KEY=... DJANGO_ALLOWED_HOSTS=... DJANGO_EMAIL_HOST=... .venv/bin/python manage.py check --deploy`
- Daily cron in production: `manage.py purge_enquiries` (deletes enquiries past their retention date).

(In the original monorepo the virtualenv sits at `../backend-venv`; the commands are the same.)

`seed_site` loads only documented data: the four companies and the two
Foods lines, the six products from `frontend/src/lib/data/products.ts` with
their English copy from `messages/en/products.json`, the five regions, and
the six partners (GCA, AUF, AfDB, Fonds Pierre Castel, UNDP, Carrefour),
attaching logos from `03-assets/logos/partners/`. It creates no people and no
posts. Pack weights are blank because the sources conflict (SITEMAP §6 D21).
Crispy Potato Chips is seeded in review, not published, because of the "C-mile"
pack branding (HANDOFF §8). UNDP's relationship note is blank because no
document states it. Re-running it is safe.

## Environment variables

Every variable is optional in development. With `DJANGO_DEBUG=0`, those marked
**required** must be set or the process refuses to start (or `check --deploy`
fails).

| Variable | Default | Notes |
|---|---|---|
| `DJANGO_DEBUG` | `1` | `0` in staging and production |
| `DJANGO_SECRET_KEY` | dev-only key | **required** when DEBUG is off |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1,[::1]` (dev) | **required**, comma-separated |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | empty | e.g. `https://api.mumitaholdings.com`, for the admin behind a proxy |
| `DJANGO_CORS_ALLOWED_ORIGINS` | `http://localhost:3000,http://localhost:3111` (dev) | the frontend origin(s), comma-separated |
| `DJANGO_ADMIN_URL` | `cms-admin/` | use something unguessable in production; `admin/` is refused |
| `DJANGO_DB_NAME`, `_USER`, `_PASSWORD`, `_HOST`, `_PORT` | unset: SQLite | set `DJANGO_DB_NAME` to switch to PostgreSQL |
| `DJANGO_EMAIL_HOST`, `_PORT` (587), `_USER`, `_PASSWORD`, `_USE_TLS` (1) | unset: console backend | **required** in production (SMTP) |
| `DJANGO_DEFAULT_FROM_EMAIL` | `website@localhost` | sender of staff notifications |
| `ENQUIRY_NOTIFY_EMAILS` | `info@localhost` (dev) | staff recipients, comma-separated |
| `ENQUIRY_RETENTION_DAYS` | `365` | Review §11 retention rule; confirm with the client |
| `ENQUIRY_THROTTLE_RATE` | `5/hour` | per client IP |
| `ENQUIRY_LOG_LEVEL` | `INFO` | logs carry enquiry id and type only |
| `DJANGO_NUM_PROXIES` | `0` | reverse proxies in front (Cloudflare + nginx = 2), for client-IP detection |
| `DJANGO_BEHIND_PROXY` | `0` | `1` to trust `X-Forwarded-Proto: https` from the proxy |
| `DJANGO_SECURE_SSL_REDIRECT` | `1` | when DEBUG is off |
| `DJANGO_HSTS_SECONDS` | `31536000` | when DEBUG is off |
| `DJANGO_HSTS_INCLUDE_SUBDOMAINS` | `1` | |
| `DJANGO_HSTS_PRELOAD` | `0` | see below |
| `DJANGO_MEDIA_ROOT`, `DJANGO_MEDIA_URL`, `DJANGO_STATIC_ROOT` | `media/`, `/media/`, `staticfiles/` | |
| `AXES_FAILURE_LIMIT` | `5` | failed admin logins before lock-out |

`check --deploy` leaves one warning, `security.W021` (HSTS preload off). That
is deliberate: preload is very hard to undo, so turn it on with
`DJANGO_HSTS_PRELOAD=1` only once the domain and every subdomain serve HTTPS.

## Translations

Six locales, with the frontend's codes: `en fr sw es zh pt`.
Translatable fields use **django-modeltranslation**: each one gets a column
per locale (`name_en`, `name_fr`, ... `name_pt`), edited in language tabs in
the admin. Registrations are in each app's `translation.py`. English is the
fallback: a field left empty in French returns the English text. Proper nouns
(brand, partner and person names) are not translated.

Adding a translated field: add it to the model, list it in `translation.py`,
then `makemigrations`.

## API

Base: `/api/v1/`. JSON only in production (the browsable API is on only with
DEBUG). All list endpoints are paginated (`?page=`, 20 per page:
`{count, next, previous, results}`) and return **published rows only**. Team
members also need `consent_to_publish`; partners need `permission_to_display`;
posts need `published_at` in the past. GET responses carry
`Cache-Control: public, max-age=300`.

Locale: `?lang=fr`, else `Accept-Language`, else English. Responses carry
`Content-Language` and `Vary: Accept-Language`. `zh-Hans`, `fr-FR` and so on
map to the site codes.

| Endpoint | Lookup | Filters |
|---|---|---|
| `GET /api/v1/brands/` | `/{slug}/` | `?kind=company\|line`, `?parent=foods` |
| `GET /api/v1/products/` | `/{slug}/` | `?brand=foods`, `?category=processed` |
| `GET /api/v1/services/` | `/{slug}/` | `?brand=agro` |
| `GET /api/v1/posts/` | `/{slug}/` (adds `body`, SEO fields) | `?lens=nutrition`, `?author={slug}` |
| `GET /api/v1/team/` | `/{slug}/` | `?department=it`, `?tier=executive` |
| `GET /api/v1/partners/` | `/{slug}/` | `?tier=institutional\|buyer` |
| `GET /api/v1/regions/` | `/{key}/` | |
| `GET /api/v1/gallery/` | `/{id}/` | `?category=` |
| `POST /api/v1/enquiries/` | | see below |

Brand colours are not in the API. The frontend owns the palette, keyed by the
brand `key` (`[data-brand]`). There is no price field anywhere. `TeamMember`
has no photo field, by design (Review §7); a test fails if one is added.
Department marks are frontend SVGs keyed by `department`
(`agric-consultancy`, `food-processing`, `nutrition`, `it`, `hr`).

## The enquiry endpoint

```
POST /api/v1/enquiries/?lang=fr
Content-Type: application/json

{"name": "…", "contact": "email or phone", "type": "buy", "message": "…", "website": ""}
```

- **Four user fields, no more** (Review §10): `name` (2–100 chars), `contact`
  (a valid email, or a phone number of 7–15 digits, `+ ( ) - .` and spaces
  allowed), `type` (`buy`, `farm`, `partner`, `other`), `message` (2–2000 chars).
  Any other key gets a 400 with that key named, so a fifth field cannot slip in.
- `website` is the **honeypot**. Render it hidden from people and assistive tech
  and leave it empty. If it is filled, the API answers exactly as on success and
  stores and sends nothing.
- Responses: `201 {"ok": true}`; `400 {field: [messages]}`; `403` if the
  browser `Origin` is not in `DJANGO_CORS_ALLOWED_ORIGINS`; `429` over the rate
  limit (5 per hour per IP by default, with a `Retry-After` header).
- The server records the locale (from `?lang=` or `Accept-Language`), the page
  (from `Referer`), and a keyed hash of the IP, never the IP itself. It emails
  `ENQUIRY_NOTIFY_EMAILS`. The subject carries only the enquiry type.
- No cookies and no session auth, so CSRF tokens do not apply. CORS allows
  only the configured frontend origins. There is no CAPTCHA.

From the frontend, either call it from the browser:

```ts
const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/enquiries/?lang=${locale}`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ name, contact, type, message, website }),
});
if (res.status === 201) { /* thank-you state */ }
else if (res.status === 400) { const errors = await res.json(); /* per-field messages */ }
else if (res.status === 429) { /* "please try again later" */ }
```

or from a Next.js server action or route handler. In that case every request
reaches Django from the Next server's IP, so the throttle would count all
visitors together. Forward the visitor's IP in `X-Forwarded-For` and set
`DJANGO_NUM_PROXIES` to match, or call from the browser instead.

The error messages come back in English. The frontend should show its own
translated message per field from `messages/<locale>/contact.json`, keyed by
field name.

## Security baseline

- DEBUG off enables SSL redirect, HSTS (1 year, subdomains), secure session and
  CSRF cookies. `DJANGO_BEHIND_PROXY` enables the proxy scheme header.
- Always on: CSP (Django's built-in middleware, a strict `'self'` policy for the
  admin and JSON), `X-Frame-Options: DENY`, nosniff, a strict referrer policy,
  and COOP.
- The admin sits at `DJANGO_ADMIN_URL`, never `/admin/`. Passwords need 12+
  characters plus Django's four validators. **django-axes** locks a
  username+IP pair for 1 hour after 5 failed logins. `manage.py axes_reset`
  clears lock-outs.
- Upload size is capped at 2 MB. Logos accept svg, png or webp only. Serve
  `MEDIA_ROOT` from a separate path with `Content-Security-Policy: sandbox` in
  front of SVGs. Only staff can upload.
- Logs never contain enquiry content or contact details.
- Not done yet (PLAN §0.2): 2FA for admin accounts (`django-otp` is the likely
  route), role-based permissions for the five blog specialists, and a shared
  cache (Redis) for throttle counters when running more than one process.
