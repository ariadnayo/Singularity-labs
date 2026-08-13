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

Once a real dataset is added here (e.g. `data/outcomes.csv`), it should
be loaded into `OutcomeRecord` instances and passed to
`singularity.endpoints.classify_batch`. No loader is implemented yet
since there is no real file to load and target against -- adding one
against a fabricated CSV would violate the data-integrity rules in
`Claude.md` section 5.
