"""Build and verify the Milestone 2 Formula 1 graph from adjacent raw CSVs."""
from __future__ import annotations

import argparse
import csv
import logging
import math
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable, SessionExpired
from neo4j.time import Date

BASE_DIR = Path(__file__).resolve().parent
LOG = logging.getLogger(__name__)


class ValidationError(ValueError):
    """Input or graph does not comply with the milestone specification."""


@dataclass(frozen=True)
class Table:
    """A fixed schema; these names never come from untrusted CSV values."""

    filename: str
    label: str
    key: str
    fields: tuple[str, ...]
    expected: int
    # (CSV foreign key, relationship type, target label, target identifier)
    links: tuple[tuple[str, str, str, str], ...] = ()


TABLES = (
    Table('drivers.csv', 'Driver', 'driverId', tuple('driverId driverRef number code forename surname dob nationality'.split()), 861),
    Table('constructors.csv', 'Constructor', 'constructorId', tuple('constructorId constructorRef constructor_name constructor_nationality'.split()), 212),
    Table('circuits.csv', 'Circuit', 'circuitId', tuple('circuitId circuitRef circuit_name circuit_loc circuit_country lat lng alt'.split()), 77),
    Table('seasons.csv', 'Season', 'year', ('year',), 75),
    Table('status.csv', 'Status', 'statusId', ('statusId', 'status'), 139),
    Table('races.csv', 'Race', 'raceId', tuple('raceId year round name date time'.split()), 1125,
          (('circuitId', 'AT_CIRCUIT', 'Circuit', 'circuitId'), ('year', 'IN_SEASON', 'Season', 'year'))),
    Table('results.csv', 'Result', 'resultId', tuple('resultId number grid position positionText positionOrder points laps time milliseconds fastestLap rank fastestLapTime fastestLapSpeed'.split()), 26759,
          (('raceId', 'FOR_RACE', 'Race', 'raceId'), ('driverId', 'BY_DRIVER', 'Driver', 'driverId'),
           ('constructorId', 'FOR_CONSTRUCTOR', 'Constructor', 'constructorId'), ('statusId', 'HAS_STATUS', 'Status', 'statusId'))),
    Table('qualifying.csv', 'Qualifying', 'qualifyId', tuple('qualifyId number position q1 q2 q3'.split()), 10494,
          (('raceId', 'FOR_RACE', 'Race', 'raceId'), ('driverId', 'BY_DRIVER', 'Driver', 'driverId'),
           ('constructorId', 'FOR_CONSTRUCTOR', 'Constructor', 'constructorId'))),
    Table('pit_stops.csv', 'PitStop', 'eventId', tuple('eventId stop lap time duration milliseconds'.split()), 11371,
          (('raceId', 'FOR_RACE', 'Race', 'raceId'), ('driverId', 'BY_DRIVER', 'Driver', 'driverId'))),
)
SOURCE_FIELDS = {
    'constructor_name': 'name', 'constructor_nationality': 'nationality',
    'circuit_name': 'name', 'circuit_loc': 'location', 'circuit_country': 'country',
}
INTEGER_FIELDS = set('driverId constructorId circuitId year statusId raceId resultId qualifyId number round grid position positionOrder laps milliseconds fastestLap rank stop lap alt'.split())
FLOAT_FIELDS = {'points', 'lat', 'lng', 'fastestLapSpeed'}
DATE_FIELDS = {'dob', 'date'}
EXPECTED_NODES = {table.label: table.expected for table in TABLES}


def load_config(path: Path = BASE_DIR / 'config.txt') -> dict[str, str]:
    """Read configuration by key, preserving equals signs inside passwords."""
    config: dict[str, str] = {}
    try:
        lines = path.read_text(encoding='utf-8-sig').splitlines()
    except OSError as exc:
        raise ValidationError(f'Cannot read configuration file: {path.name}') from exc
    for line_number, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            raise ValidationError(f'config.txt line {line_number}: expected KEY=value')
        key, value = (part.strip() for part in line.split('=', 1))
        if key not in {'URI', 'USERNAME', 'PASSWORD', 'DATABASE'} or key in config:
            raise ValidationError(f'config.txt line {line_number}: unknown or duplicate key')
        if not value:
            raise ValidationError(f'config.txt line {line_number}: empty value')
        config[key] = value
    missing = {'URI', 'USERNAME', 'PASSWORD'} - config.keys()
    if missing:
        raise ValidationError('config.txt missing keys: ' + ', '.join(sorted(missing)))
    # Reject credentials embedded in a URI so driver diagnostics cannot expose them.
    from urllib.parse import urlsplit
    uri = urlsplit(config['URI'])
    if uri.scheme not in {'neo4j', 'neo4j+s', 'neo4j+ssc', 'bolt', 'bolt+s', 'bolt+ssc'} or not uri.hostname or uri.username or uri.password:
        raise ValidationError('Invalid URI: use a Neo4j/Bolt URI without embedded credentials')
    return config


def session_options(config: dict[str, str]) -> dict[str, str]:
    """Omission selects the server default; never silently select another DB."""
    return {'database': config['DATABASE']} if 'DATABASE' in config else {}


def clean_value(value: str | None) -> str | None:
    """Missing properties are omitted; the string zero is not missing."""
    if value is None:
        return None
    value = value.strip()
    return None if value in {'', '\\N'} else value


def convert_value(field: str, value: str | None) -> Any:
    value = clean_value(value)
    if value is None:
        return None
    try:
        if field in INTEGER_FIELDS:
            return int(value)
        if field in FLOAT_FIELDS:
            number = float(value)
            if not math.isfinite(number):
                raise ValueError('non-finite number')
            return number
        if field in DATE_FIELDS:
            return date.fromisoformat(value)
        return value
    except ValueError as exc:
        raise ValidationError(f'invalid {field} value') from exc


def required_columns(table: Table) -> set[str]:
    columns = {SOURCE_FIELDS.get(field, field) for field in table.fields if field != 'eventId'}
    columns.update(link[0] for link in table.links)
    return columns


def convert_row(table: Table, row: dict[str, str]) -> dict[str, Any]:
    """Produce a property map plus foreign keys used only for graph edges."""
    props = {field: convert_value(field, row[SOURCE_FIELDS.get(field, field)])
             for field in table.fields if field != 'eventId'}
    refs = {foreign: convert_value(foreign, row[foreign]) for foreign, *_ in table.links}
    if table.key == 'eventId':
        if any(value is None for value in (*refs.values(), props['stop'])):
            raise ValidationError('PitStop requires raceId, driverId and stop')
        props['eventId'] = f"{refs['raceId']}:{refs['driverId']}:{props['stop']}"
    if props.get(table.key) is None:
        raise ValidationError(f'missing identifier {table.key}')
    if any(value is None for value in refs.values()):
        raise ValidationError('missing foreign-key identifier')
    return {'id': props[table.key], 'props': props, 'refs': refs}


def validate_csv_files(directory: Path = BASE_DIR, *, strict_counts: bool = True) -> dict[str, list[dict[str, Any]]]:
    """Validate every file, row, unique key and FK before any database write."""
    missing = [table.filename for table in TABLES if not (directory / table.filename).is_file()]
    if missing:
        raise ValidationError('Missing CSV files: ' + ', '.join(missing))
    data: dict[str, list[dict[str, Any]]] = {}
    for table in TABLES:
        rows = []
        identifiers = set()
        line_number = 1
        try:
            with (directory / table.filename).open(encoding='utf-8-sig', newline='') as handle:
                reader = csv.DictReader(handle, strict=True)
                headers = reader.fieldnames or []
                absent = required_columns(table) - set(headers)
                if absent or len(headers) != len(set(headers)):
                    raise ValidationError('missing or duplicate CSV columns: ' + ', '.join(sorted(absent)))
                for row in reader:
                    line_number = reader.line_num
                    if None in row or any(value is None for value in row.values()):
                        raise ValidationError('row has an incorrect number of columns')
                    converted = convert_row(table, row)
                    if converted['id'] in identifiers:
                        raise ValidationError(f"duplicate {table.key}: {converted['id']}")
                    identifiers.add(converted['id'])
                    rows.append(converted)
        except (OSError, UnicodeError, csv.Error, ValueError) as exc:
            raise ValidationError(f'{table.filename}, line {line_number}: {exc}') from exc
        if strict_counts and len(rows) != table.expected:
            raise ValidationError(f'{table.filename}: expected {table.expected} rows, found {len(rows)}; use the original MS1 dataset')
        data[table.label] = rows
    identifiers_by_label = {label: {row['id'] for row in rows} for label, rows in data.items()}
    for table in TABLES:
        for row in data[table.label]:
            for foreign, _, target, _ in table.links:
                if row['refs'][foreign] not in identifiers_by_label[target]:
                    raise ValidationError(f"{table.filename}, {table.key}={row['id']}: unresolved {foreign}={row['refs'][foreign]}")
    return data


def create_constraints(session: Any) -> None:
    """Match constraints by schema, avoiding collisions with unrelated names."""
    for table in TABLES:
        session.run('CREATE CONSTRAINT IF NOT EXISTS '
                    f'FOR (n:{table.label}) REQUIRE n.{table.key} IS UNIQUE').consume()


def import_query(table: Table) -> str:
    """Interpolate only the fixed schema; all dataset values are parameters."""
    query = f'UNWIND $rows AS row\nMERGE (n:{table.label} {{{table.key}: row.id}})\nSET n += row.props\n'
    for index, (foreign, relationship, target, key) in enumerate(table.links):
        query += f'WITH row, n\nMATCH (p{index}:{target} {{{key}: row.refs.{foreign}}})\nMERGE (n)-[:{relationship}]->(p{index})\n'
    return query + 'RETURN count(n) AS imported'


def write_batch(tx: Any, query: str, rows: list[dict[str, Any]]) -> None:
    record = tx.run(query, rows=rows).single()
    if record is None or record['imported'] != len(rows):
        raise ValidationError('Batch failed: a required parent node is missing')


def import_graph(session: Any, data: dict[str, list[dict[str, Any]]], batch_size: int = 1000) -> None:
    """Upsert parents before facts; each batch is atomic and safe to retry."""
    if batch_size < 1:
        raise ValidationError('Batch size must be positive')
    create_constraints(session)
    for table in TABLES:
        rows = data[table.label]
        for start in range(0, len(rows), batch_size):
            batch = rows[start:start + batch_size]
            try:
                session.execute_write(write_batch, import_query(table), batch)
            except (Neo4jError, ServiceUnavailable, SessionExpired, ValidationError) as exc:
                # Do not include driver exception strings: these can contain server details.
                raise ValidationError(f"{table.filename}: batch records {start + 1}–{start + len(batch)}, identifiers {batch[0]['id']}–{batch[-1]['id']} failed ({type(exc).__name__}); check connectivity, schema constraints and parent nodes") from exc
            LOG.info('%s: %d/%d imported', table.label, min(start + batch_size, len(rows)), len(rows))


def property_type(field: str) -> type:
    if field in INTEGER_FIELDS:
        return int
    if field in FLOAT_FIELDS:
        return float
    if field in DATE_FIELDS:
        return Date
    return str


def verify_graph(session: Any, data: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Read back all properties and edges and compare with validated CSV data.

    Unrelated labels are left alone. Extra nodes using MS2 labels or extra edges
    touching MS2 nodes are reported, never deleted. Use a dedicated database.
    """
    counts: dict[str, int] = {}
    edge_counts: Counter[str] = Counter()
    patterns: dict[str, int] = {}
    for table in TABLES:
        expected = {row['id']: row for row in data[table.label]}
        seen = set()
        for record in session.run(f'MATCH (n:{table.label}) RETURN properties(n) AS props, labels(n) AS labels'):
            props = record['props']
            identifier = props.get(table.key)
            if identifier not in expected or identifier in seen:
                raise ValidationError(f'{table.label}: unexpected or duplicate identifier {identifier}')
            seen.add(identifier)
            if record['labels'] != [table.label]:
                raise ValidationError(f'{table.label} {identifier}: unexpected labels')
            wanted = {key: value for key, value in expected[identifier]['props'].items() if value is not None}
            if set(props) != set(wanted):
                raise ValidationError(f'{table.label} {identifier}: missing or extra properties')
            for key, value in props.items():
                if type(value) is not property_type(key):
                    raise ValidationError(f'{table.label} {identifier}: incorrect type for {key}')
                native = value.to_native() if isinstance(value, Date) else value
                if native != wanted[key]:
                    raise ValidationError(f'{table.label} {identifier}: incorrect value for {key}')
            # Checking every value also rejects literal \\N and empty missing fields.
        if seen != set(expected):
            raise ValidationError(f'{table.label}: expected {len(expected)} nodes, found {len(seen)}')
        counts[table.label] = len(seen)
        for foreign, relationship, target, target_key in table.links:
            actual = Counter((record['source'], record['target']) for record in session.run(
                f'MATCH (n:{table.label})-[:{relationship}]->(p:{target}) '
                f'RETURN n.{table.key} AS source, p.{target_key} AS target'))
            wanted_edges = Counter((row['id'], row['refs'][foreign]) for row in expected.values())
            if actual != wanted_edges:
                raise ValidationError(f'{table.label}-[:{relationship}]->{target}: missing, duplicate or incorrect connections')
            count = sum(actual.values())
            patterns[f'{table.label}-[{relationship}]->{target}'] = count
            edge_counts[relationship] += count
    # Every expected edge is already checked. Any additional incident edge is invalid.
    record = session.run('MATCH (a)-[r]->(b) WHERE any(l IN labels(a) WHERE l IN $labels) '
                         'OR any(l IN labels(b) WHERE l IN $labels) RETURN count(r) AS total',
                         labels=list(EXPECTED_NODES)).single()
    if record['total'] != sum(edge_counts.values()):
        raise ValidationError('Unexpected or reversed relationships touching MS2 nodes')
    report = {'nodes': counts, 'relationships': dict(edge_counts), 'patterns': patterns,
              'total_nodes': sum(counts.values()), 'total_relationships': sum(edge_counts.values())}
    LOG.info('Verified %d nodes and %d relationships; all properties, types and connections match', report['total_nodes'], report['total_relationships'])
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch-size', type=int, default=1000)
    parser.add_argument('--validate-only', action='store_true', help='Validate CSVs without connecting to Neo4j')
    parser.add_argument('--verify-only', action='store_true', help='Check existing graph without writing')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    # Suppress driver diagnostics that may contain connection details; errors below are sanitized.
    logging.getLogger('neo4j').setLevel(logging.CRITICAL)
    try:
        if args.batch_size < 1:
            raise ValidationError('Batch size must be positive')
        data = validate_csv_files()
        LOG.info('All nine CSVs validated: %d rows', sum(map(len, data.values())))
        if args.validate_only:
            return 0
        config = load_config()
        with GraphDatabase.driver(config['URI'], auth=(config['USERNAME'], config['PASSWORD']), connection_timeout=10) as driver:
            driver.verify_connectivity()
            with driver.session(**session_options(config)) as session:
                if not args.verify_only:
                    import_graph(session, data, args.batch_size)
                verify_graph(session, data)
        return 0
    except ValidationError as exc:
        LOG.error('%s', exc)
    except (Neo4jError, ServiceUnavailable, SessionExpired) as exc:
        LOG.error('Neo4j operation failed (%s). Check the server, URI, credentials, configured DATABASE and permissions.', type(exc).__name__)
    except (OSError, ValueError) as exc:
        LOG.error('Operation failed (%s). Check local files and connection configuration.', type(exc).__name__)
    return 1


if __name__ == '__main__':
    sys.exit(main())
