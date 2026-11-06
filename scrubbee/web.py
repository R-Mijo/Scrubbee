# Copyright (c) 2026 Marco Armijo (R-Mijo). All rights reserved.
# SPDX-License-Identifier: LicenseRef-Proprietary
"""Loopback-only local UI. No telemetry, outbound requests or server-side file storage."""
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import webbrowser
import zipfile
import xml.etree.ElementTree as ET

from .core import MAX_BYTES, ScrubVault, scrub_text, scrub_bytes, restore_text
from .names import available


def create_ui_server(port=8765):
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError('Port must be between 0 and 65535')
    token = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(24)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Never log submitted text, mappings, or filenames.

        def _host_ok(self):
            return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

        def _send(self, status, payload, html=False):
            data = payload.encode('utf8') if html else json.dumps(payload).encode('utf8')
            self.send_response(status)
            self.send_header('Content-Type', 'text/html; charset=utf-8' if html else 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Connection', 'close')
            self.send_header('Content-Security-Policy', f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if not self._host_ok():
                return self._send(403, {'error': 'Unexpected host'})
            if self.path != '/':
                return self._send(404, {'error': 'Not found'})
            page = Path(__file__).with_name('ui.html').read_text(encoding='utf8')
            self._send(200, page.replace('__NONCE__', nonce).replace('__TOKEN__', token).replace('__NAMES_AVAILABLE__', 'true' if available() else 'false'), html=True)

        def do_POST(self):
            origin = f'http://127.0.0.1:{self.server.server_port}'
            if (not self._host_ok() or self.headers.get('X-Scrubbee-Token') != token
                    or self.headers.get('Origin', origin) != origin
                    or self.headers.get('Sec-Fetch-Site') == 'cross-site'):
                return self._send(403, {'error': 'Local session authorization required'})
            if self.headers.get_content_type() != 'application/json':
                return self._send(415, {'error': 'JSON content required'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= MAX_BYTES * 3 // 2:
                    return self._send(413, {'error': 'Request exceeds size limit'})
                self.connection.settimeout(10)
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError('Incomplete request')
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    raise ValueError('Request must be an object')
                if self.path == '/api/scrub':
                    terms = payload.get('custom_terms', [])
                    auto_names = payload.get('auto_names', False)
                    if type(auto_names) is not bool:
                        raise ValueError('Automatic names must be true or false')
                    if 'file_base64' in payload:
                        filename = payload.get('filename')
                        if not isinstance(filename, str) or len(filename) > 255:
                            raise ValueError('Filename required')
                        data = base64.b64decode(payload['file_base64'], validate=True)
                        output, report, vault = scrub_bytes(filename, data, custom_terms=terms, auto_names=auto_names)
                        response = dict(report, file_base64=base64.b64encode(output).decode('ascii'),
                                        filename='prepared-' + vault.session_id[:8] + Path(filename).suffix.lower())
                        if Path(filename).suffix.lower() != '.docx':
                            response['scrubbed_text'] = output.decode('utf8')
                    else:
                        report = scrub_text(payload.get('text'), custom_terms=terms, auto_names=auto_names)
                        vault = report.vault
                        response = {'scrubbed_text': report.scrubbed_text, 'redactions_count': report.redactions_count,
                                    'counts_by_type': report.counts_by_type}
                    response['vault'] = vault.to_dict()
                    response['automatic_names'] = auto_names
                    self._send(200, response)
                elif self.path == '/api/restore':
                    vault = ScrubVault.from_dict(payload.get('vault'))
                    text = payload.get('text')
                    if not isinstance(text, str) or len(text.encode('utf8')) > MAX_BYTES:
                        raise ValueError('Text exceeds size limit')
                    self._send(200, {'restored_text': restore_text(text, vault)})
                else:
                    self._send(404, {'error': 'Unknown endpoint'})
            except (ValueError, TypeError, UnicodeError, zipfile.BadZipFile, ET.ParseError, OSError) as error:
                self._send(400, {'error': str(error)})

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    server.session_token = token  # For trusted local clients and integration tests.
    return server


def serve(port=8765, open_browser=True):
    with create_ui_server(port) as server:
        url = f'http://127.0.0.1:{server.server_port}/'
        print(f'Scrubbee is local at {url} — Ctrl+C stops it. No submitted files are saved by the server.')
        if open_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
