# Verification record — November 9, 2026

This is the original 35-test delivery record. A subsequent strict audit passed 47
tests, including authenticated standalone imports and independent PDF-schema checks.
See `verification/audit_tests.txt` and `verification/audit_database.json` for that run.

The full raw version-24 dataset was imported into an isolated local Neo4j 5.26
Community instance using Python 3.11 and the official Neo4j Python driver 5.28.8.
All nine CSV counts match the saved output in the original MS1 notebook. The pinned
archive was downloaded separately and all nine file checksums were verified.

## Results

- **51,113 nodes** and **163,510 relationships**, verified by reading the database.
- All nine labels, eleven relationship patterns, identifiers, property sets, values
  and types matched the source CSVs.
- Repeated imports, including different batch sizes, preserved all counts and data.
- All five Cypher query results, column names and ordering matched independent Python
  calculations from the raw CSVs.
- **35 tests passed, 0 failures, 0 skipped** in the full integration run.
- Explicit database selection worked. Selecting a nonexistent database failed rather
  than falling back to another database.
- Synthetic fixtures verified shared drives, constructor ties and renames, distinct
  driver identities with the same name, missing values, duplicate identifiers,
  duplicate/reversed/missing relationships, wrong property types, zero matches and
  preservation of unrelated data.
- The original notebook's Git blob hash is unchanged:
  `4cab5b5418117c7a0ab5b5361db688021c7ce21f`.

Actual evidence:

- [`verification/tests.txt`](verification/tests.txt): full passing test log.
- [`verification/graph.json`](verification/graph.json): per-label, per-type and per-pattern counts.
- [`verification/query_results.json`](verification/query_results.json): all returned rows for all five queries, in order.
- [`data_manifest.json`](data_manifest.json): source version, license and raw file checksums.

The full suite was run with:

```bash
MS2_INTEGRATION=1 MS2_FIXTURE_URI=bolt://localhost:17688 python -m unittest discover -v
```

Integration tests require the described local servers. Running the default suite
without the environment flags intentionally skips them rather than pretending they
passed. Recreate an empty disposable fixture database before rerunning edge-case tests.

## Local delivery

The local full-data test server is the Docker container `acl-ms2-neo4j`, with Browser
at `http://localhost:17474` and Bolt at `bolt://localhost:17687`. It is bound only to
localhost and uses authentication disabled for this isolated local test. The ignored
local `config.txt` points to it; its username/password fields contain test placeholders.
If Docker is restarted, run `docker start acl-ms2-neo4j`. The optional Compose setup
in the README is an alternative authenticated server, not something to start alongside
this container on the same ports.

The three mandatory files (`Create_kg.py`, local `config.txt`, `queries.txt`) and all
nine CSVs are present locally under `MS2/`. Credentials/configuration and CSVs are not
published to GitHub. No university form submission or main-branch merge is performed.

## Limits

The university's private grading queries are not available; they cannot be claimed
as tested. Neo4j Aura, clustered deployments and other server/driver versions were
not exercised. No known implementation or test failures remain in the tested setup.
