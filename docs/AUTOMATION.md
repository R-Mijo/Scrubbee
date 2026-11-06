# Automatic document preparation

Scrubbee 0.3.0 can automatically prepare a supported file when it is selected or dropped into the local app, and prepare pasted text after a short pause. Review and download are deliberate actions. Names no longer need to be typed one by one when the English recognition model is installed.

## One-time local setup

Use Python 3.11 or newer. In the repository folder:

```sh
python -m venv .venv
```

On Windows, run `Install Automatic Names.cmd`, then `Start Scrubbee.cmd`. The installer creates its own environment, installs the optional names package and downloads the English model. On macOS/Linux:

```sh
.venv/bin/python -m pip install '.[names]'
.venv/bin/python -m spacy download en_core_web_sm
.venv/bin/python -m scrubbee ui
```

Installation needs internet. Subsequent name recognition is local. The checkbox says whether the installed model is available; a requested name scan fails visibly if its model cannot load. It never silently downgrades a requested name scan to pattern matching.

## Daily workflow

1. Open the local app. Automatic names and automatic preparation are on when the model is installed.
2. Drop UTF-8 text or a supported text-only Word file. No list of names is required.
3. Inspect the prepared result, then save it. For Word files, inspect the saved document before sharing.

CLI automation: `python -m scrubbee scrub note.docx --auto-names`. Use unique output and map names for each run. Originals are never overwritten. Existing unsupported-format and document-structure checks still apply.

## Detection versus encryption

The local spaCy English model recognizes PERSON entities. This is statistical name detection; it can miss unfamiliar, ambiguous or non-English names and can incorrectly classify ordinary words. Optional custom terms remain useful. It is not automatic detection of every identifier, guaranteed anonymization or a compliance certification. A single text block is limited to 1,000,000 characters with automatic names enabled.

Scrubbee substitutes placeholders and keeps a private restoration map. That map is plaintext, not encrypted. Encrypting maps at rest, key management and permanent non-reversible redaction are separate future capabilities; none is implied by the word “scrub.”

The optional spaCy software and downloaded model keep their own licenses. Scrubbee's proprietary license does not claim ownership of them. See [spaCy model installation](https://spacy.io/usage/models) and the installed model's metadata for license and evaluation details.
