"""UTF-8/Russian PDF export; no patient records are retained on the server."""
import io
import threading
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether

_font_lock = threading.Lock()
_font_ready = False
FONT = Path(__file__).parent / 'assets' / 'fonts' / 'DejaVuSans.ttf'
FIELDS = [('organ', 'Область исследования'), ('age', 'Возраст, лет'),
          ('indication', 'Показания'), ('measurements', 'Измерения врача'),
          ('observations', 'Наблюдения врача'), ('description', 'Описание'),
          ('conclusion', 'Заключение'), ('limitations', 'Ограничения'),
          ('doctor', 'Врач')]


def clean_text(value, limit=16000):
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError('Неподдерживаемый формат или размер текста протокола.')
    return ''.join(c for c in value if c in '\n\t' or ord(c) >= 32).strip()


def make_pdf(data):
    global _font_ready
    if not isinstance(data, dict):
        raise ValueError('Неподдерживаемая структура протокола.')
    values = {key: clean_text(data.get(key, '')) for key, _ in FIELDS}
    status = clean_text(data.get('status', ''), 100)
    date = clean_text(data.get('created_at', ''), 100)
    approved = (status == 'Проверено врачом' and values['doctor']
                and values['description'] and values['conclusion'])
    with _font_lock:
        if not _font_ready:
            pdfmetrics.registerFont(TTFont('SonoSans', str(FONT)))
            _font_ready = True
    out = io.BytesIO()
    document = SimpleDocTemplate(out, pagesize=A4, rightMargin=20*mm,
        leftMargin=20*mm, topMargin=18*mm, bottomMargin=22*mm,
        title='Протокол УЗИ — SonoCopilot', author='SonoCopilot',
        pageCompression=1)
    normal = ParagraphStyle('body', fontName='SonoSans', fontSize=10,
                            leading=15, spaceAfter=8, alignment=TA_LEFT, splitLongWords=True)
    heading = ParagraphStyle('heading', parent=normal, fontSize=10,
                             textColor=colors.HexColor('#126b68'), spaceBefore=10, spaceAfter=4)
    title = ParagraphStyle('title', parent=normal, fontSize=20, leading=26, spaceAfter=12)
    small = ParagraphStyle('small', parent=normal, fontSize=8, leading=12)
    def paragraph(text, style=normal):
        return Paragraph(escape(text).replace('\n', '<br/>'), style)
    flow = [paragraph('Протокол УЗИ', title),
            paragraph('Проверено врачом' if approved else 'ЧЕРНОВИК — не подтверждён врачом', heading),
            paragraph('Дата исследования: ' + (date or 'не указана'), small)]
    for key, label in FIELDS:
        flow.append(paragraph(label, heading))
        flow.append(paragraph(values[key] or 'Не указано'))
    provenance = data.get('provenance')
    if isinstance(provenance, dict):
        model = provenance.get('model')
        if isinstance(model, str):
            flow.extend([paragraph('Происхождение черновика', heading),
                         paragraph('Модель: ' + clean_text(model, 200), small)])
        if provenance.get('modified_after_generation'):
            flow.append(paragraph('Текст изменён после генерации.', small))
        if provenance.get('provider') == 'manual':
            flow.append(paragraph('Протокол составлен по данным врача, без ИИ-анализа.', small))
    flow.extend([Spacer(1, 12), paragraph(
        'SonoCopilot 1.0.0 · Исследовательская версия. Клиническая точность ИИ не подтверждена. '
        'Отметка проверки не является электронной подписью. Снимки в этот PDF не включены.', small)])
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('SonoSans', 8)
        canvas.setFillColor(colors.HexColor('#68777a'))
        canvas.drawString(20*mm, 12*mm, 'SonoCopilot · Протокол УЗИ')
        canvas.drawRightString(A4[0]-20*mm, 12*mm, str(doc.page))
        canvas.restoreState()
    document.build(flow, onFirstPage=footer, onLaterPages=footer)
    return out.getvalue()
