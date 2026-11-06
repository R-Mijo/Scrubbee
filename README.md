![Product banner](docs/assets/banner.svg)

# Scrubbee

**Keep the details yours.**

Scrubbee automatically prepares text and supported Word documents for sharing. With the optional local English model installed, it detects person names without requiring a manual name list. It replaces detected details with consistent placeholders, then can restore them locally later.

**0.3.0 | Python 3.11+ | Proprietary | Optional local English name recognition**

## In plain English

Scrubbee helps prepare private text for sharing. It replaces detected identifiers and terms you add with placeholders, then can restore the original details when a reply comes back. For example, you can replace an email and a member name before pasting a note into another service. Pattern detection can miss details: review the output and keep restoration maps private.

## Automatic names and document preparation

Run **Install Automatic Names.cmd** once on Windows, then **Start Scrubbee.cmd**. Or follow [automatic setup](docs/AUTOMATION.md) on macOS/Linux. After setup, dropping a supported document or pasting text starts preparation automatically. Review the copy, then save it. The optional model is local; content is not sent to a model service. Names can be missed or misclassified.

Custom names are optional additions. Placeholders are reversible redaction, not encryption; restoration maps remain private plaintext.

## Open the local app

On Windows, double-click **Start Scrubbee.cmd**, or run from this folder:

```sh
python -m scrubbee ui
```

The interface opens at `http://127.0.0.1:8765`. Drag in a supported file or paste text, add names/custom identifiers, prepare it, then review and save. Save the private restoration map to restore details after closing the page. Ctrl+C stops the local server.

No account, model API, analytics or external web assets are used during document processing. Installing the optional English model requires an initial download. The local server processes content in memory without saving submitted files. Browser downloads happen only when you choose to save them.

## Supported content

- UTF-8 `.txt`, `.md`, `.csv` and `.log` files.
- Text-only `.docx`, including identifiers split across formatting runs, headers, footers, comments and deleted text.
- Common SSN, Medicare ID, email, US phone, IPv4, selected API-key and Luhn-valid card patterns, plus names/terms you explicitly provide.
- Removal of Word core properties, listed company/manager fields, custom properties/custom XML, thumbnails, hidden document variables, coauthor data, Word author/date attributes and original ZIP metadata.

**Review every export. Pattern matching can miss information.** English PERSON entities can be detected by the optional local model. Birth dates, addresses and arbitrary member/account numbers are not comprehensively understood; supply custom terms where needed and inspect the result. This is pseudonymization assistance, not a guarantee of anonymization or healthcare compliance.

PDFs, images, binary files, encrypted documents, macros, signed documents, charts, embedded media/files, unrecognized document parts and external document links are rejected. Removing custom XML/bindings and document variables may affect data-bound features. Keep the original and inspect the exported copy.

## Private restoration maps

Maps contain the original values. Keep them on your computer; do not upload them with prepared files or commit them to GitHub. Exported maps are plaintext, not encrypted. Files are created exclusively with restrictive POSIX permissions where supported; Windows uses the containing folder's permissions.

Each session has a random placeholder namespace. Restoration uses one pass to prevent cascading. Originals and prior exports/maps are never overwritten. Default export filenames are generic so the source filename is not copied into a shared file.

## Command line

```sh
python -m scrubbee demo
python -m scrubbee scrub note.txt --name "Avery Example"
python -m scrubbee scrub note.docx --out prepared.docx --vault private-map.json
python -m scrubbee restore reply.txt --vault private-map.json --out restored-private.txt
python -m unittest discover -s tests -v
```

Install with `python -m pip install .` to use the `scrubbee` command. `scrubbee_cli.py` is a convenience launcher without the old module-name conflict.

HTTP binds only to loopback, validates Host/Origin, requires a session token, limits sizes and disables caching. This is a personal local utility, not a shared service or protection from malware running as you.

Created by Marco A. [License](LICENSE) Â· [Contributing](CONTRIBUTING.md)

## Ownership and permitted access

Copyright (c) 2026 Marco Armijo (R-Mijo). **All rights reserved.** This is proprietary software with publicly visible source, not an open-source release. GitHub viewing and forking rights still apply. Repository access alone grants no license to run, copy, modify, distribute, host or commercialize it. Permission requires a separate written agreement signed by the owner. See [LICENSE](LICENSE). SlipSavvy is a separate Apache-2.0 project.
