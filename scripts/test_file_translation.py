import json
import tempfile
import threading
import unittest
from pathlib import Path

from file_translation import exchange


class FileTranslationTests(unittest.TestCase):
    def test_handoff_and_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            results = []
            worker = threading.Thread(target=lambda: results.append(exchange(root, [{"role": "user", "content": "Hello"}], "zh-CN", 3)))
            worker.start()
            import time
            deadline = time.monotonic() + 2
            while not list(root.glob('*.request.json')) and time.monotonic() < deadline:
                time.sleep(0.01)
            request = next(root.glob('*.request.json'))
            response = request.with_name(request.name.replace('.request.json', '.response.json'))
            response.write_text(json.dumps({"text": "你好"}), encoding='utf-8')
            worker.join(3)
            self.assertFalse(worker.is_alive())
            self.assertEqual(results, ['你好'])
            self.assertEqual(exchange(root, [{"role": "user", "content": "Hello"}], "zh-CN", 0), '你好')
            with self.assertRaises(TimeoutError):
                exchange(root, [{"role": "user", "content": "Hello"}], "ja", 0)

    def test_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(TimeoutError):
                exchange(directory, [], 'zh-CN', 0)


if __name__ == '__main__':
    unittest.main()
