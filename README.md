# Mumita Holdings: website API and CMS

This is the backend for the **Mumita Holdings SARL** website, a Django 6.1 +
Django REST Framework 3.18 service. It serves:

- the public read API (brands, products, services, posts, team, partners,
  regions, gallery, testimonials);
- the public forms (enquiries, testimonials) and the analytics ingest;
- the API for the two client-side apps on the Next.js site
  (`mumita-holdings-web`): the admin **dashboard** (`/dashboard`) and the
  article **editor** for publishers (`/write`);
- the Django admin, as a back-office CMS for the reference data.

The binding API contract is `06-plan/PLATFORM-CONTRACT.md` in the monorepo.
This README describes what is built.

> **This repository is public.** Namecheap pulls it from git. Never commit
> a secret, key, password, database file, upload, or a person's email
> address. Everything comes from environment variables (`.env.example`).
> Run `python scripts/check_public.py` before every commit. It fails on
> anything that looks sensitive.

## Stack

| | |
|---|---|
| Framework | Django 6.1, Django REST Framework 3.18 |
| Database | MySQL/MariaDB in production (through **PyMySQL**, pure Python, `utf8mb4`), SQLite in development, PostgreSQL also supported |
| Hosting | Namecheap cPanel "Setup Python App" (Phusion Passenger), `passenger_wsgi.py`. **WhiteNoise** serves static files |
| Images | Pillow (AVIF + WebP renditions), pillow-heif (HEIC uploads) |
| Article HTML | **nh3** sanitizer (allow-list) |
| Translations | django-modeltranslation: one column per locale (en, fr, sw, es, zh, pt), English fallback |
| Security | django-axes (login lock-out), django-cors-headers (credentials for the site origins), CSP and hardened settings when DEBUG is off |

Python 3.12 or later (developed on 3.14). Pillow in the dev venv encodes AVIF
(`PIL.features.check('avif')` is true), so renditions are AVIF and WebP. On a
host where it is false, uploads fall back to WebP only by themselves.

## Project layout

```
config/        settings (all environment-driven, optional .env), urls, wsgi/asgi
passenger_wsgi.py  cPanel/Passenger entry point
accounts/      realms (admins/publishers groups), Profile (name, must_change_password),
               LoginEvent, auth/ and manage/users|login-events views, email templates,
               create_admin and send_test_email commands
api/           public DRF viewsets/serializers and every /api/v1/ route
analytics/     DailyVisit aggregates, analytics/hit and manage/stats
brands/        Brand (companies and Foods lines), seed_site
catalog/       Product and Service
content/       Post + PostRevision (workflow), Image (renditions), GalleryItem,
               sanitize.py (nh3), images.py, dashboard.py (manage/write posts,
               gallery, uploads), seed_posts
engagement/    Enquiry + EnquiryReply (inbox), Testimonial, public form endpoints,
               purge_enquiries
people/        TeamMember (no photo field, by design), Partner, Region
common/        base models, locale negotiation, client IP + IP hashing, mail,
               revalidation webhook, pagination, deploy checks
seed_assets/   public partner logos and the six original posts (posts.json)
scripts/       check_public.py
tests/         the test suite
```

## Run it

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_site          # brands, products, regions, partners (+ logos)
.venv/bin/python manage.py seed_posts         # the six original journal posts
.venv/bin/python manage.py create_admin --email <name>@mumitaholdings.com --name "Your Name"
.venv/bin/python manage.py runserver localhost:8000
```

- Use **`localhost:8000`, not `127.0.0.1`**. The dashboards on
  `localhost:3111` only send the `SameSite=Lax` session cookie to the same
  site, and `localhost` and `127.0.0.1` are different sites.
- Django admin: `http://localhost:8000/cms-admin/` (`DJANGO_ADMIN_URL`).
- API root: `http://localhost:8000/api/v1/`.
- Tests: `.venv/bin/python manage.py test tests`. The same suite passes on
  SQLite and PostgreSQL. Set `DJANGO_DB_ENGINE` to run it on another
  engine.
- Emails go to the console until `DJANGO_EMAIL_HOST` is set.
- Before committing: `python scripts/check_public.py`. In the standalone
  repo it can run as a hook:
  `printf '#!/bin/sh\nexec python3 scripts/check_public.py\n' > .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit`.
  Mark a deliberate test string with the comment `check_public: ignore`.

(In the monorepo the virtualenv is `../backend-venv`, and the commands are
the same.)

`seed_site` loads only documented data: the four companies and the two
Foods lines, the six products, the five regions, and the six partners. The
partner logos come from `seed_assets/partner-logos/` (public marks; sources
in its `SOURCES.md`). `seed_posts` loads the six genuine posts from the old
site with their **true original dates** (2018-11-02 to 2020-01-09) and the
byline "Mumita Holdings". Their text comes from `seed_assets/posts.json`, a
snapshot of the frontend's `messages/en/blog.json` and
`src/lib/data/posts.ts`. `seed_posts --export-from ../frontend` rebuilds
the snapshot. The gallery is **not** seeded: the frontend's bundled
gallery stays its fallback, and the API gallery holds dashboard uploads
only. Both seeds are safe to re-run.

## Environment variables

`.env.example` lists **every** variable `config/settings.py` reads, with
placeholder values. A test fails if one is missing. Settings read the
process environment first, then an optional git-ignored `.env` next to
`manage.py`. When `DJANGO_DEBUG=0`, the process refuses to start without
`DJANGO_SECRET_KEY` and `DJANGO_ALLOWED_HOSTS`. `check --deploy` then warns
about any other missing platform setting.

| Variable | Default | Notes |
|---|---|---|
| `DJANGO_DEBUG` | `1` | `0` in production |
| `DJANGO_SECRET_KEY` | dev-only key | **required** in production |
| `DJANGO_ALLOWED_HOSTS` | localhost (dev) | **required**, e.g. `api.mumitaholdings.com` |
| `DJANGO_ADMIN_URL` | `cms-admin/` | unguessable in production; `admin/` is refused |
| `DJANGO_FRONTEND_URL` | `http://localhost:3111` (dev) | revalidation webhook, links in emails |
| `DJANGO_CORS_ALLOWED_ORIGINS` | `http://localhost:3000,http://localhost:3111` (dev) | the site origins; CORS with credentials; also trusted for CSRF |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | empty | extra CSRF origins (e.g. the API's own, for the Django admin) |
| `DJANGO_COOKIE_DOMAIN` | unset | `.mumitaholdings.com` in production: session + CSRF cookies shared with the site |
| `DJANGO_SITE_HOSTS` | `mumitaholdings.com` | hosts (and their subdomains) whose article links are internal |
| `REVALIDATE_KEY` | empty | sent as `X-Revalidate-Key` to `FRONTEND_URL/api/revalidate`; empty disables the webhook |
| `REVALIDATE_TIMEOUT` | `3` | seconds |
| `ANALYTICS_INGEST_KEY` | empty | required `X-Analytics-Key` for `analytics/hit/`; empty disables ingest |
| `DJANGO_NUM_PROXIES` | `0` | proxies **of our own hosting** that append to `X-Forwarded-For` (see Client IP) |
| `DJANGO_TRUSTED_PROXY_KEY` | empty | secret the frontend Worker sends as `X-Proxy-Key` |
| `DJANGO_TRUSTED_PROXIES` | empty | IPs/CIDRs whose forwarded IP is trusted |
| `DJANGO_TRUSTED_PROXY_HEADER` | `X-Forwarded-For` | header with the visitor IP from a trusted forwarder |
| `DJANGO_BEHIND_PROXY` | `0` | `1` to trust `X-Forwarded-Proto: https` (only if `api` is proxied by Cloudflare) |
| `DJANGO_SECURE_SSL_REDIRECT`, `DJANGO_HSTS_SECONDS`, `DJANGO_HSTS_INCLUDE_SUBDOMAINS`, `DJANGO_HSTS_PRELOAD` | `1`, `31536000`, `1`, `0` | when DEBUG is off |
| `DJANGO_DB_ENGINE` | `sqlite` (`postgresql` if only `DJANGO_DB_NAME` is set) | `mysql` on Namecheap |
| `DJANGO_DB_NAME`, `_USER`, `_PASSWORD`, `_HOST`, `_PORT`, `_CONN_MAX_AGE` | | MySQL port 3306, PostgreSQL 5432 |
| `DJANGO_SQLITE_PATH` | `db.sqlite3` | SQLite only |
| `DJANGO_MEDIA_ROOT`, `DJANGO_MEDIA_URL`, `DJANGO_STATIC_ROOT` | `media/`, `/media/`, `staticfiles/` | |
| `DJANGO_MEDIA_BASE_URL` | empty (request host) | absolute origin of media URLs, e.g. `https://api.mumitaholdings.com` |
| `DJANGO_SERVE_MEDIA` | `1` in dev, else `0` | Django serves `/media/` itself (only if Apache does not) |
| `IMAGE_UPLOAD_MAX_BYTES` | 15 MB | gallery and article uploads |
| `DJANGO_EMAIL_HOST`, `_PORT` (587), `_USER`, `_PASSWORD`, `_USE_TLS` (1) | console backend | SMTP in production |
| `DJANGO_DEFAULT_FROM_EMAIL` | `website@localhost` | sender of every email |
| `ENQUIRY_NOTIFY_EMAILS` | `info@localhost` (dev) | staff inbox for new enquiries |
| `ENQUIRY_RETENTION_DAYS` | `365` | purge after this |
| `ENQUIRY_THROTTLE_RATE`, `TESTIMONIAL_THROTTLE_RATE`, `LOGIN_THROTTLE_RATE` | `5/hour`, `3/hour`, `30/hour` | per client IP |
| `ENQUIRY_LOG_LEVEL` | `INFO` | |
| `ACCOUNT_EMAIL_DOMAIN` | `mumitaholdings.com` | new dashboard accounts must use it |
| `AXES_FAILURE_LIMIT` | `5` | failed sign-ins per email+IP before a 1-hour lock |

`check --deploy` leaves one warning, `security.W021` (HSTS preload off), on
purpose. Preload is very hard to undo.

## Client IP

Throttling, the axes lock-out and the stored IP hashes all use
`common.security.client_ip`. Nothing is trusted by default:

1. A request from a **trusted forwarder**, the frontend Worker, uses the
   first hop of `DJANGO_TRUSTED_PROXY_HEADER` (default `X-Forwarded-For`).
   A request counts as trusted only if it carries `X-Proxy-Key` equal to
   `DJANGO_TRUSTED_PROXY_KEY`, or if its `REMOTE_ADDR` is inside
   `DJANGO_TRUSTED_PROXIES`.
2. Otherwise, with `DJANGO_NUM_PROXIES=n`, the n-th address from the
   right of `X-Forwarded-For` (DRF semantics).
3. Otherwise `REMOTE_ADDR`.

On Namecheap with `api` **DNS-only** (the default in DEPLOY.md), Apache
sees the visitor directly, so leave `DJANGO_NUM_PROXIES=0`. A value above 0
would let anyone set their own IP with a forged header. The Worker sends
`X-Forwarded-For: <CF-Connecting-IP>` and `X-Proxy-Key`, set the key here.
If you later proxy `api` through Cloudflare, set `DJANGO_BEHIND_PROXY=1`
and `DJANGO_TRUSTED_PROXY_HEADER=CF-Connecting-IP`, and list Cloudflare's
published ranges in `DJANGO_TRUSTED_PROXIES`. To verify, the go-live
check is that enquiries sent from two networks get different `ip_hash`
values.

## API

Base `/api/v1/`. JSON only in production. The public list endpoints are
paginated (`?page=`, 20 per page, `{count, next, previous, results}`),
return **published rows only**, and carry `Cache-Control: public,
max-age=300`. For the locale, `?lang=fr`, else `Accept-Language`, else
English. `auth/`, `manage/` and `write/` are always English.

### Public

| Endpoint | Notes |
|---|---|
| `GET brands/`, `products/`, `services/`, `team/`, `partners/`, `regions/` | as before (filters: `?kind= ?parent= ?brand= ?category= ?department= ?tier=`) |
| `GET posts/`, `posts/{slug}/` | `{slug, title, dek, excerpt, lens, author, published_at, reading_minutes, cover, media_key}`, and the detail view adds `body_html, seo_title, seo_description`. `?lens=`, `?author=` (team slug). Future-dated posts are hidden |
| `GET gallery/`, `gallery/{id}/` | `{id, category, alt, caption, image}`, `?category=`. Dashboard uploads only |
| `GET testimonials/` | `{id, name, role_or_place, quote, photo: null}`, published only |
| `POST testimonials/submit/` | `{name, role_or_place, quote, consent: true, website: ""}`. Lands as `pending`. Consent required, honeypot, 3/hour, Origin check |
| `POST enquiries/` | see below |
| `POST analytics/hit/` | server-to-server: header `X-Analytics-Key`, `{path, referrer_host, country, device, is_bot}`, answers 204. Bots are dropped. It stores one daily aggregate row per date/path/country/referrer host/device, with no IP, cookie or user |

The image object is `{id, src, width, height, renditions: [{w, fmt, url}],
blur}`. Renditions are AVIF and WebP at 400/800/1200/1600/2400 px, never
wider than the source (a smaller source also gets its own width). `src` is
the largest WebP, and `blur` is a tiny WebP data URI. EXIF is stripped and
the original upload is not kept.

### Auth (sessions)

| Endpoint | |
|---|---|
| `GET auth/csrf/` | sets `csrftoken`; returns `{ok, csrfToken}` |
| `POST auth/login/` | `{email, password, realm: "admin"\|"publisher"}` returns `{user}`. Wrong password, unknown email, inactive account and wrong realm all get the same 400 `{detail}`. A lock-out gets 429 `{detail: "locked"}`. Every attempt is a `LoginEvent` |
| `POST auth/logout/` | |
| `GET auth/me/` | `{id, name, email, role, must_change_password}` or 401 |
| `POST auth/password/` | `{current, new}`: Django validators (12+ chars), clears `must_change_password`, keeps the session |

Cookies: `sessionid` (HttpOnly) and `csrftoken`, `SameSite=Lax`, `Secure`
in production, `Domain=DJANGO_COOKIE_DOMAIN`. The idle timeout is 8 h: the
expiry slides with each request. Send `credentials: "include"` and
`X-CSRFToken` on every unsafe request, login included. No session gives
401. The wrong role gives 403. `must_change_password` gives 403
`{detail: "password_change_required"}` on `manage/` and `write/`.

### Admin: `manage/` (group `admins`)

| Endpoint | |
|---|---|
| `GET manage/stats/?days=30` | logins, enquiries, posts, testimonials, visits (PLATFORM-CONTRACT) |
| `GET manage/login-events/` | `?realm= ?success=` |
| `GET manage/enquiries/`, `GET/PATCH manage/enquiries/{id}/`, `POST .../{id}/reply/` | `?source= ?status= ?type= ?q=`. Only `status` is editable. `reply` emails the enquirer (Reply-To: the admin) and stores an `EnquiryReply`. A phone contact gets 400 `{detail: "phone"}` |
| `GET/POST manage/gallery/`, `GET/PATCH/DELETE manage/gallery/{id}/`, `POST manage/gallery/reorder/` | multipart `image, category, alt, caption?, status?`. Categories: `farms training processing cold products events awards csr international prais`. jpg/png/webp/heic, 15 MB |
| `GET/POST manage/posts/`, `GET/PATCH/DELETE manage/posts/{id}/`, `POST .../approve/`, `POST .../reject/ {note}` | every post. Admins can also write and publish directly (`status`) |
| `GET/POST manage/testimonials/`, `PATCH/DELETE .../{id}/`, `POST .../approve/`, `.../reject/` | publishing needs `consent` |
| `GET/POST manage/users/`, `GET/PATCH manage/users/{id}/`, `POST .../reset-password/` | `{name, email, role, password?, generate}`. The email must end `@mumitaholdings.com`. Credentials are emailed (plain text + HTML). You cannot deactivate or demote yourself or the last active admin. No hard delete |
| `POST manage/uploads/` | inline article image returns an image object |

### Publisher: `write/` (groups `publishers` and `admins`, own posts only)

`GET/POST write/posts/`, `GET/PATCH/DELETE write/posts/{id}/`,
`POST write/posts/{id}/submit/`, `POST write/uploads/`. Other people's
posts return 404. Publishers cannot set `status`, and can only use a cover
image they uploaded themselves.

### Post workflow

```
draft ──submit──▶ pending_review ──approve──▶ published
                        │  ▲
                 reject │  │ submit
                        ▼  │
                 changes_requested
```

- Editing a **published** post through `write/` creates a `PostRevision`,
  and the live post stays up until an admin approves it. Approving copies
  the revision over the live post and keeps its original `published_at`.
  Rejecting one sends the note to the author by email.
- `submit/` emails every active admin.
- API responses show the *working copy* (the revision if there is one),
  with `has_live_version` and `has_pending_revision`.

Revalidation: after publish, unpublish, approve, a live edit or deleting a
live post, Django calls `POST {DJANGO_FRONTEND_URL}/api/revalidate` with
`X-Revalidate-Key` and `{paths: ["/blog", "/blog/<slug>", "/"]}`. After a
gallery change the paths are `["/gallery", "/"]`, and after a testimonial
change `["/"]`. The call is made after the commit, with a 3-second
timeout. A failure is logged and never fails the request.

### Article HTML

`body_html` is sanitized on save with nh3 to the contract's allow-list
(`p h2 h3 h4 strong em u s a ul ol li blockquote code pre hr img figure
figcaption table thead tbody tr th td br`):

- Scripts, styles, comments, event handlers and `style` attributes go.
  Other tags are unwrapped (their text is kept).
- Links keep `http(s)`, `mailto` and `tel` only. External links (not
  `DJANGO_SITE_HOSTS`) get `rel="noopener noreferrer"`.
- `<img>` survives only when its `src` is our uploads
  (`/media/uploads/...`, relative or on this API's host).
- `excerpt` falls back to the first ~200 characters of the text, and
  `reading_minutes` is words / 200, rounded up.

## The enquiry endpoint

```
POST /api/v1/enquiries/?lang=fr
{"name": "…", "contact": "email or phone", "type": "buy", "message": "…",
 "source": "product-quote", "topic": "Plantain Flour", "website": ""}
```

- **Four visitor fields**: `name`, `contact` (email, or phone with 7 to 15
  digits), `type` (`buy`, `farm`, `partner`, `other`) and `message`.
- The page sets `source` and `topic`; the visitor never types them. Both
  are optional.
  - `source` is one of `contact partners join-distributor join-strategic
    join-investor join-volunteer join-grant marketplace-register
    feasibility product-quote service-quote`.
  - `topic` is up to 120 characters.
- Any other key gets a 400. `website` is the honeypot: when it is filled,
  the API answers 201 and stores nothing.
- Responses: `201 {ok: true}`, `400 {field: [..]}`, `403` for a foreign
  `Origin`, `429` over 5 per hour per IP.
- Stored along with the enquiry: locale, `Referer`, and a keyed IP hash
  (never the IP). Staff are emailed at `ENQUIRY_NOTIFY_EMAILS`. The
  dashboard inbox statuses are `unread`, `read`, `replied` and `archived`.

## Deploying on Namecheap (cPanel)

The full go-live runbook, with DNS and the Worker, is `06-plan/DEPLOY.md`
§5. The backend side:

1. **MySQL**: cPanel → MySQL® Databases.
   - Create `<cpuser>_mumita_api` and a user with a 24+ character
     password, then grant ALL PRIVILEGES.
   - In phpMyAdmin, set the database collation to `utf8mb4_unicode_ci`.
   - Django connects with `charset=utf8mb4` and strict mode through PyMySQL,
     so no compiler is needed. MariaDB 10.6+ or MySQL 8.0.11+.
2. **Subdomain**: create `api.mumitaholdings.com` with the document root
   `/home/<cpuser>/api.mumitaholdings.com`, and run AutoSSL.
   `DJANGO_MEDIA_ROOT=/home/<cpuser>/api.mumitaholdings.com/media` puts
   uploads inside that document root, so Apache serves `/media/...`
   directly. Only if it doesn't, set `DJANGO_SERVE_MEDIA=1`.
3. **Code**: cPanel → Git™ Version Control → Create.
   - Clone `https://github.com/BertinAm/mumita-holdings-api.git` into
     `/home/<cpuser>/repositories/mumita-holdings-api`.
   - **Deploy HEAD Commit** runs `.cpanel.yml`. It rsyncs the code to the
     app root `~/mumita-api` (keeping `.env`, `media/`, `staticfiles/` and
     `tmp/`), then runs `pip install -r requirements.txt`,
     `migrate --noinput` and `collectstatic --noinput`, and touches
     `tmp/restart.txt`.
   - Edit `APPROOT`/`VENV` in `.cpanel.yml` if your paths differ.
4. **Python app**: cPanel → Setup Python App.
   - Python **3.12+**, application root `mumita-api`, URL
     `api.mumitaholdings.com`, startup file `passenger_wsgi.py`, entry
     point `application`.
5. **Environment**:
   - Enter the variables from `.env.example` in the app screen, **and**
     put the same values in `~/mumita-api/.env` (`chmod 600`). The deploy
     task and cron only see `.env`.
   - Values come from your password manager. `DJANGO_STATIC_ROOT` can
     stay the default (`~/mumita-api/staticfiles`); WhiteNoise serves it.
6. **First run** (in the app's virtualenv shell):
   - `python manage.py check --deploy`
   - `migrate`, then `seed_site` and `seed_posts`
   - `create_admin --email <name>@mumitaholdings.com --name "<Full Name>"`
     prints a generated password **once**. Sign in at
     `https://mumitaholdings.com/dashboard/login`, where you must change
     it.
   - `send_test_email you@example.com` checks SMTP.
7. **Cron**: cPanel → Cron Jobs:
   - daily: `15 3 * * * cd ~/mumita-api && ~/virtualenv/mumita-api/3.12/bin/python manage.py purge_enquiries`
   - every 5 minutes (publishes content changes to the static frontend by
     calling the Workers Builds deploy hook in `FRONTEND_DEPLOY_HOOK_URL`, once
     per burst of edits):
     `*/5 * * * * cd ~/mumita-api && ~/virtualenv/mumita-api/3.12/bin/python manage.py rebuild_frontend`
8. **Restart**: after changing environment variables, press Restart in
   Setup Python App (or `touch ~/mumita-api/tmp/restart.txt`).

Passenger may cap request bodies below 15 MB on some plans. If big uploads
fail with 413 before reaching Django, raise `LimitRequestBody` in the
subdomain's `.htaccess` (for example `LimitRequestBody 16777216`).

## Security baseline

- DEBUG off enables:
  - the SSL redirect and HSTS;
  - Secure session and CSRF cookies;
  - the deploy checks for the platform keys.
- Always on:
  - CSP for everything Django serves;
  - `X-Frame-Options: DENY`, nosniff, a strict referrer policy and COOP.
- The Django admin sits at `DJANGO_ADMIN_URL`, never `/admin/`.
- Not indexable: every response except `/media/` carries
  `X-Robots-Tag: noindex, nofollow, noarchive`, and `/robots.txt` disallows
  everything but `/media/` (`common/robots.py`). The frontend's `/dashboard`
  and `/write` apps have their own noindex header, meta tag and robots rule.
- Passwords need 12+ characters and Django's validators. Generated
  passwords have 24 characters.
- **django-axes** locks an email+IP pair for 1 hour after 5 failures. The
  API answers 429, and `manage.py axes_reset` clears the lock.
- Login CSRF is enforced.
- Uploads are re-encoded from pixels, so no active content or EXIF
  survives. Uploads are capped at 15 MB and 80 megapixels.
- Logs never contain enquiry content, contact details or passwords, only
  ids and types.
- Not done yet: 2FA for admin accounts (`django-otp`), and a shared cache
  for throttle counters when running more than one process.
