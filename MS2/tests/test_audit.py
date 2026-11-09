"""Independent PDF-schema and standalone grading audit on a disposable server.

Set MS2_AUDIT_CONFIG to a private config file for an EMPTY authenticated database
whose name is not neo4j. No existing data is removed. Each run needs a fresh database.
"""
from __future__ import annotations

from collections import Counter
import csv
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from neo4j import GraphDatabase
from neo4j.time import Date

from Create_kg import BASE_DIR, load_config
from run_queries import execute_queries
from tests.reference import reference_answers
from tests.test_integration import assert_answers

# Transcribed from the PDF, deliberately independent of the importer's TABLES,
# property-type sets, mappings, conversion functions and verify_graph().
SPEC = {
    'Driver': ('drivers.csv', 'driverId', 861, 'driverId driverRef number code forename surname dob nationality'),
    'Constructor': ('constructors.csv', 'constructorId', 212, 'constructorId constructorRef constructor_name constructor_nationality'),
    'Circuit': ('circuits.csv', 'circuitId', 77, 'circuitId circuitRef circuit_name circuit_loc circuit_country lat lng alt'),
    'Season': ('seasons.csv', 'year', 75, 'year'),
    'Status': ('status.csv', 'statusId', 139, 'statusId status'),
    'Race': ('races.csv', 'raceId', 1125, 'raceId year round name date time'),
    'Result': ('results.csv', 'resultId', 26759, 'resultId number grid position positionText positionOrder points laps time milliseconds fastestLap rank fastestLapTime fastestLapSpeed'),
    'Qualifying': ('qualifying.csv', 'qualifyId', 10494, 'qualifyId number position q1 q2 q3'),
    'PitStop': ('pit_stops.csv', 'eventId', 11371, 'eventId stop lap time duration milliseconds'),
}
EDGES = [
    ('Race', 'AT_CIRCUIT', 'Circuit', 'circuitId'), ('Race', 'IN_SEASON', 'Season', 'year'),
    ('Result', 'FOR_RACE', 'Race', 'raceId'), ('Result', 'BY_DRIVER', 'Driver', 'driverId'),
    ('Result', 'FOR_CONSTRUCTOR', 'Constructor', 'constructorId'), ('Result', 'HAS_STATUS', 'Status', 'statusId'),
    ('Qualifying', 'FOR_RACE', 'Race', 'raceId'), ('Qualifying', 'BY_DRIVER', 'Driver', 'driverId'),
    ('Qualifying', 'FOR_CONSTRUCTOR', 'Constructor', 'constructorId'),
    ('PitStop', 'FOR_RACE', 'Race', 'raceId'), ('PitStop', 'BY_DRIVER', 'Driver', 'driverId'),
]
INTS = set('driverId constructorId circuitId year statusId raceId resultId qualifyId number round grid position positionOrder laps milliseconds fastestLap rank stop lap alt'.split())
FLOATS = {'points', 'lat', 'lng', 'fastestLapSpeed'}
DATES = {'dob', 'date'}
RENAMES = {'constructor_name': 'name', 'constructor_nationality': 'nationality',
           'circuit_name': 'name', 'circuit_loc': 'location', 'circuit_country': 'country'}


def csv_identifier(label, row):
    if label == 'PitStop':
        return ':'.join(str(int(row[key])) for key in ('raceId', 'driverId', 'stop'))
    return int(row[SPEC[label][1]])


def count_snapshot(session):
    """Real Cypher count queries, not inferred totals from CSV row counts."""
    nodes = {label: session.run(f'MATCH (n:{label}) RETURN count(n) AS n').single()['n'] for label in SPEC}
    patterns = {f'{source}-[{rel}]->{target}': session.run(
        f'MATCH (:{source})-[r:{rel}]->(:{target}) RETURN count(r) AS n').single()['n']
        for source, rel, target, _ in EDGES}
    return {'nodes': nodes, 'patterns': patterns,
            'total_nodes': session.run('MATCH (n) RETURN count(n) AS n').single()['n'],
            'total_relationships': session.run('MATCH ()-[r]->() RETURN count(r) AS n').single()['n']}


@unittest.skipUnless(os.environ.get('MS2_AUDIT_CONFIG'), 'Set MS2_AUDIT_CONFIG for isolated authenticated CLI audit')
class StandaloneAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config(Path(os.environ['MS2_AUDIT_CONFIG']))
        if cls.config.get('DATABASE') in (None, 'neo4j', 'system'):
            raise RuntimeError('Audit requires an explicitly named custom disposable database')
        cls.driver = GraphDatabase.driver(cls.config['URI'], auth=(cls.config['USERNAME'], cls.config['PASSWORD']))
        cls.addClassCleanup(cls.driver.close)
        cls.session = cls.driver.session(database=cls.config['DATABASE'])
        cls.addClassCleanup(cls.session.close)
        if cls.session.run('MATCH (n) RETURN count(n) AS n').single()['n'] != 0:
            raise RuntimeError('Audit database must be EMPTY; no data will be cleared')
        # An unrelated existing name must not silently suppress Driver uniqueness.
        cls.session.run('CREATE CONSTRAINT ms2_driver_id IF NOT EXISTS '
                        'FOR (n:AuditUnrelated) REQUIRE n.externalId IS UNIQUE').consume()
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.bundle = cls.root / 'grader_bundle'
        cls.bundle.mkdir()
        shutil.copyfile(BASE_DIR / 'Create_kg.py', cls.bundle / 'Create_kg.py')
        cls.raw = {}
        manifest = json.loads((BASE_DIR / 'data_manifest.json').read_text())
        for label, (filename, _, expected_count, _) in SPEC.items():
            source = BASE_DIR / filename
            assert hashlib.sha256(source.read_bytes()).hexdigest() == manifest['files'][filename]['sha256']
            shutil.copyfile(source, cls.bundle / filename)
            with source.open(encoding='utf-8-sig', newline='') as handle:
                rows = list(csv.DictReader(handle))
            assert len(rows) == expected_count
            cls.raw[label] = {csv_identifier(label, row): row for row in rows}
        cls.runs = []
        cls.snapshots = []
        # Full executable runs from an unrelated cwd, first without DATABASE,
        # then with DATABASE in shuffled key order. No project modules are copied.
        for explicit in (False, True):
            cls.write_config(explicit=explicit)
            started = time.monotonic()
            result = cls.run_cli()
            if result.returncode:
                raise AssertionError(f'Standalone import failed: {result.stdout}\n{result.stderr}')
            cls.runs.append({'explicit_database': explicit, 'exit_code': result.returncode,
                             'seconds': round(time.monotonic() - started, 3)})
            cls.snapshots.append(count_snapshot(cls.session))
        cls.answers = execute_queries(cls.session)
        cls.evidence = {'database': cls.config['DATABASE'], 'authenticated': True,
                        'standalone_runs': cls.runs, 'first_import': cls.snapshots[0],
                        'second_import': cls.snapshots[1], 'query_results': cls.answers}

    @classmethod
    def tearDownClass(cls):
        # Credential-free optional evidence, retained even if an assertion fails.
        if os.environ.get('MS2_AUDIT_OUTPUT'):
            Path(os.environ['MS2_AUDIT_OUTPUT']).write_text(json.dumps(cls.evidence, ensure_ascii=False, indent=2) + '\n')

    @classmethod
    def write_config(cls, *, explicit=True, overrides=None):
        config = dict(cls.config)
        if not explicit:
            config.pop('DATABASE')
        if overrides:
            config.update(overrides)
        # Deliberately not URI/USERNAME/PASSWORD order.
        path = cls.bundle / 'config.txt'
        path.write_text('\n'.join(f'{key}={config[key]}' for key in ('PASSWORD', 'DATABASE', 'URI', 'USERNAME') if key in config) + '\n')
        path.chmod(0o600)

    @classmethod
    def run_cli(cls):
        return subprocess.run([sys.executable, str(cls.bundle / 'Create_kg.py')], cwd=cls.root,
                              text=True, capture_output=True, timeout=180)

    def test_complete_imports_with_and_without_database(self):
        self.assertEqual(self.snapshots[0], self.snapshots[1])
        snapshot = self.snapshots[1]
        self.assertEqual(snapshot['total_nodes'], 51113)
        self.assertEqual(snapshot['total_relationships'], 163510)
        self.assertEqual(snapshot['nodes'], {label: spec[2] for label, spec in SPEC.items()})
        self.assertEqual(snapshot['patterns'], {f'{s}-[{r}]->{t}': SPEC[s][2] for s, r, t, _ in EDGES})
        self.assertEqual(self.session.run('CALL db.info() YIELD name RETURN name').single()['name'], self.config['DATABASE'])

    def test_every_property_against_independent_pdf_spec_and_csv(self):
        checked = 0
        for label, (_, key, _, fields) in SPEC.items():
            seen = set()
            for record in self.session.run(f'MATCH (n:{label}) RETURN labels(n) AS labels, properties(n) AS p'):
                self.assertEqual(record['labels'], [label])
                props = record['p']
                identifier = props[key]
                self.assertNotIn(identifier, seen)
                seen.add(identifier)
                row = self.raw[label][identifier]
                expected = {}
                for field in fields.split():
                    text = str(identifier) if field == 'eventId' else row[RENAMES.get(field, field)].strip()
                    if text in ('', '\\N'):
                        self.assertNotIn(field, props)
                        continue
                    cast = int if field in INTS else float if field in FLOATS else date.fromisoformat if field in DATES else str
                    expected[field] = cast(text)
                    actual_type = int if field in INTS else float if field in FLOATS else Date if field in DATES else str
                    self.assertIs(type(props[field]), actual_type, f'{label}.{field}')
                    checked += 1
                actual = {k: v.to_native() if type(v) is Date else v for k, v in props.items()}
                self.assertEqual(actual, expected)
            self.assertEqual(seen, set(self.raw[label]))
        self.evidence['properties_individually_checked'] = checked

    def test_every_relationship_endpoint_and_no_duplicate_edges(self):
        for source, relation, target, foreign in EDGES:
            source_id, target_id = SPEC[source][1], SPEC[target][1]
            actual = Counter((r['source'], r['target']) for r in self.session.run(
                f'MATCH (s:{source})-[:{relation}]->(t:{target}) '
                f'RETURN s.{source_id} AS source, t.{target_id} AS target'))
            expected = Counter((key, int(row[foreign])) for key, row in self.raw[source].items())
            self.assertEqual(actual, expected, f'{source}-{relation}->{target}')
        actual_patterns = {(tuple(r['s']), r['type'], tuple(r['t'])) for r in self.session.run(
            'MATCH (s)-[r]->(t) RETURN DISTINCT labels(s) AS s, type(r) AS type, labels(t) AS t')}
        self.assertEqual(actual_patterns, {((s,), r, (t,)) for s, r, t, _ in EDGES})

    def test_all_nine_unique_constraints_despite_name_collision(self):
        constraints = self.session.run('SHOW CONSTRAINTS YIELD type, labelsOrTypes, properties '
                                       'RETURN type, labelsOrTypes, properties').data()
        unique = {(tuple(r['labelsOrTypes']), tuple(r['properties'])) for r in constraints if r['type'] == 'UNIQUENESS'}
        for label, (_, key, _, _) in SPEC.items():
            self.assertIn(((label,), (key,)), unique)
        self.assertIn((('AuditUnrelated',), ('externalId',)), unique)

    def test_five_queries_against_independent_raw_csv_answers(self):
        assert_answers(self, self.answers, reference_answers(BASE_DIR))

    def test_wrong_password_rejected_without_secret_disclosure(self):
        wrong = 'audit-intentionally-wrong-password'
        self.write_config(overrides={'PASSWORD': wrong})
        try:
            result = self.run_cli()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('AuthError', result.stderr)
            self.assertNotIn(wrong, result.stdout + result.stderr)
            self.assertNotIn(self.config['PASSWORD'], result.stdout + result.stderr)
        finally:
            self.write_config()

    def test_wrong_database_rejected_without_fallback(self):
        self.write_config(overrides={'DATABASE': 'audit_nonexistent_database'})
        try:
            result = self.run_cli()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('ERROR', result.stderr)
            self.assertEqual(count_snapshot(self.session), self.snapshots[1])
        finally:
            self.write_config()

    def test_unrelated_node_preserved_by_full_import(self):
        # Roll back after exercising every importer batch against this transaction.
        from Create_kg import TABLES, import_query, validate_csv_files, write_batch
        data = validate_csv_files()
        with self.session.begin_transaction() as tx:
            tx.run('CREATE (:AuditUnrelated {externalId: "keep-me"})').consume()
            for table in TABLES:
                for start in range(0, len(data[table.label]), 1000):
                    write_batch(tx, import_query(table), data[table.label][start:start + 1000])
            self.assertEqual(tx.run('MATCH (n:AuditUnrelated) RETURN n.externalId AS id').single()['id'], 'keep-me')
            tx.rollback()
