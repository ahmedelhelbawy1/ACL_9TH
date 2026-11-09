"""Opt-in tests: real CSV answers, reruns, and isolated synthetic edge cases.

MS2_INTEGRATION=1 enables real-data tests using adjacent config.txt.
MS2_FIXTURE_URI enables fixture tests ONLY on an empty disposable database.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import tempfile
import unittest

from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError

from Create_kg import (BASE_DIR, ValidationError, import_graph, load_config,
                       session_options, validate_csv_files, verify_graph)
from run_queries import execute_queries
from tests.fixtures import write_fixture
from tests.reference import reference_answers


def assert_answers(case: unittest.TestCase, actual: list, expected: list) -> None:
    for index, (found, wanted) in enumerate(zip(actual, expected), 1):
        with case.subTest(query=index):
            case.assertEqual(len(found), len(wanted))
            for actual_row, expected_row in zip(found, wanted):
                case.assertEqual(list(actual_row), list(expected_row))
                for key, value in expected_row.items():
                    if isinstance(value, float):
                        case.assertAlmostEqual(actual_row[key], value, places=9)
                    else:
                        case.assertEqual(actual_row[key], value)


@unittest.skipUnless(os.environ.get('MS2_INTEGRATION') == '1', 'Set MS2_INTEGRATION=1 for the real-data graph')
class RealDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = load_config()
        cls.data = validate_csv_files()
        cls.driver = GraphDatabase.driver(config['URI'], auth=(config['USERNAME'], config['PASSWORD']))
        cls.addClassCleanup(cls.driver.close)
        cls.session = cls.driver.session(**session_options(config))
        cls.addClassCleanup(cls.session.close)
        import_graph(cls.session, cls.data)

    def test_full_schema_and_rerun(self):
        first = verify_graph(self.session, self.data)
        import_graph(self.session, self.data, batch_size=777)
        second = verify_graph(self.session, self.data)
        self.assertEqual(first, second)
        self.assertEqual(second['total_nodes'], 51113)
        self.assertEqual(second['total_relationships'], 163510)
        self.assertEqual(second['relationships'], {
            'AT_CIRCUIT': 1125, 'IN_SEASON': 1125, 'FOR_RACE': 48624,
            'BY_DRIVER': 48624, 'FOR_CONSTRUCTOR': 37253, 'HAS_STATUS': 26759})

    def test_five_queries_against_independent_csv_answers(self):
        assert_answers(self, execute_queries(self.session), reference_answers(BASE_DIR))

    def test_explicit_database_and_no_fallback(self):
        database = self.session.run('CALL db.info() YIELD name RETURN name').single()['name']
        with self.driver.session(database=database) as session:
            self.assertEqual(session.run('MATCH (n:Driver) RETURN count(n) AS n').single()['n'], 861)
        with self.driver.session(database='ms2_nonexistent_database') as session:
            with self.assertRaises(Neo4jError):
                session.run('RETURN 1').consume()


@unittest.skipUnless(os.environ.get('MS2_FIXTURE_URI'), 'Set MS2_FIXTURE_URI to an EMPTY disposable Neo4j database')
class EdgeCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = Path(cls.temp.name)
        write_fixture(cls.directory)
        cls.data = validate_csv_files(cls.directory, strict_counts=False)
        cls.driver = GraphDatabase.driver(os.environ['MS2_FIXTURE_URI'], auth=(
            os.environ.get('MS2_FIXTURE_USERNAME', 'neo4j'), os.environ.get('MS2_FIXTURE_PASSWORD', 'local_test_only')))
        cls.addClassCleanup(cls.driver.close)
        cls.session = cls.driver.session()
        cls.addClassCleanup(cls.session.close)
        if cls.session.run('MATCH (n) RETURN count(n) AS count').single()['count']:
            raise RuntimeError('Fixture database must be EMPTY; refusing to change existing data')
        import_graph(cls.session, cls.data, batch_size=17)

    def test_all_queries_and_sorting(self):
        assert_answers(self, execute_queries(self.session), reference_answers(self.directory))

    def test_shared_drives_and_primary_constructor_tie(self):
        answers = execute_queries(self.session)
        hamilton = next(row for row in answers[3] if row['Driver'] == 'Lewis Hamilton')
        self.assertEqual(hamilton['Starts'], 5)
        self.assertAlmostEqual(hamilton['Avg_Finish'], round(10 / 6, 6))
        self.assertEqual(hamilton['Wins'], 5)
        self.assertEqual(answers[4], [{'Drivers_Changed': 2, 'Drivers': ['Lewis Hamilton', 'Tie Driver']}])
        self.assertEqual(sum(row['Shared_Races'] for row in answers[2]), 6)

    def test_zero_changed_drivers_still_returns_one_row(self):
        with self.session.begin_transaction() as tx:
            tx.run('MATCH (r:Race {year: 2021}) SET r.year = 2022').consume()
            self.assertEqual(execute_queries(tx)[4], [{'Drivers_Changed': 0, 'Drivers': []}])
            tx.rollback()

    def test_idempotent_rerun(self):
        first = verify_graph(self.session, self.data)
        import_graph(self.session, self.data, batch_size=13)
        self.assertEqual(verify_graph(self.session, self.data), first)

    def assert_corruption_detected(self, query):
        with self.session.begin_transaction() as tx:
            tx.run(query).consume()
            with self.assertRaises(ValidationError):
                verify_graph(tx, self.data)
            tx.rollback()

    def test_duplicate_relationship_detected(self):
        self.assert_corruption_detected('MATCH (r:Result {resultId: 1}), (d:Driver {driverId: 1}) CREATE (r)-[:BY_DRIVER]->(d)')

    def test_reversed_relationship_detected(self):
        self.assert_corruption_detected('MATCH (r:Result {resultId: 1}), (d:Driver {driverId: 1}) CREATE (d)-[:BY_DRIVER]->(r)')

    def test_missing_relationship_detected(self):
        self.assert_corruption_detected('MATCH (:Result {resultId: 1})-[r:FOR_RACE]->() DELETE r')

    def test_incorrect_property_type_detected(self):
        self.assert_corruption_detected("MATCH (r:Result {resultId: 1}) SET r.points = '25'")

    def test_literal_missing_value_detected(self):
        with self.session.begin_transaction() as tx:
            tx.run('MATCH (d:Driver {driverId: 1}) SET d.code = $missing', missing='\\N').consume()
            with self.assertRaises(ValidationError):
                verify_graph(tx, self.data)
            tx.rollback()

    def test_empty_optional_properties_are_absent(self):
        record = self.session.run("MATCH (q:Qualifying) RETURN properties(q)['q2'] AS q2, properties(q)['q3'] AS q3").single()
        self.assertIsNone(record['q2'])
        self.assertIsNone(record['q3'])

    def test_missing_properties_removed_on_rerun(self):
        # Temporary transaction: exercise the same upsert statement without persisting corruption.
        from Create_kg import TABLES, import_query, write_batch
        with self.session.begin_transaction() as tx:
            tx.run("MATCH (q:Qualifying) SET q.q2 = 'stale'").consume()
            write_batch(tx, import_query(TABLES[7]), self.data['Qualifying'])
            verify_graph(tx, self.data)
            tx.rollback()

    def test_duplicate_node_identifier_rejected(self):
        with self.assertRaises(Neo4jError):
            with self.session.begin_transaction() as tx:
                tx.run('CREATE (:Driver {driverId: 1})').consume()

    def test_same_name_drivers_are_not_aggregated_together(self):
        with self.session.begin_transaction() as tx:
            tx.run("MATCH (race:Race {raceId: 7}) "
                   "CREATE (d:Driver {driverId: 999, forename: 'Lewis', surname: 'Hamilton'}) "
                   "CREATE (r:Result {resultId: 99999, points: 3.0, position: 4}) "
                   "CREATE (r)-[:BY_DRIVER]->(d), (r)-[:FOR_RACE]->(race)").consume()
            matches = [row for row in execute_queries(tx)[0] if row['Driver'] == 'Lewis Hamilton']
            self.assertEqual([row['Points'] for row in matches], [26.0, 3.0])
            tx.rollback()

    def test_unrelated_data_preserved(self):
        with self.session.begin_transaction() as tx:
            tx.run('CREATE (:UnrelatedTestNode {value: 42})').consume()
            verify_graph(tx, self.data)
            self.assertEqual(tx.run('MATCH (n:UnrelatedTestNode) RETURN n.value AS value').single()['value'], 42)
            tx.rollback()


if __name__ == '__main__':
    unittest.main()
