"""Independent Python answers calculated from raw CSVs, not graph traversal."""
from collections import Counter, defaultdict
import csv
from pathlib import Path


def reference_answers(directory: Path) -> list[list[dict]]:
    def read(name):
        with (directory / (name + '.csv')).open(newline='', encoding='utf-8-sig') as handle:
            return list(csv.DictReader(handle))

    races = {int(r['raceId']): r for r in read('races')}
    drivers = {int(r['driverId']): r for r in read('drivers')}
    constructors = {int(r['constructorId']): r['name'] for r in read('constructors')}
    statuses = {int(r['statusId']): r['status'] for r in read('status')}
    results = read('results')
    name = lambda key: drivers[key]['forename'] + ' ' + drivers[key]['surname']
    performance, reliability, shared, monaco, primary = {}, {}, {}, {}, defaultdict(Counter)
    for row in results:
        race_id, driver, constructor = (int(row[key]) for key in ('raceId', 'driverId', 'constructorId'))
        race = races[race_id]
        year = int(race['year'])
        status = statuses[int(row['statusId'])]
        if year == 2021:
            p = performance.setdefault(driver, [0.0, 0])
            p[0] += float(row['points'])
            p[1] += row['position'] == '1'
        if 2014 <= year <= 2021:
            r = reliability.setdefault(constructor, [0, 0])
            r[0] += 1
            r[1] += status == 'Finished' or status.startswith('+')
        if driver in {1, 822}:
            pair = shared.setdefault((constructor, race_id), defaultdict(list))
            pair[driver].append(int(row['positionOrder']))
        if int(race['circuitId']) == 6 and race['date'] < '2020-01-01' and status not in {'Did not qualify', 'Did not prequalify', 'Withdrew'}:
            m = monaco.setdefault(driver, [set(), [], 0])
            m[0].add(race_id)
            m[1].append(int(row['positionOrder']))
            m[2] += row['position'] == '1'
        if year in {2020, 2021}:
            primary[(driver, year)][constructor] += 1
    q1 = [{'Driver': name(d), 'Points': p, 'Wins': w} for d, (p, w) in performance.items()]
    q1.sort(key=lambda r: (-r['Points'], -r['Wins'], r['Driver']))
    q2 = [{'Constructor': constructors[c], 'Entries': n, 'Classified': k, 'Reliability': k / n} for c, (n, k) in reliability.items() if n >= 100]
    q2.sort(key=lambda r: (-r['Reliability'], r['Constructor']))
    head_to_head = {}
    for (constructor, _), entries in shared.items():
        if set(entries) == {1, 822}:
            h, b = min(entries[1]), min(entries[822])
            totals = head_to_head.setdefault(constructor, [0, 0, 0])
            totals[0] += 1
            totals[1] += h < b
            totals[2] += b < h
    q3 = [{'Constructor': constructors[c], 'Shared_Races': n, 'Hamilton_Ahead': h, 'Bottas_Ahead': b} for c, (n, h, b) in head_to_head.items()]
    q3.sort(key=lambda r: r['Constructor'])
    q4 = [{'Driver': name(d), 'Starts': len(starts), 'Avg_Finish': round(sum(positions) / len(positions), 6), 'Wins': wins}
          for d, (starts, positions, wins) in monaco.items() if len(starts) >= 5]
    q4.sort(key=lambda r: (r['Avg_Finish'], -r['Wins'], r['Driver']))
    selected = {key: min(counts, key=lambda c: (-counts[c], c)) for key, counts in primary.items()}
    changed = [d for d in drivers if (d, 2020) in selected and (d, 2021) in selected and selected[d, 2020] != selected[d, 2021]]
    changed.sort(key=lambda d: (name(d), d))
    q5 = [{'Drivers_Changed': len(changed), 'Drivers': [name(d) for d in changed]}]
    return [q1, q2, q3, q4, q5]
