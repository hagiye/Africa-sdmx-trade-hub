# Production deployment

This project is packaged for one small Koyeb web service backed by hosted
PostgreSQL. The deployment must remain on resources explicitly labelled `$0` or
`Free` in the provider dashboard. Stop before creation if the account presents
any paid instance, upgrade, or metered fallback.

## Free-tier check

Verified against provider documentation on 2026-09-04:

- [Koyeb Free Instance](https://www.koyeb.com/docs/reference/instances) lists
  512 MB RAM, 0.1 vCPU, 2 GB SSD, one region, and scale-to-zero after one hour.
  It is available only in Frankfurt or Washington, D.C. and is not intended for
  business-critical production workloads.
- [Koyeb pricing FAQ](https://www.koyeb.com/docs/faqs/pricing) says each
  organization can use one free web service and that the free web service is
  not charged. Only select an instance whose dashboard label explicitly says
  `Free` and `$0`.
- [Neon pricing](https://neon.com/pricing) lists a `$0` Free plan with no credit
  card required, 0.5 GB storage per project, usage limits, and scale-to-zero.

These are current conditions, not a permanent free-forever guarantee. Check the
two dashboards again immediately before resource creation and after deployment.

## 1. Create or select the database

In Neon, select the **Free — $0** plan and create a small project/database. Do
not select Launch or Scale. Copy the pooled connection string and store it in a
local process environment variable temporarily; never write it into a tracked
file. Neon connection strings normally include `sslmode=require` and may also
include `channel_binding=require`.

The application accepts any of these SQLAlchemy-compatible forms:

```text
postgresql+psycopg://USER:PASSWORD@HOST/DATABASE?sslmode=require
postgresql://USER:PASSWORD@HOST/DATABASE?sslmode=require
postgres://USER:PASSWORD@HOST/DATABASE?sslmode=require
```

The last two are normalized to `postgresql+psycopg://` internally. URL-encode
special characters in credentials.

## 2. Apply migrations and bootstrap once

Use a trusted local shell with the production `DATABASE_URL` set only in the
process environment:

```powershell
$env:DATABASE_URL = "<NEON-POOLED-CONNECTION-STRING>"
$env:DATABASE_SSL_MODE = "require"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe scripts/bootstrap_demo_database.py
.\.venv\Scripts\python.exe scripts/bootstrap_demo_database.py
Remove-Item Env:DATABASE_URL
```

The first bootstrap deliberately repeats the controlled 2023 record inside its
in-memory fixture payload. This records one non-rejecting duplicate-quality
validation result while leaving the source and target warehouses at three
unique observations. The second bootstrap must report every count unchanged.
This is deliberately not an app startup command: no deployment replica runs
migrations or invokes an external statistical provider.

## 3. Push the reviewed branch

Before pushing:

```powershell
git status --short --ignored
git ls-files .env "*.sql" "*.dump"
python -m pytest -v
npm --prefix frontend test
npm --prefix frontend run build
docker build -t africa-sdmx-trade-hub .
git push origin main
```

The tracked-files check must print no secret `.env`, SQL dump, or database dump.

## 4. Create the Koyeb web service

In the Koyeb control panel:

1. Create App, choose **GitHub**, and authorize the repository
   `hagiye/Africa-sdmx-trade-hub`.
2. Select branch `main`, builder **Dockerfile**, Dockerfile path `Dockerfile`.
3. Choose service type **Web Service** and instance type **Free**. Confirm the
   displayed price is exactly `$0` before continuing.
4. Choose Frankfurt or Washington, D.C.; do not select a paid region or Eco,
   Standard, or GPU instance.
5. Expose HTTP port `8000`, route `/`, and keep one replica. The image reads the
   platform `PORT`; if the form requires a value, set `PORT=8000`.
6. Configure an HTTP `GET` health check on `/health` for port `8000`.
7. Add runtime variables:
   - `ENVIRONMENT=production`
   - `DATABASE_URL` from a Koyeb Secret, not plaintext source control
   - `DATABASE_SSL_MODE=require`
   - `SECRET_KEY` from a Koyeb Secret
   - `PORT=8000`
   - `DATABASE_POOL_SIZE=2`
   - `DATABASE_MAX_OVERFLOW=1`
   - leave `CORS_ALLOWED_ORIGINS` empty for same-origin access
8. Re-check **Free / $0**, then deploy. Do not override the Dockerfile command.

Koyeb's [Git deployment documentation](https://www.koyeb.com/docs/build-and-deploy/build-from-git)
confirms that a repository Dockerfile is built as a normal container image.
Its [health-check documentation](https://www.koyeb.com/docs/run-and-scale/health-checks)
defines a successful HTTP check as a `2xx` or `3xx` response.

## 5. Verify the public deployment

Run the automated check, then directly refresh every SPA route:

```powershell
python scripts/smoke_test_deployment.py https://<REAL-KOYEB-DOMAIN>
```

Verify `/`, `/explore`, `/metadata`, `/validation`, `/harmonization`,
`/architecture`, `/about`, `/docs`, `/redoc`, and `/health`. Confirm an unknown
`/api/v1/...` route is JSON `404`, while a frontend route refresh returns
`index.html`.

For the public security review, confirm:

- `/.env` and filesystem paths are not served
- database URLs, passwords, and secret values are absent from pages and logs
- malformed API requests do not reveal stack traces or raw database errors
- only intended read-only statistical endpoints are public
- security headers are present
- the service and database dashboards both still show the Free/$0 plan

Koyeb Free instances scale to zero after an hour of inactivity, so the first
request may wait for a cold start. After an idle period, allow up to 60 seconds,
then repeat the smoke test and record the observed wake-up behavior.

## 6. Publish real links

Only after all checks pass, replace README `<PUBLIC_URL>` placeholders with the
real Koyeb URL, commit with `feat: deploy public SDMX trade data portal`, push,
and verify the resulting deployment again.
