"""Use the isolated debug server's optional document libraries."""
import importlib.util
import unittest
from io import BytesIO
from zipfile import ZipFile
from report_export import render


class SampleExportTest(unittest.TestCase):
    @unittest.skipUnless(all(importlib.util.find_spec(p) for p in ("pptx","docx","openpyxl","reportlab")), "requires export libraries")
    def test_four_download_formats(self):
        self.assertTrue(render("pdf","巡检报告",["样例数据"]).startswith(b"%PDF"))
        for fmt, member in (("docx","word/document.xml"),("pptx","ppt/slides/slide1.xml"),("xlsx","xl/worksheets/sheet1.xml")):
            with self.subTest(fmt=fmt), ZipFile(BytesIO(render(fmt,"巡检报告",["¥5,199","=1+2"]))) as archive:
                self.assertIn(member,archive.namelist())
                self.assertNotIn(b"<f>",archive.read(member))
                self.assertIsNone(archive.testzip())

    def test_bad_format(self):
        with self.assertRaises(ValueError):
            render("html","报告",[])
