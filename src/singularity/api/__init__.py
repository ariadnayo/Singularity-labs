"""
Read-only FastAPI layer over the PostgreSQL schema in db/migrations/.

This is the data layer for the eventual user-facing website -- kept
deliberately small: no auth, no write/ingestion endpoints (ingestion
stays a human-run script, scripts/run_clinicaltrials_ingestion.py, per
the Phase 2B scope decision), no background jobs, no GraphQL. See
docs/architecture.md "API Layer" for the full rationale.
"""
