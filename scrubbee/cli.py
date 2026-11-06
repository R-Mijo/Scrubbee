# Copyright (c) 2026 Marco Armijo (R-Mijo). All rights reserved.
# SPDX-License-Identifier: LicenseRef-Proprietary
import argparse
import json
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET
from .core import ScrubVault, scrub_file, scrub_text, restore_text, _write_new

def main(argv=None):
    parser = argparse.ArgumentParser(description='Scrubbee: prepare content locally; review before sharing')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('demo')
    scrub = sub.add_parser('scrub')
    scrub.add_argument('file', type=Path)
    scrub.add_argument('--out', type=Path)
    scrub.add_argument('--vault', type=Path)
    scrub.add_argument('--name', action='append', default=[])
    scrub.add_argument('--auto-names', action='store_true', help='Detect English person names using the installed local model')
    restore = sub.add_parser('restore')
    restore.add_argument('file', type=Path)
    restore.add_argument('--vault', required=True, type=Path)
    restore.add_argument('--out', required=True, type=Path)
    ui = sub.add_parser('ui')
    ui.add_argument('--port', type=int, default=8765)
    ui.add_argument('--no-browser', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'demo':
            raw = 'Example: Avery Example, email avery@example.invalid, SSN 123-45-6789.'
            report = scrub_text(raw, custom_terms=['Avery Example'])
            print(json.dumps({'synthetic_input': raw, 'scrubbed': report.scrubbed_text,
                              'restored': restore_text(report.scrubbed_text, report.vault),
                              'notice': 'Pattern detection is incomplete. Review before sharing.'}, indent=2))
        elif args.command == 'scrub':
            print(json.dumps(scrub_file(args.file, args.out, args.vault, args.name, auto_names=args.auto_names), indent=2))
        elif args.command == 'restore':
            restored = restore_text(args.file.read_text(encoding='utf8'), ScrubVault.load(args.vault))
            _write_new(args.out, restored.encode('utf8'))
            print(f'Restored locally: {args.out}')
        else:
            from .web import serve
            serve(args.port, open_browser=not args.no_browser)
        return 0
    except (ValueError, OSError, UnicodeError, zipfile.BadZipFile, ET.ParseError) as error:
        parser.exit(2, f'Scrubbee: {error}\n')
