# Singularity Labs — Database

## Status

Phase 2A deliverable. Schema designed, migrations written, and
verified against a real local PostgreSQL 16 instance (2026-08-14,
session 9) — not just checked for SQL syntax. See
`docs/autonomous_state.md` "Session 9 Summary" for the exact
verification performed, and `tests/test_db_schema.py` for the
automated, reproducible version of that verification.

**No ORM or migration-management tool has been chosen yet.** These are
plain, sequentially-numbered `.sql` files, deliberately, because the
backend framework decision (Phase 2B) will determine whether that's
Alembic (if SQLAlchemy), a framework-native tool, or something else —
picking one now would be guessing ahead of that decision. These files
are written to be trivially adoptable by any of those tools later
(each is a single forward-only migration; none require environment-
specific templating).

## Design principles

1. **Observed vs. derived data are separate tables.** `outcome_records`
   contains only what was actually reported by the source. Classifier
   output (`endpoint`, `subtype`, `confident`, `reason`) lives in
   `endpoint_classifications`, a separate, versioned table — never
   mixed into the same row as observed data. This directly implements
   the distinction `docs/architecture.md` and `Claude.md` §7 require.
2. **Classifications are versioned and immutable, not overwritten.**
   Every row in `endpoint_classifications` carries a
   `classifier_version` (see `singularity.endpoints.CLASSIFIER_VERSION`).
   Re-running the classifier after a future fix adds a new row rather
   than silently replacing history — the `latest_endpoint_classifications`
   view gives you "current" without losing that history.
3. **Provenance is preserved on every table**, mirroring
   `singularity.schema.Provenance` exactly (source, source record id,
   retrieval timestamp, request URL, query params, raw source data).
4. **Dates are stored as `TEXT`, not `DATE`, deliberately.** A real
   ClinicalTrials.gov date may be partial (e.g. `"2025-01"`, no day).
   Parsing/normalizing that is a data transformation and must be an
   explicit, separate, documented step, per `Claude.md` §5 ("never
   silently transform clinical measurements... every transformation
   must be explicit and reproducible") — not baked silently into a
   column type that would truncate or reject partial dates.
5. **No artificial uniqueness on `outcome_records`.** Real
   ClinicalTrials.gov data contains genuine duplicate rows (confirmed
   in earlier sessions' real-data validation, and already handled by
   `singularity.ingest`'s duplicate-detection-not-removal design). The
   schema uses a surrogate `BIGSERIAL` key rather than a natural key
   that would reject or silently collapse legitimate duplicates.
6. **A `CHECK` constraint on `endpoint`** catches an invalid canonical
   endpoint value (e.g. a future typo) at write time rather than
   silently persisting it — verified to actually reject bad data in
   `tests/test_db_schema.py`.

## Field-verification caveat (important, disclosed not hidden)

Only `protocolSection.identificationModule.nctId` and
`protocolSection.outcomesModule` have been independently verified
against a live ClinicalTrials.gov API v2 response in this project. The
other `protocolSection` fields this schema's `trials` table maps
(`statusModule`, `designModule`, `sponsorCollaboratorsModule`,
`conditionsModule`, `armsInterventionsModule`) are based on the
publicly documented API v2 schema, but were not re-verified against a
fresh live response in the session that designed this schema (web-
fetch tooling was unavailable that session — see
`docs/autonomous_state.md` "Session 9 Summary"). Spot-check these
field paths against a real API response before trusting them at scale
in Phase 2B.

## Running migrations locally

```bash
createdb singularity_labs
for f in db/migrations/*.sql; do psql -d singularity_labs -f "$f"; done
```

## Running the schema tests

Requires a locally reachable PostgreSQL instance and the optional `db`
dependency group:

```bash
pip install -e ".[db]"
# defaults to postgresql://postgres:testpass@localhost:5432/postgres;
# override with SINGULARITY_TEST_ADMIN_DSN if needed
pytest tests/test_db_schema.py -v
```

If no PostgreSQL instance is reachable, these tests **skip** (not
fail) — this is intentional so the rest of the suite stays green in
any environment, including this project's own sandboxed development
environment, which has no persistent database.

## Schema overview

| Table | Purpose | Mirrors |
|---|---|---|
| `trials` | Protocol-level trial metadata | `singularity.schema.Trial` |
| `outcome_records` | Raw, observed outcome measurements | `singularity.schema.OutcomeRecord` |
| `endpoint_classifications` | Versioned, derived classifier output | `singularity.schema.ClassificationResult` |
| `latest_endpoint_classifications` (view) | Most recent classification per outcome record | — |

`outcome_records.nct_id` is a foreign key to `trials.nct_id` —
ingestion code must upsert the trial before its outcome records.
`endpoint_classifications.outcome_record_id` is a foreign key to
`outcome_records.id` with `ON DELETE CASCADE`.
