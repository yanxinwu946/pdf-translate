import json
import tempfile
import unittest
from pathlib import Path
from queue_status import inventory


class QueueStatusTests(unittest.TestCase):
    def test_missing_invalid_and_reused_responses(self):
        with tempfile.TemporaryDirectory() as directory:
            q = Path(directory)
            for name in ['a', 'b', 'c']:
                (q / (name + '.request.json')).write_text('{}', encoding='utf-8')
            (q / 'b.response.json').write_text('{broken', encoding='utf-8')
            (q / 'c.response.json').write_text(json.dumps({'text': '原文'}), encoding='utf-8')
            requests, pending, invalid = inventory(q)
            self.assertEqual(len(requests), 3)
            self.assertEqual([p.name for p in pending], ['a.request.json'])
            self.assertEqual([p.name for p in invalid], ['b.request.json'])


if __name__ == '__main__':
    unittest.main()
