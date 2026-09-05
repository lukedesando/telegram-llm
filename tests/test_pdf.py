import pathlib
import sys
import unittest

import pymupdf

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.pdf import extract_pdf_text


class PdfExtractionTests(unittest.TestCase):
    @staticmethod
    def _pdf_bytes(text: str) -> bytes:
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), text)
        data = doc.tobytes()
        doc.close()
        return data

    def test_extract_pdf_text(self):
        text = extract_pdf_text(self._pdf_bytes("Flight relay acceptance evidence"))
        self.assertIn("Flight relay acceptance evidence", text)

    def test_extract_pdf_text_is_bounded(self):
        text = extract_pdf_text(self._pdf_bytes("alpha beta gamma delta"), max_chars=10)
        self.assertLessEqual(len(text), 10)
        self.assertTrue(text.startswith("alpha"))


if __name__ == "__main__":
    unittest.main()
