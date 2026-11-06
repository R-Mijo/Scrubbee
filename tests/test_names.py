import unittest
from unittest.mock import patch
from scrubbee.core import scrub_text, scrub_bytes, restore_text

class AutomaticNamesTests(unittest.TestCase):
    def test_automatic_name_replacement_and_restore(self):
        text='Jane Smith called jane@example.invalid.'
        with patch('scrubbee.names.person_spans',return_value=[(0,10)]):
            r=scrub_text(text,auto_names=True)
        self.assertNotIn('Jane Smith',r.scrubbed_text)
        self.assertEqual(r.counts_by_type['PERSON'],1)
        self.assertEqual(restore_text(r.scrubbed_text,r.vault),text)
    def test_model_not_used_when_disabled(self):
        with patch('scrubbee.names.person_spans',side_effect=AssertionError('must not run')):
            self.assertEqual(scrub_text('Jane Smith').scrubbed_text,'Jane Smith')
    def test_missing_model_does_not_claim_success(self):
        with patch('scrubbee.names.person_spans',side_effect=ValueError('Model missing')):
            with self.assertRaisesRegex(ValueError,'Model missing'):
                scrub_bytes('x.txt',b'Jane Smith',auto_names=True)
    def test_generated_placeholders_are_protected(self):
        r=scrub_text('jane@example.invalid')
        with patch('scrubbee.names.person_spans',return_value=[(0,len(r.scrubbed_text))]):
            second=scrub_text(r.scrubbed_text,auto_names=True)
        self.assertEqual(second.scrubbed_text,r.scrubbed_text)
    def test_bad_boolean_rejected(self):
        with self.assertRaises(ValueError):scrub_text('x',auto_names='true')
