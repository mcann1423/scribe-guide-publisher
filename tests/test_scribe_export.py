import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scribe_export import guide_filename, is_scribe_url


class ScribeExportTests(unittest.TestCase):
    def test_accepts_only_scribe_viewer_urls(self):
        self.assertTrue(is_scribe_url('https://scribehow.com/viewer/How_to_export__abc'))
        self.assertTrue(is_scribe_url('https://scribehow.com/o/example/viewer/How_to_export__abc'))
        for url in ('https://scribehow.com/workspace', 'http://scribehow.com/viewer/x', 'https://example.com/viewer/x', 'https://scribehow.com/o/example/page/x'):
            with self.subTest(url=url): self.assertFalse(is_scribe_url(url))

    def test_filename_is_simple_and_unique(self):
        used = set()
        self.assertEqual(guide_filename('Report Spam in Gmail', used), 'report-spam-in-gmail.html')
        self.assertEqual(guide_filename('Report Spam in Gmail', used), 'report-spam-in-gmail-2.html')
        self.assertEqual(guide_filename('!!!', used), 'scribe-guide.html')


if __name__ == '__main__': unittest.main()
