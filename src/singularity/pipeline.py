"""
End-to-end ingestion orchestration:

    ClinicalTrials.gov
          v
    ClinicalTrialsAdapter.iter_studies()
          v
    extract_trial() / extract_outcome_records_verbose()
          v
    classify_outcome()
          v
    db.upsert_trial() / db.replace_outcome_records_for_trial() / db.insert_classifications()
          v
    PostgreSQL (auditable, versioned)

IDEMPOTENCY / RE-RUN DESIGN (read this before changing anything):

db/README.md documents a deliberate choice: `outcome_records` has NO
natural-key uniqueness constraint, because real ClinicalTrials.gov
data contains genuine duplicate rows that must be preserved (see
db/migrations/0002_create_outcome_records.sql). That means a plain
"insert if not present" idempotency check is not possible for
outcome_records -- there is no reliable way to tell "this is the same
row as last time" from "this is a second, genuinely distinct duplicate
row" without a natural key.

This pipeline resolves that with a **delete-then-insert-per-trial**
strategy (`db.replace_outcome_records_for_trial`): every ingestion run
for a given nct_id deletes that trial's existing outcome_records and
inserts a fresh set. This makes re-running ingestion for the same
trial idempotent in the sense that matters (same input -> same final
DB state), at the cost of losing row-level classification history
across re-ingestion runs (old endpoint_classifications for the deleted
rows cascade-delete automatically). This is a standard, defensible ETL
pattern given the schema's own no-natural-key decision, but it IS a
design choice, not a mechanically forced one -- flagged explicitly in
docs/autonomous_state.md "Session 10 Summary" for human review, in
case append-only/content-hash-based row stability was actually wanted
instead.

FAILURE HANDLING:

- Network/HTTP failures while fetching from ClinicalTrials.gov are NOT
  caught here -- they propagate immediately and abort the run. This
  matches the existing "fail loudly on infrastructure problems, don't
  guess" principle already established in
  singularity.sources.clinicaltrials.fetch_studies_page and
  singularity.ingest.
- Malformed DATA for a single study (e.g. an unexpected null where a
  list was expected in the raw JSON, or a DB constraint violation for
  one trial) IS caught, per-study, and reported in the returned
  IngestionReport rather than aborting the whole run -- other studies
  in the same batch still get ingested. This is what makes "Add tests
  for partial failures" meaningful: a batch of N studies where one is
  malformed should still ingest N-1 of them.
- Nothing here ever fabricates a value to paper over a failure. A
  failed study is reported as failed, not silently skipped or guessed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import db as _db
from .endpoints import CLASSIFIER_VERSION, classify_outcome
from .sources.clinicaltrials import ClinicalTrialsAdapter, extract_outcome_records_verbose, extract_trial


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class IngestionReport:
    """Summary of one ingestion run. Every count here is a real,
    directly-measured count from this run -- nothing is estimated.
    """

    query_params: dict
    started_at: str
    finished_at: "str | None" = None

    studies_fetched: int = 0
    studies_skipped_no_nct_id: int = 0

    trials_upserted: int = 0

    outcome_records_inserted: int = 0
    outcome_records_skipped_malformed: int = 0
    skipped_outcome_details: list = field(default_factory=list)

    classifications_inserted: int = 0

    # Studies where per-study processing raised an exception (malformed
    # data, a DB constraint violation for that one trial, etc.) --
    # caught, rolled back for that trial only, and reported here. The
    # run continues with the next study.
    failed_studies: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "query_params": self.query_params,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "studies_fetched": self.studies_fetched,
            "studies_skipped_no_nct_id": self.studies_skipped_no_nct_id,
            "trials_upserted": self.trials_upserted,
            "outcome_records_inserted": self.outcome_records_inserted,
            "outcome_records_skipped_malformed": self.outcome_records_skipped_malformed,
            "skipped_outcome_details": self.skipped_outcome_details,
            "classifications_inserted": self.classifications_inserted,
            "failed_studies": self.failed_studies,
        }

    def to_markdown(self) -> str:
        lines = [
            f"# Ingestion Report",
            "",
            f"Query: `{self.query_params}`",
            f"Started: {self.started_at}  Finished: {self.finished_at}",
            "",
            f"- Studies fetched: {self.studies_fetched}",
            f"- Studies skipped (no NCT ID): {self.studies_skipped_no_nct_id}",
            f"- Trials upserted: {self.trials_upserted}",
            f"- Outcome records inserted: {self.outcome_records_inserted}",
            f"- Outcome records skipped (malformed): {self.outcome_records_skipped_malformed}",
            f"- Classifications inserted: {self.classifications_inserted}",
            f"- Studies that failed processing: {len(self.failed_studies)}",
        ]
        if self.failed_studies:
            lines.append("")
            lines.append("## Failed studies")
            for f in self.failed_studies:
                lines.append(f"- `{f.get('nct_id')}`: {f.get('error')}")
        if self.skipped_outcome_details:
            lines.append("")
            lines.append("## Skipped outcome measures (malformed)")
            for s in self.skipped_outcome_details[:50]:
                lines.append(f"- `{s.get('nct_id')}`: {s.get('reason')}")
            if len(self.skipped_outcome_details) > 50:
                lines.append(f"- ... and {len(self.skipped_outcome_details) - 50} more")
        return "\n".join(lines)


def run_clinicaltrials_ingestion(
    conn,
    adapter: "ClinicalTrialsAdapter | None" = None,
    *,
    query_cond: "str | None" = None,
    query_term: "str | None" = None,
    filter_overall_status: "list[str] | None" = None,
    filter_ids: "list[str] | None" = None,
    filter_advanced: "str | None" = None,
    page_size: int = 50,
    max_pages: "int | None" = None,
    classifier_version: str = CLASSIFIER_VERSION,
) -> IngestionReport:
    """Run the full ClinicalTrials.gov -> normalize -> classify ->
    PostgreSQL pipeline for studies matching the given query.

    `conn` is an already-open PostgreSQL connection (see
    `singularity.db.get_connection`) -- this function does not open or
    close it, so the caller controls the connection's lifecycle (and
    can inject a test connection against a scratch database).

    `adapter` defaults to a real `ClinicalTrialsAdapter()` (real HTTP)
    if not provided -- pass one constructed with a mock `http_get` for
    tests, exactly as the rest of this project's adapter tests already
    do.

    Raises immediately (does not catch) on network/HTTP failures while
    fetching -- see the module docstring's "FAILURE HANDLING" section.
    Per-study data/DB failures are caught, reported, and do not abort
    the run.
    """
    if adapter is None:
        adapter = ClinicalTrialsAdapter()

    query_params = {
        "query_cond": query_cond,
        "query_term": query_term,
        "filter_overall_status": filter_overall_status,
        "filter_ids": filter_ids,
        "filter_advanced": filter_advanced,
        "page_size": page_size,
        "max_pages": max_pages,
    }
    report = IngestionReport(query_params=query_params, started_at=_now_iso())

    # Network/HTTP failures here are NOT caught -- they propagate and
    # abort the run, per this module's stated failure-handling policy.
    for study in adapter.iter_studies(
        query_cond=query_cond,
        query_term=query_term,
        filter_overall_status=filter_overall_status,
        filter_ids=filter_ids,
        filter_advanced=filter_advanced,
        page_size=page_size,
        max_pages=max_pages,
    ):
        report.studies_fetched += 1

        try:
            trial = extract_trial(study)
            if trial is None:
                report.studies_skipped_no_nct_id += 1
                continue

            records, skipped = extract_outcome_records_verbose(study)
            report.outcome_records_skipped_malformed += len(skipped)
            report.skipped_outcome_details.extend(skipped)

            _db.upsert_trial(conn, trial)
            report.trials_upserted += 1

            outcome_ids = _db.replace_outcome_records_for_trial(conn, trial.nct_id, records)
            report.outcome_records_inserted += len(outcome_ids)

            results = [classify_outcome(rec) for rec in records]
            _db.insert_classifications(conn, outcome_ids, results, classifier_version)
            report.classifications_inserted += len(results)

            conn.commit()
        except Exception as e:  # noqa: BLE001 -- intentionally broad: any per-study
            # failure (malformed JSON causing a Python-level error, a DB
            # constraint violation, etc.) must not abort the whole run.
            # See module docstring "FAILURE HANDLING".
            conn.rollback()
            nct_id = None
            try:
                nct_id = study.get("protocolSection", {}).get("identificationModule", {}).get("nctId")
            except Exception:  # noqa: BLE001 -- best-effort only, for the report
                pass
            report.failed_studies.append({"nct_id": nct_id, "error": f"{type(e).__name__}: {e}"})

    report.finished_at = _now_iso()
    return report
