"""Archive integrity tests do not need network access."""
import io
from pathlib import Path
import tempfile
import unittest
import zipfile
from download_data import install_archive


class DownloadTests(unittest.TestCase):
    def test_corrupt_archive_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(zipfile.BadZipFile):
                install_archive(b'not an archive', Path(temp))
            self.assertEqual(list(Path(temp).iterdir()), [])

    def test_wrong_dataset_rejected_before_writes(self):
        content = io.BytesIO()
        with zipfile.ZipFile(content, 'w') as archive:
            archive.writestr('circuits.csv', 'circuitId\n999\n')
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                install_archive(content.getvalue(), Path(temp))
            self.assertEqual(list(Path(temp).iterdir()), [])
