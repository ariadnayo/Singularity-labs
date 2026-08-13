# data/

No dataset is currently checked into this repository.

`docs/autonomous_state.md` references a working dataset (5,165 rows,
801 classified across PFS/OS/ORR/DOR/DFS, 4,364 unclassified) that was
used to establish the current endpoint-classification priorities, but
that dataset is not present in this repo and must not be fabricated
or reconstructed from memory.

## Expected format

Per `docs/data_dictionary.md`, raw outcome records are expected to have
at minimum:

| column     | type          | notes                                   |
|------------|---------------|------------------------------------------|
| nct_id     | string        | ClinicalTrials.gov identifier             |
| title      | string        | full outcome measure title                |
| parameter  | string        | e.g. MEDIAN, MEAN, NUMBER, COUNT_OF_...    |
| unit       | string        | e.g. months, percentage of participants    |
| timeframe  | string        | assessment period                          |
| group      | string        | treatment arm / cohort                     |
| value      | float         | reported value                             |

`src/singularity/schema.py` defines `OutcomeRecord` matching this shape.

## Loading data

`src/singularity/ingest.py` implements `load_records_from_csv(path)`,
which parses a CSV at that path into `OutcomeRecord` instances plus a
`ValidationReport` (row counts, missing-field rows, malformed values,
duplicates, unexpected columns).

`src/singularity/audit.py` implements `run_audit(csv_path)`, which runs
ingestion + `singularity.endpoints.classify_batch` +
`singularity.endpoints.summarize` end-to-end and returns an
`AuditReport` (with `.to_markdown()`).

**As of this writing, no real dataset file exists anywhere in this
repository or in any location available to the ingesting agent.** To
run the pipeline against real data, one of the following is required:

1. Add a real CSV file to `data/` (e.g. `data/outcomes.csv`) matching
   the column schema above, sourced from an actual clinical-trial data
   provider (e.g. an export from ClinicalTrials.gov's structured
   results). The provenance of the file should be documented alongside
   it (source, export date, query used).
2. Or, if the data is meant to come from a live API rather than a
   static export, specify: the API/endpoint, authentication method,
   and the exact query or filter used to produce the 5,165-row dataset
   referenced in earlier `docs/autonomous_state.md` notes. No such API
   integration exists in this codebase yet -- it would need to be
   built as a separate ingestion path once the source is known.

Until one of these is provided, `run_audit()` will correctly raise
`FileNotFoundError` rather than fall back to synthetic or previously
reported numbers.
