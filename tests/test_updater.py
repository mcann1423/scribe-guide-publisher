import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from updater import ASSET_NAME, Release, check_for_update, download_installer, latest_release


class Response:
    def __init__(self, data): self.data, self.offset = data, 0
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, count=-1):
        if count < 0: count = len(self.data) - self.offset
        result = self.data[self.offset:self.offset + count]; self.offset += len(result); return result


def release_data(version='9.9.9', asset_url=None, size=4, digest=None):
    asset = {'name': ASSET_NAME, 'browser_download_url': asset_url or 'https://github.com/mcann1423/scribe-guide-publisher/releases/download/v'+version+'/'+ASSET_NAME, 'size': size}
    if digest: asset['digest'] = digest
    return json.dumps({'tag_name': 'v'+version, 'assets': [asset]}).encode('utf-8')


class UpdateTests(unittest.TestCase):
    def test_detects_newer_release(self):
        response = release_data()
        found = check_for_update(lambda request, timeout: Response(response))
        self.assertEqual(found.version, '9.9.9')

    def test_rejects_unexpected_asset_url(self):
        response = release_data(asset_url='https://example.test/'+ASSET_NAME)
        with self.assertRaises(ValueError): latest_release(lambda request, timeout: Response(response))

    def test_download_verifies_size_and_digest(self):
        data = b'installer bytes'
        checksum = hashlib.sha256(data).hexdigest()
        release = Release('9.9.9', 'https://github.com/mcann1423/scribe-guide-publisher/releases/download/v9.9.9/'+ASSET_NAME, len(data), checksum)
        with tempfile.TemporaryDirectory() as folder:
            result = download_installer(release, Path(folder), lambda request, timeout: Response(data))
            self.assertEqual(result.suffix, '.exe')
            self.assertEqual(result.read_bytes(), data)

    def test_download_rejects_size_mismatch(self):
        release = Release('9.9.9', 'https://github.com/mcann1423/scribe-guide-publisher/releases/download/v9.9.9/'+ASSET_NAME, 99)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError): download_installer(release, Path(folder), lambda request, timeout: Response(b'bad'))
            self.assertEqual(list(Path(folder).iterdir()), [])


if __name__ == '__main__': unittest.main()
