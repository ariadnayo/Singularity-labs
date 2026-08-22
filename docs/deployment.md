# Deployment

**Status: not yet deployed or tested against a live deployment.**
Everything below has been tested locally (real local PostgreSQL, real
FastAPI app, 109/109 tests passing) but **not** against an actual
Render deployment -- see `docs/autonomous_state.md` "Session 15
Summary" for the exact verified-vs-not boundary. Do not treat this as
a production-readiness claim.

## Recommended stack: Render

One platform, one committed blueprint (`render.yaml`), no extra
infrastructure to stitch together:

- **Managed PostgreSQL** (Render Postgres) for `trials`/
  `outcome_records`/`endpoint_classifications`.
- **One web service** running the existing FastAPI app via `uvicorn`
  -- no ORM, no GraphQL, no background-job system, no auth. Matches
  the codebase exactly as it exists today.
- **Ingestion stays manual** -- `scripts/run_clinicaltrials_ingestion.py`,
  run by a human against the deployed database's connection string,
  exactly as it already works locally. (Render's optional Cron Jobs
  feature could automate this later without needing a separate
  background-job system -- not enabled now, deliberately, per the
  explicit "no unnecessary infrastructure" scope.)

Why Render specifically, as the one concrete recommendation: it hosts
both the database and the web service under one dashboard/one
blueprint, has a free tier sufficient for an MVP, and needs no
additional services (no separate secrets manager, no separate cron
system) for anything this codebase currently does.

## First-time setup

1. **Apply the blueprint.** In the Render dashboard: New -> Blueprint ->
   point at this repo -> Render reads `render.yaml` and provisions both
   the database and the web service. `SINGULARITY_DATABASE_URL` is
   wired automatically from the database to the web service -- you
   never type or commit that connection string anywhere.

2. **Run migrations against the deployed database.** From your local
   machine (or Colab, same as previous sessions), using the *external*
   connection string Render shows in the database's dashboard page:
   ```bash
   export SINGULARITY_DATABASE_URL="<Render external connection string>"
   for f in db/migrations/*.sql; do
     psql "$SINGULARITY_DATABASE_URL" -f "$f"
   done
   ```
   Not automated by the blueprint, deliberately -- matches how
   migrations have always been run in this project (see `db/README.md`).

3. **Verify the deployed API is actually up:**
   ```bash
   curl https://<your-service>.onrender.com/health
   # {"status": "ok", "database": "connected"}
   ```
   If `"database"` says `"not_configured"` or `"unreachable"` instead
   of `"connected"`, something is wrong with step 1 or 2 -- this
   endpoint is specifically designed to make that diagnosis immediate
   rather than requiring you to dig through logs (see
   `singularity.api.main.health`'s docstring).

4. **Run ingestion against the deployed database** (once, to populate
   it with real data -- or point it at your existing Colab-ingested
   data if you're migrating that database to Render instead of
   starting fresh):
   ```bash
   export SINGULARITY_DATABASE_URL="<Render external connection string>"
   python3 scripts/run_clinicaltrials_ingestion.py --condition "cancer" --status COMPLETED --has-results --page-size 10 --max-pages 1
   ```

5. **Set CORS for the real frontend origin, once it exists.** In the
   Render dashboard, set the `SINGULARITY_CORS_ORIGINS` environment
   variable to your deployed frontend's real URL (comma-separated if
   more than one, e.g. a Vercel preview URL plus the production
   domain). Until then, the API defaults to `localhost:3000`/`5173`
   only -- a deployed frontend calling the deployed API will be
   blocked by CORS until this is set, by design (fails closed, not
   open).

## Environment variables

| Variable | Required | Set by |
|---|---|---|
| `SINGULARITY_DATABASE_URL` | Yes (or `DATABASE_URL` as a fallback -- see `singularity.db.get_connection`) | Render, automatically, via the blueprint's `fromDatabase` binding |
| `SINGULARITY_CORS_ORIGINS` | No (defaults to localhost dev origins) | You, manually, once a real frontend origin exists |

**No secrets are committed to this repository.** `render.yaml`
contains no credentials -- the database connection string is resolved
by Render at deploy time via the `fromDatabase` reference, never
written to a file. Verify: `git grep -i "postgresql://" -- ':!tests' ':!*.md'`
should return nothing outside test files (test files use a
local-only, non-secret default, `testpass`, documented as such in
`db/README.md`).

## API documentation

Once running (locally or deployed), interactive OpenAPI docs are
available at `/docs` (Swagger UI) and `/redoc` (ReDoc), auto-generated
by FastAPI from the Pydantic response models in `singularity.api.models`
-- no separate documentation to maintain.

## Closing the remaining `Trial` field-verification gap

Not part of deployment itself, but relevant before trusting `Trial`
data at scale: `docs/autonomous_state.md` "Session 15 Summary"
documents the exact small Colab query needed to check whether
`official_title`/`interventions`/`start_date`/`completion_date`/
`enrollment_count` are being extracted correctly from real
ClinicalTrials.gov responses. This was requested but not resolved this
session -- pending that query's output.
