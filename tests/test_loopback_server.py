# SPDX-License-Identifier: AGPL-3.0-only
import json
from pathlib import Path
import socket
import sys
import threading
import unittest
from unittest.mock import patch
import urllib.request
from flask import Flask
from werkzeug.serving import WSGIRequestHandler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'payload'))
from utils.loopback_server import LoopbackWSGIServer


class LoopbackServerTests(unittest.TestCase):
    def test_flask_serves_existing_routes_when_reverse_dns_is_unavailable(self):
        app = Flask(__name__)
        app.add_url_rule('/health', 'health', lambda: {'status': 'success'})
        class Quiet(WSGIRequestHandler):
            def log(self, *args, **kwargs):
                pass
        with patch.object(socket, 'getfqdn', side_effect=AssertionError('Loopback startup must not query DNS')):
            server = LoopbackWSGIServer('127.0.0.1', 0, app, handler=Quiet)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            local = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with local.open(f'http://127.0.0.1:{server.server_port}/health', timeout=3) as response:
                self.assertEqual(json.load(response), {'status': 'success'})
        finally:
            server.shutdown(); thread.join(timeout=3); server.server_close()


if __name__ == '__main__':
    unittest.main()
