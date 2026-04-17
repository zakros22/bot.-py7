import io
import os
import json
import logging
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    ARABIC_OK = True
except ImportError:
    ARABIC_OK = False

logger = logging.getLogger(__name__)

# خطوط العربية
_FONTS_DIR = os.path.join(os.path.dirname(__file__), 'fonts')
_AMIRI_REG = os.path.join(_FONTS_DIR, 'Amiri-Regular.ttf')
_AMIRI_BOLD = os.path.join(_FONTS_DIR, 'Amiri-Bold.ttf')

ARABIC_FONT = 'Helvetica'
ARABIC_FONT_BOLD = 'Helvetica-Bold'

try:
    if os.path.exists(_AMIRI_REG):
        pdfmetrics.registerFont(TTFont('Amiri', _AMIRI_REG))
        ARABIC_FONT = 'Amiri'
    if os.path.exists(_AMIRI_BOLD):
        pdfmetrics.registerFont(TTFont('Amiri-Bold', _AMIRI_BOLD))
        ARABIC_FONT_BOLD = 'Amiri-Bold'
    if ARABIC_FONT == 'Amiri':
        logger.info("Amiri Arabic font registered successfully.")
except Exception as _fe:
    logger.warning(f"Could not register Amiri font: {_fe}")

# الألوان
PRIMARY = colors.HexColor('#1A73E8')
SECONDARY = colors.HexColor('#34A853')
ACCENT = colors.HexColor('#EA4335')
GOLD = colors.HexColor('#FBBC04')
LIGHT_BG = colors.HexColor('#F8F9FA')
DARK_TEXT = colors.HexColor('#202124')
MID_TEXT = colors.HexColor('#5F6368')


def _ar(text: str) -> str:
    if not ARABIC_OK or not text:
        return text
    try:
        reshaped = arabic_reshaper.reshape(str(text))
        return get_display(reshaped)
    except Exception:
        return text


def _rtl(text: str, lang: str) -> str:
    return _ar(text) if lang == 'ar' else text


def _make_styles(lang: str):
    align = TA_RIGHT if lang == 'ar' else TA_LEFT
    font = ARABIC_FONT if lang == 'ar' else 'Helvetica'
    font_bold = ARABIC_FONT_BOLD if lang == 'ar' else 'Helvetica-Bold'

    base = ParagraphStyle('base', fontName=font, fontSize=10, leading=18, textColor=DARK_TEXT, alignment=align)

    return {
        'title': ParagraphStyle('title', parent=base, fontSize=20, fontName=font_bold, textColor=colors.white, alignment=TA_CENTER, spaceAfter=4, leading=26),
        'subtitle': ParagraphStyle('subtitle', parent=base, fontSize=10, textColor=colors.white, alignment=TA_CENTER, spaceAfter=2, leading=16),
        'section': ParagraphStyle('section', parent=base, fontSize=13, fontName=font_bold, textColor=PRIMARY, spaceBefore=8, spaceAfter=4),
        'q_number': ParagraphStyle('q_number', parent=base, fontSize=11, fontName=font_bold, textColor=colors.white, leading=16),
        'q_body': ParagraphStyle('q_body', parent=base, fontSize=11, leading=20, spaceBefore=2, spaceAfter=4, fontName=font),
        'option': ParagraphStyle('option', parent=base, fontSize=10, leading=16, fontName=font),
        'answer': ParagraphStyle('answer', parent=base, fontSize=10, fontName=font_bold, textColor=SECONDARY, spaceBefore=4),
        'explanation': ParagraphStyle('explanation', parent=base, fontSize=9, textColor=MID_TEXT, spaceBefore=2, spaceAfter=2, fontName=font),
        'footer': ParagraphStyle('footer', parent=base, fontSize=8, textColor=MID_TEXT, alignment=TA_CENTER),
        'tag': ParagraphStyle('tag', parent=base, fontSize=9, textColor=colors.white, alignment=TA_CENTER, fontName=font_bold),
    }


def _type_tag(q_type: str, lang: str) -> tuple:
    labels_ar = {'multiple_choice': 'اختيار متعدد', 'true_false': 'صح / خطأ', 'fill_blank': 'ملء الفراغات', 'qa': 'سؤال وجواب'}
    labels_en = {'multiple_choice': 'Multiple Choice', 'true_false': 'True / False', 'fill_blank': 'Fill in the Blank', 'qa': 'Q & A'}
    tag_colors = {'multiple_choice': PRIMARY, 'true_false': SECONDARY, 'fill_blank': GOLD, 'qa': ACCENT}
    labels = labels_ar if lang == 'ar' else labels_en
    return labels.get(q_type, q_type), tag_colors.get(q_type, MID_TEXT)


def _safe_text(text) -> str:
    if text is None:
        return ''
    s = str(text).strip()
    s = ''.join(c for c in s if ord(c) >= 32 or c == '\n')
    return s


def generate_quiz_pdf(questions_raw: list, quiz_title: str, lang: str = 'ar') -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2.5*cm, bottomMargin=2.5*cm)
    S = _make_styles(lang)
    story = []
    W = A4[0] - 4*cm

    now_str = datetime.now().strftime('%Y-%m-%d  %H:%M')
    raw_title = _safe_text(quiz_title) or ('ملف الأسئلة' if lang == 'ar' else 'Quiz Questions')
    title_txt = _rtl(raw_title, lang)
    total_q = len(questions_raw)

    # Header
    if lang == 'ar':
        subtitle_txt = _ar(f'عدد الأسئلة: {total_q}  •  {now_str}')
    else:
        subtitle_txt = f'Questions: {total_q}  •  {now_str}'

    hdr_data = [[Paragraph(title_txt, S['title'])], [Paragraph('@zakros_Quizebot', S['subtitle'])], [Paragraph(subtitle_txt, S['subtitle'])]]
    hdr_table = Table(hdr_data, colWidths=[W])
    hdr_table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), PRIMARY), ('ROWPADDING', (0, 0), (-1, -1), 8), ('ROUNDEDCORNERS', [8])]))
    story.append(hdr_table)
    story.append(Spacer(1, 0.5*cm))

    # الأسئلة
    for i, q in enumerate(questions_raw, 1):
        q_type = _safe_text(q.get('question_type', 'multiple_choice'))
        q_text = _safe_text(q.get('question_text', ''))
        correct = _safe_text(q.get('correct_answer', ''))
        explain = _safe_text(q.get('explanation', ''))
        
        if not q_text:
            continue
        
        tag_label, tag_color = _type_tag(q_type, lang)
        
        q_content = [Paragraph(f"<b>{i}. {_rtl(q_text, lang)}</b>", S['q_body'])]
        
        if q_type == 'multiple_choice' and q.get('options'):
            try:
                opts = json.loads(q['options']) if isinstance(q['options'], str) else q['options']
                for opt in opts:
                    if opt:
                        q_content.append(Paragraph(f"• {_rtl(opt, lang)}", S['option']))
            except Exception:
                pass
        
        q_content.append(Paragraph(f"✅ <b>{_rtl(correct, lang)}</b>", S['answer']))
        if explain:
            q_content.append(Paragraph(f"💡 {_rtl(explain, lang)}", S['explanation']))
        
        story.append(KeepTogether(q_content))
        story.append(Spacer(1, 0.3*cm))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
