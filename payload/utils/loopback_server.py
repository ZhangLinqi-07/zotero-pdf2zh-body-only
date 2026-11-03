# SPDX-License-Identifier: AGPL-3.0-only
"""Serve the loopback backend without a reverse-DNS lookup during binding."""
from socketserver import TCPServer
from werkzeug.serving import ThreadedWSGIServer


class LoopbackWSGIServer(ThreadedWSGIServer):
    def server_bind(self):
        if self.server_address[0] != '127.0.0.1':
            return super().server_bind()
        # HTTPServer.server_bind resolves getfqdn before it calls listen. A
        # launch agent must not need network discovery to serve localhost.
        TCPServer.server_bind(self)
        self.server_name = '127.0.0.1'
        self.server_port = self.server_address[1]
