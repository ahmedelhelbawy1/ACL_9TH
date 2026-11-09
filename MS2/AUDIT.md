# Milestone 2 — Final audit report

Audit date: November 9, 2026. Repository: `ahmedelhelbawy1/ACL_9TH`.
The original five-page `Milestone 2 Description.pdf` was available and read in full.
This audit inspected the existing implementation; it did not replace the project.

## A. Overall readiness

**PARTIAL — all technical requirements are verified; publishing the audit fixes is blocked.**

There are **no failed or blocked execution tests**: 47 tests passed, with zero failures
and zero skips. The remaining incomplete requirement is pushing the new audit commits
from this agent session. This publication blocker must not be confused with an
unverified graph or query. The original implementation commit is already on GitHub.

## B. Requirements checklist

| Requirement | Status | Evidence |
|---|---|---|
| All nine CSV files loaded | PASS | All required filenames, exact row counts and SHA-256 checksums verified. |
| Correct node schema | PASS | Independent schema transcribed from PDF; every imported node compared with its raw CSV row. |
| Correct property types | PASS | 384,426 present properties individually checked, including native Neo4j Date values. |
| Correct relationships | PASS | All 11 patterns and every source/target ID compared with CSV foreign keys. |
| 51,113 nodes | PASS | Actual Cypher count after each complete standalone import. |
| 163,510 relationships | PASS | Actual Cypher count after each complete standalone import. |
| Missing values handled | PASS | Absent optional fields checked against CSVs; empty q2/q3 and valid zeros covered by fixtures. |
| No duplicate nodes | PASS | Independent key checks and all nine uniqueness constraints, including a naming-collision regression. |
| No duplicate relationships | PASS | Exact endpoint multiplicities match the CSVs; deliberate duplicates detected. |
| Rerunning is safe | PASS | Two complete standalone runs plus existing integration reruns; counts and values unchanged. |
| Config.txt compatible | PASS | Authenticated custom database; shuffled keys; runs both with and without DATABASE. |
| Query 1 correct | PASS | 21 rows; full reference comparison, exact columns and sorting. |
| Query 2 correct | PASS | 11 rows; full reference comparison, exact columns and sorting. |
| Query 3 correct | PASS | 1 row; 100 shared Mercedes races, 75 Hamilton ahead, 25 Bottas ahead. |
| Query 4 correct | PASS | 106 rows; distinct starts, all eligible shared-drive results, exact sorting. |
| Query 5 correct | PASS | 1 row; count 6 and exact ordered names checked, including tie/rename fixtures. |
| Autograder formatting correct | PASS | UTF-8 file, exactly five numbered sections; executable queries and exact aliases. |
| Three submission files prepared | PASS | Create_kg.py, local config.txt and queries.txt exist together in MS2/. |
| GitHub changes pushed | BLOCKED | Original implementation is published; this session cannot authenticate to push audit fixes. |

Additional inspection: the importer uses `Path(__file__)`, standard CSV parsing,
parameterized `UNWIND`, stable-key `MERGE`, retryable write transactions and context
managers. Parents precede fact nodes. All five excluded tables are absent. The
standalone bundle contained only `Create_kg.py`, the CSVs and `config.txt`; it needed
no other project modules, notebook, interactive input or machine-specific path.
The installed dependency is the official Neo4j Python driver 5.28.8.

All tracked Python, Cypher, configuration examples, Compose settings, tests and
Markdown documentation were inspected. The local config was parsed without exposing
its password. Token/private-key pattern checks found no credentials in tracked files;
actual config, CSVs and virtual environments remain ignored.

## C. Actual database results

The strict audit used an authenticated disposable Neo4j 5.26.32 server with a custom
user database named `ms2audit`. The existing full-data development graph was also
rechecked. No unrelated existing database was deleted or reset.

| Label | First import | Second import |
|---|---:|---:|
| Driver | 861 | 861 |
| Constructor | 212 | 212 |
| Circuit | 77 | 77 |
| Season | 75 | 75 |
| Status | 139 | 139 |
| Race | 1,125 | 1,125 |
| Result | 26,759 | 26,759 |
| Qualifying | 10,494 | 10,494 |
| PitStop | 11,371 | 11,371 |
| **Total nodes** | **51,113** | **51,113** |

| Relationship pattern | First import | Second import |
|---|---:|---:|
| `Race-[AT_CIRCUIT]->Circuit` | 1,125 | 1,125 |
| `Race-[IN_SEASON]->Season` | 1,125 | 1,125 |
| `Result-[FOR_RACE]->Race` | 26,759 | 26,759 |
| `Result-[BY_DRIVER]->Driver` | 26,759 | 26,759 |
| `Result-[FOR_CONSTRUCTOR]->Constructor` | 26,759 | 26,759 |
| `Result-[HAS_STATUS]->Status` | 26,759 | 26,759 |
| `Qualifying-[FOR_RACE]->Race` | 10,494 | 10,494 |
| `Qualifying-[BY_DRIVER]->Driver` | 10,494 | 10,494 |
| `Qualifying-[FOR_CONSTRUCTOR]->Constructor` | 10,494 | 10,494 |
| `PitStop-[FOR_RACE]->Race` | 11,371 | 11,371 |
| `PitStop-[BY_DRIVER]->Driver` | 11,371 | 11,371 |
| **Total relationships** | **163,510** | **163,510** |

- Standalone import 1: without `DATABASE`; exit code 0; 7.290 seconds.
- Standalone import 2: with `DATABASE`; exit code 0; 4.627 seconds.

Each count above came from a real Cypher count query. Independent checks also
verified all endpoint mappings and all 384,426 present property values/types, not
just aggregate totals. Missing properties were checked against the source rows.
Deliberate bad-type, duplicate, missing-edge and reversed-edge fixtures were detected.
All nine required uniqueness constraints exist despite an unrelated naming collision.

## D. Query verification

All five queries executed successfully. Their full returned rows, columns, filtering,
aggregations and ordering matched independent raw-CSV reference calculations.

### Query 1 — PASS

- Execution: successful.
- Columns: `Driver`, `Points`, `Wins`.
- Returned rows: **21**.
- Sample result:

```json
{
  "Driver": "Max Verstappen",
  "Points": 388.5,
  "Wins": 10
}
```

### Query 2 — PASS

- Execution: successful.
- Columns: `Constructor`, `Entries`, `Classified`, `Reliability`.
- Returned rows: **11**.
- Sample result:

```json
{
  "Constructor": "Mercedes",
  "Entries": 320,
  "Classified": 298,
  "Reliability": 0.93125
}
```

### Query 3 — PASS

- Execution: successful.
- Columns: `Constructor`, `Shared_Races`, `Hamilton_Ahead`, `Bottas_Ahead`.
- Returned rows: **1**.
- Sample result:

```json
{
  "Constructor": "Mercedes",
  "Shared_Races": 100,
  "Hamilton_Ahead": 75,
  "Bottas_Ahead": 25
}
```

### Query 4 — PASS

- Execution: successful.
- Columns: `Driver`, `Starts`, `Avg_Finish`, `Wins`.
- Returned rows: **106**.
- Sample result:

```json
{
  "Driver": "Ayrton Senna",
  "Starts": 10,
  "Avg_Finish": 3.8,
  "Wins": 6
}
```

### Query 5 — PASS

- Execution: successful.
- Columns: `Drivers_Changed`, `Drivers`.
- Returned rows: **1**.
- Sample result:

```json
{
  "Drivers_Changed": 6,
  "Drivers": [
    "Carlos Sainz",
    "Daniel Ricciardo",
    "Esteban Ocon",
    "Lance Stroll",
    "Sebastian Vettel",
    "Sergio Pérez"
  ]
}
```

Query 1 uses Grand Prix points only; its totals intentionally exclude sprint points.
Query 2 returns ratios, not percentages. Query 3 counts shared races once and compares
`positionOrder`. Query 4 filters out exactly the three statuses in the PDF, counts
starts by distinct race, and retains eligible shared-drive results for averages/wins.
Query 5 compares constructor IDs, resolves ties using the smaller ID and excludes
drivers absent from either season. Its complete six-name list is shown above.
Synthetic tests also checked no matches, same-name drivers, tied primary constructors,
renamed teams with identical names, missing qualifying values and shared drives.

## E. Problems found and fixes applied

| Finding | Affected file | Fix | Verification |
|---|---|---|---|
| A pre-existing unrelated constraint with a reserved importer name silently suppressed the required Driver uniqueness constraint. | `Create_kg.py` | Removed fixed constraint names; Neo4j now matches uniqueness by label/property schema. | Reproduced the failure on the original code; fixed code has all nine constraints and preserves the unrelated constraint. |
| Query-reference comparison used `zip()` without verifying the number of result sets, so a missing final query could escape that helper's comparison. | `tests/test_integration.py` | Assert equal result-set counts before comparing every row. | Added a missing-result-set regression; it passes with the fix. |
| Earlier tests did not exercise a real authenticated custom database through the standalone entry point, and schema verification reused importer definitions. | `tests/test_audit.py` | Added independent PDF-schema checks and isolated full CLI imports with/without DATABASE from an unrelated working directory. | All eight standalone audit tests passed; wrong credentials and wrong database were rejected. |
| CSV edge-case coverage did not explicitly include quoted fields, malformed quotes and duplicate headers. | `tests/test_unit.py` | Added targeted regression cases, including BOM-encoded input. | All cases passed. |

No changes to the five Cypher queries were necessary during this audit. Existing
correct behavior was retained. Documentation now explains the strict audit setup and
separates the original 35-test record from this new 47-test run.

The notebook's content is unchanged; its original and current Git blob hash is
`4cab5b5418117c7a0ab5b5361db688021c7ce21f`.

## F. Blockers

**GitHub publication only:** the attempted push failed with:

```text
fatal: could not read Username for 'https://github.com': Device not configured
```

This session has no usable Git authentication. The previously attempted GitHub
connector also denied repository writes. Do not put tokens in source files or chat.
Use the already authenticated terminal to run the push command in section G.

No required technical test was blocked. University private grading queries were not
available and are not claimed as tested. All supplied specification checks passed;
this is not a guarantee about undisclosed grading infrastructure. Aura and clustered
Neo4j deployments were outside the tested environment.

## G. GitHub status

- Branch: `feature/milestone-2-knowledge-graph`.
- Audited published implementation: `58fce93d010e14b8d1e9ff3bf43486d48bb6c444`.
- Verified fix/test commit: `bc3d73696f8042d3b98361bb8922a7901b04156c`.
- Report commit: the commit containing this file; inspect with `git log -1 --format=%H`.
- Push status at report creation: **BLOCKED** by agent-session authentication.
- Pull request: none created or requested. No force-push, branch deletion or merge.
- `main` remains at `c5a8b75bc6b2a025ab9e4209bb4b463887ae7da1`.

From the existing `ACL_9TH` checkout:

```bash
git push -u origin feature/milestone-2-knowledge-graph
```

After it succeeds, verify that the remote branch points to the local HEAD. This
report records the audit-time status; a subsequent successful push resolves the
publication blocker without requiring another implementation change.

## H. Final submission readiness

1. **Is Create_kg.py ready? Yes.** The fixed script completed both standalone imports
   and passed independent schema, value, type, relationship and idempotency checks.
2. **Is config.txt correctly prepared? Yes, for the local test server.** It exists
   beside the script and is ignored in Git. Both authenticated grading configurations
   were tested separately. A different server requires its own URI/credentials and,
   optionally, DATABASE; no Python changes are needed.
3. **Is queries.txt ready? Yes.** UTF-8, exact headers/order/aliases, all five results verified.
4. **Does the graph meet the required counts? Yes.** 51,113 nodes and 163,510 relationships
   after both standalone imports.
5. **Do all five queries return correct results? Yes**, against independent calculations
   and the stated edge cases.
6. **Can the university autograder run it without code changes? Yes, for the documented
   specification.** Supply its CSVs/config beside the script, install the driver, and
   execute `python Create_kg.py` with Python 3.11+ and a compatible Neo4j server.
7. **Is anything still required from the student?** Push the audit commits using the
   authenticated terminal. Keep local config.txt with the three required artifacts;
   GitHub deliberately contains config.example.txt instead of real credentials. Any
   eventual university submission is separate and was not performed.

## Evidence files and reproduction

- `verification/audit_tests.txt`: all 47 passing tests, zero skipped.
- `verification/audit_database.json`: actual first/second counts, authenticated run
  timings, property count and complete five-query results; no credentials.
- `verification/audit_constraint_reproduction.json`: original-code failure evidence.
- `data_manifest.json`: exact source file checksums and version.

Run with three isolated endpoints as documented in the README:

```bash
MS2_INTEGRATION=1 \
MS2_FIXTURE_URI=bolt://localhost:17688 \
MS2_AUDIT_CONFIG=/path/to/private-audit-config.txt \
MS2_AUDIT_OUTPUT=/path/to/audit-results.json \
python -m unittest discover -v
```

The fixture and authenticated audit databases must be empty before each run; the
tests refuse to reset existing data. Neo4j's custom-default database configuration
is documented in the [official Docker settings reference](https://neo4j.com/docs/operations-manual/current/docker/ref-settings/).
