# Copyright (c) 2026 Marco Armijo (R-Mijo). All rights reserved.
# SPDX-License-Identifier: LicenseRef-Proprietary
"""Local pattern-assisted pseudonymization. Detection is deliberately not exhaustive."""
from __future__ import annotations
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import wraps
from io import BytesIO
import json
import os
import posixpath
from pathlib import Path
import re
import secrets
from threading import RLock
import zipfile
import xml.etree.ElementTree as ET

MAX_BYTES = 20 * 1024 * 1024
TEXT_SUFFIXES = {'.txt', '.md', '.csv', '.log'}
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
TEXT_TAGS = {f'{{{W}}}{name}' for name in ('t', 'delText', 'instrText')} | {f'{{{A}}}t'}
PATTERNS = [
    ('API_KEY', re.compile(r'\b(?:sk-[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{35}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b')),
    ('EMAIL', re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b')),
    ('SSN', re.compile(r'\b\d{3}[- ]\d{2}[- ]\d{4}\b')),
    ('MEDICARE_ID', re.compile(r'\b[1-9][A-NP-RT-Y][A-NP-RT-Y0-9]\d[- ]?[A-NP-RT-Y][A-NP-RT-Y0-9]\d[- ]?[A-NP-RT-Y]{2}\d{2}\b', re.I)),
    ('CREDIT_CARD', re.compile(r'(?<!\w)(?:\d[ -]?){12,18}\d(?!\w)')),
    ('PHONE', re.compile(r'(?<![\w])(?:\+?1[ .-]?)?(?:\(\d{3}\)[ .-]?|\d{3}[ .-])\d{3}[ .-]\d{4}(?!\w)')),
    ('IPV4', re.compile(r'\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b')),
]
TOKEN_RE = re.compile(r'\[\[SCRUB:[a-f0-9]{32}:[A-Z0-9_]+:\d+\]\]')
_XML_LOCK = RLock()


def _serialized_xml(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        # ElementTree's namespace registry is global; serialize our DOCX work.
        with _XML_LOCK:
            return function(*args, **kwargs)
    return wrapper


def _write_new(path, data):
    """Never replace an original, existing export, symlink or previous vault."""
    target = Path(path)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
    except BaseException:
        target.unlink(missing_ok=True)
        raise


@dataclass
class ScrubVault:
    session_id: str = field(default_factory=lambda: secrets.token_hex(16))
    token_to_raw: dict[str, str] = field(default_factory=dict)
    raw_to_token: dict[str, str] = field(default_factory=dict)
    counts_by_type: dict[str, int] = field(default_factory=dict)

    def token(self, category, raw):
        if raw in self.raw_to_token:
            return self.raw_to_token[raw]
        index = self.counts_by_type.get(category, 0) + 1
        self.counts_by_type[category] = index
        token = f'[[SCRUB:{self.session_id}:{category}:{index}]]'
        self.raw_to_token[raw] = token
        self.token_to_raw[token] = raw
        return token

    def to_dict(self):
        return {'format': 1, 'session_id': self.session_id,
                'token_to_raw': dict(self.token_to_raw), 'counts_by_type': dict(self.counts_by_type)}

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or data.get('format') != 1:
            raise ValueError('Unsupported restoration map')
        session = data.get('session_id')
        mapping = data.get('token_to_raw')
        counts = data.get('counts_by_type')
        if not isinstance(session, str) or not re.fullmatch('[a-f0-9]{32}', session):
            raise ValueError('Invalid restoration session')
        if not isinstance(mapping, dict) or not isinstance(counts, dict):
            raise ValueError('Invalid restoration mapping')
        for token, raw in mapping.items():
            if not isinstance(token, str) or not TOKEN_RE.fullmatch(token) or f':{session}:' not in token or not isinstance(raw, str):
                raise ValueError('Invalid restoration entry')
        if len(set(mapping.values())) != len(mapping):
            raise ValueError('Duplicate restoration values')
        for cat, count in counts.items():
            if not isinstance(cat, str) or not re.fullmatch('[A-Z0-9_]+', cat) or type(count) is not int or count < 0:
                raise ValueError('Invalid token counters')
        for token in mapping:
            _, _, category, number = token[2:-2].split(':')
            if counts.get(category, 0) < int(number):
                raise ValueError('Restoration map counters are inconsistent')
        return cls(session, dict(mapping), {v: k for k, v in mapping.items()}, dict(counts))

    def save(self, path):
        # Sensitive plaintext. Mode 0600 on POSIX; Windows inherits directory ACLs.
        _write_new(path, json.dumps(self.to_dict(), indent=2).encode('utf8'))

    @classmethod
    def load(cls, path):
        content = Path(path).read_bytes()
        if len(content) > MAX_BYTES:
            raise ValueError('Restoration map exceeds size limit')
        return cls.from_dict(json.loads(content))


@dataclass(frozen=True)
class Finding:
    start: int
    end: int
    category: str
    replacement: str


@dataclass
class ScrubReport:
    scrubbed_text: str
    findings: list[Finding]
    counts_by_type: dict[str, int]
    vault: ScrubVault

    @property
    def redactions_count(self):
        return len(self.findings)


def _luhn(raw):
    digits = [int(c) for c in raw if c.isdigit() and c.isascii()]
    if not 13 <= len(digits) <= 19 or len(set(digits)) == 1:
        return False
    total = 0
    for i, value in enumerate(reversed(digits)):
        if i % 2:
            value *= 2
            value = value - 9 if value > 9 else value
        total += value
    return total % 10 == 0


def scrub_text(text, vault=None, custom_terms=None):
    if not isinstance(text, str) or len(text.encode('utf8')) > MAX_BYTES:
        raise ValueError('Text must be UTF-8 text within the 20 MiB limit')
    terms = custom_terms if custom_terms is not None else []
    if not isinstance(terms, (tuple, list)) or len(terms) > 100 or any(not isinstance(t, str) or len(t) > 200 for t in terms):
        raise ValueError('Provide at most 100 custom terms of up to 200 characters')
    v = vault if vault is not None else ScrubVault()
    candidates = []
    # Find against the original text once: generated tokens cannot be redacted.
    patterns = [('CUSTOM', re.compile(re.escape(t.strip()), re.I)) for t in terms if t.strip()] + PATTERNS
    protected = [(m.start(), m.end()) for m in TOKEN_RE.finditer(text)]
    for priority, (category, pattern) in enumerate(patterns):
        for match in pattern.finditer(text):
            if category == 'CREDIT_CARD' and not _luhn(match.group()):
                continue
            if any(a < match.end() and b > match.start() for a, b in protected):
                continue
            candidates.append((match.start(), match.end(), priority, category))
    findings = []
    cursor = 0
    for start, end, _, category in sorted(candidates, key=lambda x: (x[0], -(x[1] - x[0]), x[2])):
        if start < cursor:
            continue
        findings.append(Finding(start, end, category, v.token(category, text[start:end])))
        cursor = end
    pieces = []
    cursor = 0
    for finding in findings:
        pieces.extend((text[cursor:finding.start], finding.replacement))
        cursor = finding.end
    pieces.append(text[cursor:])
    return ScrubReport(''.join(pieces), findings, dict(Counter(f.category for f in findings)), v)


def restore_text(text, vault):
    if not isinstance(text, str) or not isinstance(vault, ScrubVault):
        raise ValueError('Text and restoration map are required')
    # One substitution pass prevents cascade when a raw value looks like a token.
    return TOKEN_RE.sub(lambda m: vault.token_to_raw.get(m.group(), m.group()), text)


def _parse_xml(data):
    data.decode('utf-8-sig', errors='strict')
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('DTD/entity XML is unsupported')
    namespaces = dict((prefix or '', uri) for _, (prefix, uri) in ET.iterparse(BytesIO(data), events=['start-ns']))
    for prefix, uri in namespaces.items():
        if not re.fullmatch(r'ns\d+', prefix):
            ET.register_namespace(prefix, uri)
    return ET.fromstring(data), namespaces


def _serialize(root, namespaces):
    encoded = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    # Preserve declarations referenced by markup-compatibility attribute values.
    for prefix, uri in namespaces.items():
        attr = 'xmlns' + (f':{prefix}' if prefix else '')
        if (attr + '=').encode() not in encoded:
            root.set(attr, uri)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def _scrub_nodes(nodes, vault, terms):
    raw = ''.join(node.text or '' for node in nodes)
    report = scrub_text(raw, vault, terms)
    position = 0
    for node in nodes:
        value = node.text or ''
        end = position + len(value)
        pieces = []
        cursor = position
        for f in report.findings:
            if f.end <= position or f.start >= end:
                continue
            pieces.append(raw[cursor:max(cursor, f.start)])
            if position <= f.start < end:
                pieces.append(f.replacement)
            cursor = min(end, f.end)
        pieces.append(raw[cursor:end])
        node.text = ''.join(pieces)
        position = end
    return report.counts_by_type


@_serialized_xml
def scrub_docx_bytes(data, vault=None, custom_terms=None):
    if len(data) > MAX_BYTES:
        raise ValueError('Document exceeds 20 MiB limit')
    v = vault if vault is not None else ScrubVault()
    counts = Counter()
    result = BytesIO()
    with zipfile.ZipFile(BytesIO(data)) as zin:
        names = zin.namelist()
        if len(names) != len(set(names)) or len(names) > 2000 or 'word/document.xml' not in names:
            raise ValueError('Not a supported Word document')
        if sum(info.file_size for info in zin.infolist()) > MAX_BYTES:
            raise ValueError('Expanded document exceeds 20 MiB limit')
        dropped = {name for name in names if name == 'docProps/custom.xml'
                   or name.startswith('customXml/') or name.lower().startswith('docprops/thumbnail.')
                   or name in {'word/people.xml', 'word/commentsExtended.xml',
                               'word/commentsIds.xml', 'word/commentsExtensible.xml'}}
        supported = re.compile(r'(?:\[Content_Types\]\.xml|_rels/\.rels|docProps/(?:core|app)\.xml|'
                               r'word/(?:document|styles|stylesWithEffects|numbering|settings|webSettings|fontTable|'
                               r'footnotes|endnotes|comments|header\d+|footer\d+)\.xml|'
                               r'word/theme/theme\d+\.xml|word/_rels/[^/]+\.rels)')
        for info in zin.infolist():
            name = info.filename.lower()
            if info.flag_bits & 1 or name.startswith('/') or '..' in name.split('/'):
                raise ValueError('Encrypted or unsafe archive member')
            if any(x in name for x in ('/media/', '/embeddings/', 'vbaproject', '_xmlsignatures/')):
                raise ValueError('Documents with images, embedded files, macros or signatures are unsupported; use a text-only copy')
            if name.endswith('/'):
                continue
            if info.filename not in dropped and not supported.fullmatch(info.filename):
                raise ValueError(f'Unsupported Word part cannot be inspected: {info.filename}')
            if not (name.endswith('.xml') or name.endswith('.rels') or name.startswith('docprops/thumbnail.')):
                raise ValueError(f'Unsupported document part: {info.filename}')
        with zipfile.ZipFile(result, 'w', zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                name = info.filename
                if name.endswith('/') or name in dropped:
                    continue
                root, ns = _parse_xml(zin.read(name))
                if name.endswith('.rels'):
                    for relation in list(root):
                        if relation.get('TargetMode', '').lower() == 'external':
                            raise ValueError('External document links are unsupported; remove them before export')
                        target = relation.get('Target', '')
                        relative_base = '' if name == '_rels/.rels' else posixpath.dirname(posixpath.dirname(name))
                        part = posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join(relative_base, target))
                        if part in dropped or relation.get('Type', '').endswith(('/custom-properties', '/customXml', '/metadata/thumbnail')):
                            root.remove(relation)
                if name == '[Content_Types].xml':
                    for item in list(root):
                        if item.get('PartName', '').lstrip('/') in dropped:
                            root.remove(item)
                if name == 'docProps/core.xml':
                    root.clear()  # Remove all core metadata, not just an author label.
                elif name == 'docProps/app.xml':
                    for item in root.iter():
                        if item.tag.rsplit('}', 1)[-1] in {'Company', 'Manager', 'Template', 'HyperlinkBase'}:
                            item.text = ''
                else:
                    groups = defaultdict(list)
                    def visit(node, paragraph=None):
                        if node.tag in {f'{{{W}}}p', f'{{{A}}}p'}:
                            paragraph = node
                        if node.tag in TEXT_TAGS:
                            groups[paragraph if paragraph is not None else node].append(node)
                        for attr in list(node.attrib):
                            if attr.rsplit('}', 1)[-1] in {'author', 'initials'}:
                                node.attrib[attr] = ''
                            elif attr.rsplit('}', 1)[-1] == 'date' or attr.rsplit('}', 1)[-1].startswith('rsid'):
                                del node.attrib[attr]
                            elif node.tag.rsplit('}', 1)[-1] in {'docPr', 'cNvPr'} and attr in {'name', 'descr', 'title'}:
                                node.attrib[attr] = 'ScrubbeeObject' if attr == 'name' else ''
                        for child in list(node):
                            if child.tag in {f'{{{W}}}{local}' for local in ('dataBinding', 'docVars', 'mailMerge', 'rsids')}:
                                node.remove(child)
                        for child in node:
                            visit(child, paragraph)
                    visit(root)
                    for nodes in groups.values():
                        counts.update(_scrub_nodes(nodes, v, custom_terms))
                # New ZipInfo prevents retaining original ZIP comments/timestamps.
                zout.writestr(name, _serialize(root, ns))
    return result.getvalue(), {'redactions_count': sum(counts.values()), 'counts_by_type': dict(counts),
                               'metadata_removed': ['core properties', 'company/manager/template fields', 'custom properties and custom XML', 'document thumbnails', 'Word author/date attributes', 'document variables and coauthor data', 'ZIP metadata']}, v


def scrub_bytes(filename, data, *, custom_terms=None):
    suffix = Path(filename).suffix.lower()
    if len(data) > MAX_BYTES:
        raise ValueError('File exceeds 20 MiB limit')
    if suffix == '.docx':
        return scrub_docx_bytes(data, custom_terms=custom_terms)
    if suffix not in TEXT_SUFFIXES:
        raise ValueError('Supported files: UTF-8 .txt, .md, .csv, .log and text-only .docx. PDF/images are not supported.')
    text = data.decode('utf-8-sig', errors='strict')
    if '\x00' in text:
        raise ValueError('Binary data is not a supported text file')
    report = scrub_text(text, custom_terms=custom_terms)
    return report.scrubbed_text.encode('utf8'), {'redactions_count': report.redactions_count,
                                               'counts_by_type': report.counts_by_type}, report.vault


def scrub_file(input_path, output_path=None, vault_path=None, custom_terms=None):
    source = Path(input_path)
    target = Path(output_path) if output_path else source.with_name('scrubbed-' + secrets.token_hex(4) + source.suffix.lower())
    vault_target = Path(vault_path) if vault_path else target.with_name(target.name + '.restore-' + secrets.token_hex(4) + '.json')
    if len({source.resolve(), target.resolve(), vault_target.resolve()}) != 3:
        raise ValueError('Input, output and restoration map must be different files')
    if target.exists() or vault_target.exists():
        raise FileExistsError('Export already exists; choose new output and restoration map names')
    if source.stat().st_size > MAX_BYTES:
        raise ValueError('File exceeds 20 MiB limit')
    output, report, vault = scrub_bytes(source.name, source.read_bytes(), custom_terms=custom_terms)
    # Write the sensitive map first. An output is never created without its map.
    vault.save(vault_target)
    try:
        _write_new(target, output)
    except BaseException:
        vault_target.unlink(missing_ok=True)
        raise
    return dict(report, output_file=str(target), restoration_map=str(vault_target))
