import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from session import TranslationServer, main


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.server = TranslationServer(self.directory.name, 'zh-CN', 1)
        self.worker = threading.Thread(target=self.server.serve_forever)
        self.worker.start()
        self.base = f'http://127.0.0.1:{self.server.server_address[1]}'
        self.client = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join()
        self.directory.cleanup()

    def test_health(self):
        with self.client.open(self.base + '/health') as response:
            self.assertEqual(json.load(response)['mode'], 'current-session')

    def test_current_session_response(self):
        payload = {'messages': [{'role': 'user', 'content': 'Hello'}]}
        request = urllib.request.Request(self.base + '/v1/chat/completions', data=json.dumps(payload).encode())
        with patch('session.exchange', return_value='你好') as exchange:
            with self.client.open(request) as response:
                self.assertEqual(json.load(response)['choices'][0]['message']['content'], '你好')
            self.assertEqual(exchange.call_args.args[1], payload['messages'])

    def test_reject_invalid_request(self):
        request = urllib.request.Request(self.base + '/v1/chat/completions', data=b'{"messages":[]}')
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.client.open(request)
        self.assertEqual(error.exception.code, 422)
        error.exception.close()

    def test_launcher_only_starts_layout_engine(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'paper.pdf'
            source.touch()
            with patch('sys.argv', ['session.py', str(source), '--fresh']), patch('session.shutil.which', return_value='pdf2zh_next'), patch('session.subprocess.call', return_value=0) as launch:
                self.assertEqual(main(), 0)
            self.assertEqual(launch.call_count, 1)
            command = launch.call_args.args[0]
            self.assertEqual(command[0], 'pdf2zh_next')
            self.assertIn('--ignore-cache', command)
            self.assertIn('current-session-v1', command)
            self.assertIn('127.0.0.1', launch.call_args.kwargs['env']['NO_PROXY'])


if __name__ == '__main__':
    unittest.main()
