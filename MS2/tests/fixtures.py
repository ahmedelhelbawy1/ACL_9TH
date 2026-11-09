"""Small synthetic CSVs ONLY for tests; never a substitute for the MS1 data."""
import csv
from pathlib import Path
from Create_kg import TABLES, required_columns


def write_fixture(directory: Path) -> None:
    rows = {table.label: [] for table in TABLES}
    for driver_id, first, last in [(1, 'Lewis', 'Hamilton'), (822, 'Valtteri', 'Bottas'), (3, 'New', 'Driver'), (4, 'Old', 'Driver'), (5, 'Tie', 'Driver')]:
        rows['Driver'].append(dict(driverId=driver_id, driverRef=first, forename=first, surname=last, dob='1985-01-07', number='0'))
    rows['Constructor'] = [dict(constructorId=10, constructorRef='same_a', name='Same Name', nationality='British'),
                           dict(constructorId=20, constructorRef='same_b', name='Same Name', nationality='French')]
    rows['Circuit'] = [dict(circuitId=6, circuitRef='monaco', name='Monaco', location='Monte Carlo', country='Monaco', lat='43.73', lng='7.42', alt='0')]
    rows['Season'] = [dict(year=y) for y in (2010, 2013, 2014, 2020, 2021, 2022)]
    rows['Status'] = [dict(statusId=i, status=s) for i, s in enumerate(['Finished', '+1 Lap', 'Collision', 'Did not qualify', 'Did not prequalify', 'Withdrew'], 1)]
    for race_id in range(1, 6):
        rows['Race'].append(dict(raceId=race_id, year=2010, round=race_id, name='Monaco', date=f'2010-05-{race_id:02}', circuitId=6))
    for race_id, year in [(6, 2020), (7, 2021), (8, 2021), (9, 2014), (10, 2013), (11, 2022)]:
        rows['Race'].append(dict(raceId=race_id, year=year, round=1, name='Test', date=f'{year}-01-01', circuitId=6))

    def result(race, driver=1, constructor=10, position=2, status=1, points=0):
        rows['Result'].append(dict(resultId=len(rows['Result']) + 1, raceId=race, driverId=driver,
                                  constructorId=constructor, position=position, positionOrder=position,
                                  positionText=str(position), statusId=status, points=points, grid=0, laps=10))
    for race_id in range(1, 6):
        result(race_id, position=1, points=25)
        result(race_id, driver=822, position=2, points=18)
    result(1, position=5)  # shared drive: affects average, not start count
    for excluded in (4, 5, 6):
        result(1, position=99, status=excluded)
    result(6, driver=1, constructor=10)
    result(7, driver=1, constructor=20, position=1, points=25)
    result(7, driver=822, constructor=20, position=2, points=18)
    result(7, driver=1, constructor=20, position=3, points=1)  # count shared race once
    result(6, driver=822, constructor=20)
    result(8, driver=3, constructor=20, position=1, points=25)  # absent in 2020
    result(6, driver=4, constructor=10)  # absent in 2021
    result(6, driver=5, constructor=20)
    result(6, driver=5, constructor=10)  # tie => lower ID 10
    result(7, driver=5, constructor=20)  # change, even though name is identical
    for i in range(100):
        result(9, driver=3, constructor=10, status=1 if i < 70 else 2 if i < 90 else 3)
    result(10, driver=3, constructor=20)  # outside reliability date range
    result(11, driver=3, constructor=20)
    rows['Qualifying'] = [dict(qualifyId=1, raceId=7, driverId=1, constructorId=20, number=44, position=1, q1='1:10.000', q2='', q3='\\N')]
    rows['PitStop'] = [dict(raceId=7, driverId=1, stop=1, lap=10, time='14:10:00', duration='22.5', milliseconds=22500)]
    for table in TABLES:
        fields = sorted(required_columns(table))
        with (directory / table.filename).open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in rows[table.label]:
                writer.writerow({field: row.get(field, '\\N') for field in fields})
