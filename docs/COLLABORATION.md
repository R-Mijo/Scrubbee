# Gemini Argon findings: independent verification

November 6, 2026. Reviewed baseline: `176997f6be0103bbae9914fe28499b984584edaa` on `R-Mijo/Scrubbee`. All 24 baseline source files matched their GitHub blob SHAs before edits. Main matched the user's handoff, and no open Scrubbee pull requests were found.

The user supplied Gemini's written report. It stated that Gemini had not pushed changes. No automatic chat synchronization or access to Gemini's environment is assumed. Only concrete affected code was inspected; completed project setup, naming and broader reviews were not repeated.

## Findings

- **Confirmed:** `scrub_text('Patient Art started his chart review.', custom_terms=['Art'])` replaced `Art`, the substring inside `started`, and the substring inside `chart`. A new regression test failed on that baseline, demonstrating unnecessary redactions and extra review work.
- **Fixed:** custom terms now use word-character guards at word-like edges. Matching is still case-insensitive and punctuation is literal. `Art` replaces a standalone name, leaving `started`, `chart`, `Art_2` and longer Unicode words intact. Enter full identifiers when a term belongs to a longer identifier; arbitrary substring matching is no longer implied. Supported DOCX text uses the same matcher across formatting runs.
- **Already correct:** exact original capitalization is preserved. The existing map keys are exact raw strings, so `Art`, `ART` and `art` have separate placeholders. The test now explicitly checks restoration after a serialized map roundtrip. No restoration format change was needed.

## Verification

`python -m unittest discover -s tests -v` passed **29 tests** using the existing local environment with spaCy and the English model installed. Both real-model text/Word integrations ran and passed. Five new tests cover short terms inside longer words, case variants, Unicode/underscore boundaries, punctuation/multiword terms and text split across Word formatting runs. Existing local HTTP, map, metadata, export and document-rejection tests also passed.

The first local HTTP run lacked permission to connect to temporary loopback apps; after that permission was granted, the entire suite passed. The accompanying pull request records the exact resulting code commit and GitHub CI runs. No Site deployment, installer execution, clipboard monitoring, browser extension, encryption or licensing change is included.

## Reproduce

```python
from scrubbee.core import scrub_text, restore_text, ScrubVault
raw = 'Patient Art started his chart review. ART met art.'
r = scrub_text(raw, custom_terms=['Art'])
assert r.redactions_count == 3
assert 'started his chart review.' in r.scrubbed_text
assert restore_text(r.scrubbed_text, ScrubVault.from_dict(r.vault.to_dict())) == raw
```

This fix reduces unnecessary corrections. It does not establish that Scrubbee beats the user's manual workflow on speed. The next product milestone remains a deliberately activated, local preparation/review/copy workflow with fewer application switches and automatic session matching. Benchmark it against the user's manual process before claiming time savings. Further reviews should identify an exact commit, input, expected/observed behavior and evidence, and be independently reproduced.
