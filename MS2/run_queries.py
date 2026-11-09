"""Execute the five submitted queries and optionally save their actual results."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from neo4j import GraphDatabase

from Create_kg import BASE_DIR, load_config, session_options

COLUMNS = [
    ['Driver', 'Points', 'Wins'],
    ['Constructor', 'Entries', 'Classified', 'Reliability'],
    ['Constructor', 'Shared_Races', 'Hamilton_Ahead', 'Bottas_Ahead'],
    ['Driver', 'Starts', 'Avg_Finish', 'Wins'],
    ['Drivers_Changed', 'Drivers'],
]


def read_queries(path: Path = BASE_DIR / 'queries.txt') -> list[str]:
    text = path.read_text(encoding='utf-8')
    headers = re.findall(r'^//\d+\. Query \d+$', text, flags=re.MULTILINE)
    if headers != [f'//{i}. Query {i}' for i in range(1, 6)]:
        raise ValueError('queries.txt must contain the five exact numbered headers in order')
    pieces = re.split(r'^//\d+\. Query \d+\s*$', text, flags=re.MULTILINE)
    if pieces[0].strip():
        raise ValueError('Unexpected content before Query 1')
    queries = [piece.strip().rstrip(';') for piece in pieces[1:]]
    if not all(queries):
        raise ValueError('Empty query')
    return queries


def execute_queries(session: object) -> list[list[dict]]:
    results = []
    for index, query in enumerate(read_queries()):
        result = session.run(query)
        if list(result.keys()) != COLUMNS[index]:
            raise ValueError(f'Query {index + 1}: incorrect output columns')
        results.append(result.data())
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Save all query results as JSON')
    args = parser.parse_args()
    config = load_config()
    with GraphDatabase.driver(config['URI'], auth=(config['USERNAME'], config['PASSWORD'])) as driver:
        with driver.session(**session_options(config)) as session:
            results = execute_queries(session)
    for index, rows in enumerate(results, 1):
        print(f'Query {index}: {len(rows)} rows; columns: {", ".join(COLUMNS[index - 1])}')
    if args.output:
        args.output.write_text(json.dumps(results, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
