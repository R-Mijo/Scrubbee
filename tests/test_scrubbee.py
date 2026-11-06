# Copyright (c) 2026 Marco Armijo (R-Mijo). All rights reserved.
# SPDX-License-Identifier: LicenseRef-Proprietary
import base64
from io import BytesIO
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import zipfile
import xml.etree.ElementTree as ET

from scrubbee.core import ScrubVault, scrub_text, restore_text, scrub_bytes, scrub_file, W
from scrubbee.web import create_ui_server


def docx(parts=None):
    defaults = {
        '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/docProps/custom.xml" ContentType="custom"/></Types>',
        '_rels/.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="c" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties" Target="docProps/custom.xml"/></Relationships>',
        'word/document.xml': f'<w:document xmlns:w="{W}"><w:body><w:p><w:r><w:t>Write to alice@</w:t></w:r><w:r><w:t>example.invalid or 123-</w:t></w:r><w:r><w:t>45-6789.</w:t></w:r></w:p></w:body></w:document>',
        'docProps/core.xml': '<c:coreProperties xmlns:c="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"><c:author>Private Author</c:author></c:coreProperties>',
        'docProps/app.xml': '<Properties><Company>Private Company</Company><Manager>Private Manager</Manager></Properties>',
        'docProps/custom.xml': '<Properties><Secret>Private custom property</Secret></Properties>',
    }
    defaults.update(parts or {})
    output = BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.comment = b'private ZIP comment'
        for name, content in defaults.items():
            archive.writestr(name, content)
    return output.getvalue()


class ScrubTests(unittest.TestCase):
    def test_patterns_roundtrip_and_repeated_identity(self):
        raw = ('Avery Example: avery@example.invalid; avery@example.invalid; 123-45-6789; '
               '1EG4-TE5-MK72; (602) 555-0199; 192.168.1.9; 4111 1111 1111 1111; sk-proj-abcdefghijklmnopqrstuvwxyz')
        result = scrub_text(raw, custom_terms=['Avery Example'])
        for fragment in ['avery@example.invalid', 'Avery Example', '123-45-6789', '1EG4-TE5-MK72', '4111 1111 1111 1111']:
            self.assertNotIn(fragment, result.scrubbed_text)
        self.assertEqual(result.redactions_count, 9)
        self.assertEqual(restore_text(result.scrubbed_text, result.vault), raw)
        self.assertEqual(len(result.vault.token_to_raw), 8)

    def test_longest_custom_match_and_no_token_rescrubbing(self):
        result = scrub_text('Avery Example uses avery@example.invalid', custom_terms=['Avery', 'Avery Example'])
        self.assertNotIn('Example', result.scrubbed_text)
        again = scrub_text(result.scrubbed_text, result.vault, ['SCRUB'])
        self.assertEqual(again.scrubbed_text, result.scrubbed_text)

    def test_restoration_is_single_pass(self):
        vault = ScrubVault()
        a = vault.token('CUSTOM', 'value')
        b = vault.token('CUSTOM', a)
        self.assertEqual(restore_text(b, vault), a)

    def test_validated_map_roundtrip_and_refuse_overwrite(self):
        vault = scrub_text('alice@example.invalid').vault
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'map.json'
            vault.save(path)
            self.assertEqual(ScrubVault.load(path).to_dict(), vault.to_dict())
            with self.assertRaises(FileExistsError):
                vault.save(path)
        data = vault.to_dict()
        data['counts_by_type'] = {}
        with self.assertRaises(ValueError):
            ScrubVault.from_dict(data)

    def test_docx_split_runs_and_metadata(self):
        output, report, vault = scrub_bytes('test.docx', docx())
        self.assertEqual(report['redactions_count'], 2)
        with zipfile.ZipFile(BytesIO(output)) as archive:
            self.assertEqual(archive.comment, b'')
            self.assertNotIn('docProps/custom.xml', archive.namelist())
            self.assertNotIn(b'Private', archive.read('docProps/core.xml'))
            self.assertNotIn(b'Private', archive.read('docProps/app.xml'))
            self.assertNotIn(b'custom-properties', archive.read('_rels/.rels'))
            xml = ET.fromstring(archive.read('word/document.xml'))
            combined = ''.join(n.text or '' for n in xml.iter(f'{{{W}}}t'))
            self.assertNotIn('alice@', combined)
            self.assertNotIn('123-45', combined)
            self.assertEqual(restore_text(combined, vault), 'Write to alice@example.invalid or 123-45-6789.')

    def test_headers_comments_and_tracked_author(self):
        header = f'<w:hdr xmlns:w="{W}"><w:p><w:r><w:t>secret@example.invalid</w:t></w:r></w:p></w:hdr>'
        comment = f'<w:comments xmlns:w="{W}"><w:comment w:author="Secret" w:date="2026"><w:p><w:r><w:delText>123-45-6789</w:delText></w:r></w:p></w:comment></w:comments>'
        output, report, _ = scrub_bytes('x.docx', docx({'word/header1.xml': header, 'word/comments.xml': comment}))
        self.assertEqual(report['redactions_count'], 4)
        with zipfile.ZipFile(BytesIO(output)) as archive:
            self.assertNotIn(b'secret@example', archive.read('word/header1.xml'))
            self.assertNotIn(b'Secret', archive.read('word/comments.xml'))
            ET.fromstring(archive.read('word/comments.xml'))

    def test_embedded_media_and_external_links_fail_closed(self):
        for parts in [
            {'word/media/image.png': b'not actually inspected'},
            {'word/embeddings/payload.bin': b'payload'},
            {'word/_rels/document.xml.rels': '<Relationships><Relationship TargetMode="External" Target="https://example.invalid"/></Relationships>'},
        ]:
            with self.subTest(parts=parts), self.assertRaises(ValueError):
                scrub_bytes('x.docx', docx(parts))

    def test_entity_archive_traversal_and_size_rejected(self):
        for parts in [
            {'word/document.xml': '<!DOCTYPE a [<!ENTITY x "boom">]><a>&x;</a>'},
            {'../private.xml': '<a/>'},
        ]:
            with self.assertRaises(ValueError):
                scrub_bytes('x.docx', docx(parts))
        with patch('scrubbee.core.MAX_BYTES', 1000), self.assertRaises(ValueError):
            scrub_bytes('x.docx', docx({'word/large.xml': '<a>' + 'x' * 10000 + '</a>'}))

    def test_unsupported_binary_and_bad_encoding(self):
        for filename, data in [('scan.pdf', b'%PDF-private'), ('image.png', b'png'), ('x.txt', b'abc\x00def'), ('x.txt', b'\xff')]:
            with self.subTest(filename=filename), self.assertRaises((ValueError, UnicodeError)):
                scrub_bytes(filename, data)

    def test_file_export_cannot_overwrite_input_or_prior_map(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'note.txt'
            source.write_text('alice@example.invalid')
            with self.assertRaises(ValueError):
                scrub_file(source, source)
            result = scrub_file(source)
            saved = Path(result['restoration_map'])
            self.assertTrue(saved.exists())
            self.assertEqual(source.read_text(), 'alice@example.invalid')
            with self.assertRaises(FileExistsError):
                scrub_file(source, result['output_file'])

    def test_thumbnails_and_custom_xml_are_removed(self):
        output, _, _ = scrub_bytes('x.docx', docx({'customXml/item1.xml': '<a>private</a>', 'docProps/thumbnail.jpeg': b'private image'}))
        with zipfile.ZipFile(BytesIO(output)) as archive:
            self.assertNotIn('customXml/item1.xml', archive.namelist())
            self.assertNotIn('docProps/thumbnail.jpeg', archive.namelist())


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = create_ui_server(0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'
        cls.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def request(self, route, payload=None, **headers):
        hdr = {'Content-Type': 'application/json', 'X-Scrubbee-Token': self.server.session_token, 'Origin': self.base}
        hdr.update(headers)
        body = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(self.base + route, body, hdr)
        return self.opener.open(request, timeout=5)

    def test_page_local_assets_and_headers(self):
        with self.request('/') as response:
            page = response.read().decode()
            self.assertIn('Keep the details yours', page)
            self.assertIn(self.server.session_token, page)
            self.assertIn("default-src 'none'", response.headers['Content-Security-Policy'])
            self.assertEqual(response.headers['Cache-Control'], 'no-store')

    def test_scrub_restore_and_file_routes(self):
        with self.request('/api/scrub', {'text': 'alice@example.invalid'}) as response:
            data = json.load(response)
        self.assertNotIn('alice@', data['scrubbed_text'])
        with self.request('/api/restore', {'text': data['scrubbed_text'], 'vault': data['vault']}) as response:
            self.assertEqual(json.load(response)['restored_text'], 'alice@example.invalid')
        with self.request('/api/scrub', {'filename': 'x.txt', 'file_base64': base64.b64encode(b'alice@example.invalid').decode()}) as response:
            self.assertIn('file_base64', json.load(response))

    def test_cross_origin_host_and_missing_token_denied(self):
        for headers in [{'Origin': 'https://attacker.invalid'}, {'Host': 'attacker.invalid'}, {'X-Scrubbee-Token': ''}]:
            with self.subTest(headers=headers), self.assertRaises(urllib.error.HTTPError) as caught:
                self.request('/api/scrub', {'text': 'hello'}, **headers)
            self.assertEqual(caught.exception.code, 403)

    def test_unsupported_format_and_wrong_payload_return_errors(self):
        for payload in [[], {'filename': 'x.pdf', 'file_base64': 'JVBERg=='}, {'text': 4}]:
            with self.subTest(payload=payload), self.assertRaises(urllib.error.HTTPError) as caught:
                self.request('/api/scrub', payload)
            self.assertEqual(caught.exception.code, 400)


if __name__ == '__main__':
    unittest.main()
