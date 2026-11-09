"""Download the verified MS1 source, pinned to Kaggle version 24."""
from __future__ import annotations
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
from urllib.error import URLError
from urllib.request import Request, urlopen
import zipfile

from Create_kg import BASE_DIR, validate_csv_files


def install_archive(archive: bytes, directory: Path = BASE_DIR) -> None:
    """Check all hashes and references before placing any CSV beside the script."""
    manifest = json.loads((BASE_DIR / 'data_manifest.json').read_text(encoding='utf-8'))
    with tempfile.TemporaryDirectory() as temp:
        staging = Path(temp)
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            for filename, expected in manifest['files'].items():
                content = zipped.read(filename)
                if hashlib.sha256(content).hexdigest() != expected['sha256']:
                    raise ValueError(f'{filename}: checksum mismatch; refusing a different dataset')
                destination = directory / filename
                if destination.exists() and destination.read_bytes() != content:
                    raise ValueError(f'{filename}: existing file differs; move it aside before retrying')
                (staging / filename).write_bytes(content)
        validate_csv_files(staging)
        for filename in manifest['files']:
            shutil.copyfile(staging / filename, directory / filename)
    print('Installed all nine verified version-24 CSVs beside Create_kg.py.')


def main() -> int:
    manifest = json.loads((BASE_DIR / 'data_manifest.json').read_text(encoding='utf-8'))
    try:
        request = Request(manifest['download_url'], headers={'User-Agent': 'ACL-MS2/1.0'})
        with urlopen(request, timeout=120) as response:
            install_archive(response.read())
        return 0
    except (URLError, OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        print(f'Download failed ({type(exc).__name__}): {exc}', file=sys.stderr)
        print('Use the version-24 Kaggle download listed in README.md and place the nine raw CSVs alongside Create_kg.py.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
