"""Render the selected sample content, independent of business APIs."""
from io import BytesIO
from xml.sax.saxutils import escape


def render(fmt, title, lines):
    output = BytesIO()
    if fmt == "pdf":
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.platypus import Paragraph, SimpleDocTemplate
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        style = ParagraphStyle("Chinese", fontName="STSong-Light", fontSize=10, leading=16, wordWrap="CJK", alignment=TA_LEFT)
        heading = ParagraphStyle("Heading", parent=style, fontSize=16, leading=24, spaceAfter=8)
        SimpleDocTemplate(output, title=title).build([Paragraph(escape(title), heading)] +
            [Paragraph(escape(line),style) for line in lines])
    elif fmt == "docx":
        from docx import Document
        doc = Document()
        doc.add_heading(title,0)
        for line in lines:
            doc.add_paragraph(line)
        doc.save(output)
    elif fmt == "xlsx":
        from openpyxl import Workbook
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "报告"
        sheet.column_dimensions["A"].width = 85
        for n,line in enumerate([title,*lines],1):
            cell = sheet.cell(n,1,line)
            cell.data_type = "s"
        workbook.save(output)
    elif fmt == "pptx":
        from pptx import Presentation
        from pptx.util import Pt
        deck = Presentation()
        chunks = [line[i:i+75] for line in lines for i in range(0,len(line),75)]
        for start in range(0,max(1,len(chunks)),5):
            slide = deck.slides.add_slide(deck.slide_layouts[1])
            slide.shapes.title.text = title
            text = slide.placeholders[1].text_frame
            for i,line in enumerate(chunks[start:start+5]):
                par = text.paragraphs[0] if i==0 else text.add_paragraph()
                par.text = line
                par.font.size = Pt(16)
        deck.save(output)
    else:
        raise ValueError("不支持的文件格式")
    return output.getvalue()
