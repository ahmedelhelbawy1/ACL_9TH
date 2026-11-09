"""No server required: parser failures and specification-sensitive conversions."""
import csv
from datetime import date
from pathlib import Path
import tempfile
import unittest

from Create_kg import (TABLES, ValidationError, clean_value, convert_value, load_config,
                       session_options, validate_csv_files)
from run_queries import read_queries
from tests.fixtures import write_fixture


class UnitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        write_fixture(self.directory)

    def test_all_nine_tables_and_pitstop_identifier(self):
        data = validate_csv_files(self.directory, strict_counts=False)
        self.assertEqual(len(data), 9)
        self.assertEqual(data['PitStop'][0]['id'], '7:1:1')

    def test_missing_values_and_zero(self):
        for value in ('\\N', '', '   ', None):
            self.assertIsNone(clean_value(value))
        self.assertEqual(convert_value('number', '0'), 0)
        self.assertIsNone(convert_value('q2', ''))

    def test_numeric_types(self):
        self.assertIs(type(convert_value('points', '0')), float)
        self.assertIs(type(convert_value('alt', '0')), int)
        self.assertIs(type(convert_value('fastestLapSpeed', '200.3')), float)
        self.assertIs(type(convert_value('duration', '22.5')), str)

    def test_dates(self):
        self.assertEqual(convert_value('date', '2021-01-02'), date(2021, 1, 2))
        self.assertIs(type(convert_value('dob', '1985-01-07')), date)

    def test_bad_types(self):
        for field, value in [('position', '1.5'), ('points', 'nan'), ('lat', 'inf'), ('date', '2021-02-30')]:
            with self.subTest(field=field), self.assertRaises(ValidationError):
                convert_value(field, value)

    def test_config_by_key_and_embedded_equals(self):
        path = self.directory / 'config.txt'
        path.write_text('PASSWORD=a=b=c\nDATABASE=custom\n# comment\nUSERNAME=neo4j\nURI=bolt://localhost:7687\n')
        config = load_config(path)
        self.assertEqual(config['PASSWORD'], 'a=b=c')
        self.assertEqual(session_options(config), {'database': 'custom'})
        del config['DATABASE']
        self.assertEqual(session_options(config), {})

    def test_bad_configs_do_not_leak_values(self):
        path = self.directory / 'config.txt'
        for contents in ['PASSWORD=secret\n', 'URI=bad\nUSERNAME=u\nPASSWORD=secret', 'URI=bolt://user:secret@localhost\nUSERNAME=u\nPASSWORD=secret', 'PASSWORD=secret\nPASSWORD=secret', 'DATABASE=']:
            path.write_text(contents)
            with self.subTest(contents=contents), self.assertRaises(ValidationError) as context:
                load_config(path)
            self.assertNotIn('secret', str(context.exception))

    def test_missing_file_names(self):
        (self.directory / 'drivers.csv').unlink()
        with self.assertRaisesRegex(ValidationError, 'drivers.csv'):
            validate_csv_files(self.directory)

    def test_required_columns(self):
        (self.directory / 'drivers.csv').write_text('driverId\n1\n')
        with self.assertRaisesRegex(ValidationError, 'columns'):
            validate_csv_files(self.directory, strict_counts=False)

    def mutate_results(self, change):
        path = self.directory / 'results.csv'
        with path.open(newline='') as handle:
            reader = csv.DictReader(handle)
            fields, rows = reader.fieldnames, list(reader)
        change(rows)
        with path.open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def test_duplicate_identifiers(self):
        self.mutate_results(lambda rows: rows.append(rows[0].copy()))
        with self.assertRaisesRegex(ValidationError, 'duplicate resultId'):
            validate_csv_files(self.directory, strict_counts=False)

    def test_missing_identifier(self):
        self.mutate_results(lambda rows: rows[0].update(resultId='\\N'))
        with self.assertRaisesRegex(ValidationError, 'missing identifier'):
            validate_csv_files(self.directory, strict_counts=False)

    def test_unresolved_foreign_key(self):
        self.mutate_results(lambda rows: rows[0].update(raceId='9999'))
        with self.assertRaisesRegex(ValidationError, 'unresolved raceId'):
            validate_csv_files(self.directory, strict_counts=False)

    def test_missing_foreign_key(self):
        self.mutate_results(lambda rows: rows[0].update(driverId=''))
        with self.assertRaisesRegex(ValidationError, 'missing foreign-key'):
            validate_csv_files(self.directory, strict_counts=False)

    def test_wrong_row_width(self):
        with (self.directory / 'drivers.csv').open('a') as handle:
            handle.write('1,2\n')
        with self.assertRaisesRegex(ValidationError, 'number of columns'):
            validate_csv_files(self.directory, strict_counts=False)

    def test_expected_dataset_counts(self):
        with self.assertRaisesRegex(ValidationError, 'expected 861'):
            validate_csv_files(self.directory)

    def test_query_headers_and_order(self):
        self.assertEqual(len(read_queries()), 5)
        path = self.directory / 'queries.txt'
        path.write_text('//2. Query 2\nRETURN 1\n')
        with self.assertRaises(ValueError):
            read_queries(path)


if __name__ == '__main__':
    unittest.main()
