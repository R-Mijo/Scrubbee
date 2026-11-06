from io import BytesIO
import unittest
import zipfile
from scrubbee.names import available
from scrubbee.core import scrub_text, scrub_bytes, restore_text

@unittest.skipUnless(available(), 'Optional local English model is not installed')
class LocalModelTests(unittest.TestCase):
    def test_real_names_and_roundtrip(self):
        text='Jane Smith spoke with Michael Johnson. Email: jane@example.invalid.'
        result=scrub_text(text,auto_names=True)
        self.assertNotIn('Jane Smith',result.scrubbed_text)
        self.assertNotIn('Michael Johnson',result.scrubbed_text)
        self.assertIn('Email:',result.scrubbed_text)
        self.assertEqual(result.counts_by_type['PERSON'],2)
        self.assertEqual(restore_text(result.scrubbed_text,result.vault),text)
    def test_real_names_across_word_runs(self):
        stream=BytesIO()
        with zipfile.ZipFile(stream,'w') as archive:
            archive.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
            archive.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Jane </w:t></w:r><w:r><w:t>Smith spoke with Michael Johnson.</w:t></w:r></w:p></w:body></w:document>')
        output,report,vault=scrub_bytes('sample.docx',stream.getvalue(),auto_names=True)
        with zipfile.ZipFile(BytesIO(output)) as archive:
            xml=archive.read('word/document.xml')
        self.assertNotIn(b'Jane',xml)
        self.assertNotIn(b'Michael',xml)
        self.assertEqual(report['counts_by_type']['PERSON'],2)
