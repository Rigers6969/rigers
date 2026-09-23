"""Lays out the fetched vocabulary/grammar/idioms into one PDF, using
reportlab's platypus layer (Paragraph/Spacer/PageBreak) so text wraps
and paginates automatically - no manual coordinate math."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

# Helvetica (reportlab's default) has no glyphs for IPA phonetic symbols
# (e.g. the ʌ/ɛ/ʊ in "/rʌn/"), so they render as solid black boxes.
# DejaVu Sans covers IPA - bundled in fonts/ (Bitstream Vera license, see
# fonts/LICENSE) so this doesn't depend on fonts installed on the machine.
_FONTS_DIR = Path(__file__).resolve().parent / "fonts"
pdfmetrics.registerFont(TTFont("DejaVuSans", str(_FONTS_DIR / "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", str(_FONTS_DIR / "DejaVuSans-Bold.ttf")))
pdfmetrics.registerFontFamily(
    "DejaVuSans", normal="DejaVuSans", bold="DejaVuSans-Bold",
    italic="DejaVuSans", boldItalic="DejaVuSans-Bold",
)

_styles = getSampleStyleSheet()
_title_style = ParagraphStyle("TitleBig", parent=_styles["Title"], fontName="DejaVuSans-Bold", fontSize=28, leading=34, spaceAfter=10)
_subtitle_style = ParagraphStyle("Subtitle", parent=_styles["Normal"], fontName="DejaVuSans", fontSize=12, textColor="#555555")
_section_style = ParagraphStyle("Section", parent=_styles["Heading1"], fontName="DejaVuSans-Bold", fontSize=20, spaceBefore=18, spaceAfter=10)
_chapter_style = ParagraphStyle("Chapter", parent=_styles["Heading2"], fontName="DejaVuSans-Bold", fontSize=14, spaceBefore=12, spaceAfter=6)
_word_style = ParagraphStyle("Word", parent=_styles["Heading3"], fontName="DejaVuSans-Bold", fontSize=13, spaceBefore=10, spaceAfter=2)
_body_style = ParagraphStyle("Body", parent=_styles["Normal"], fontName="DejaVuSans", fontSize=10.5, leading=15, spaceAfter=4)
_example_style = ParagraphStyle("Example", parent=_styles["Italic"], fontName="DejaVuSans", fontSize=10, textColor="#444444", leftIndent=12, spaceAfter=8)
_phrase_style = ParagraphStyle("Phrase", parent=_styles["Heading3"], fontName="DejaVuSans-Bold", fontSize=12, spaceBefore=10, spaceAfter=2, textColor="#8a5a00")


def _escape(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_pdf(
    out_path: Path,
    vocabulary: list[dict],
    grammar: list[dict],
    idioms: list[dict],
) -> Path:
    doc = SimpleDocTemplate(
        str(out_path), pagesize=LETTER,
        topMargin=0.9 * inch, bottomMargin=0.9 * inch,
        leftMargin=0.9 * inch, rightMargin=0.9 * inch,
    )
    story = []

    story.append(Paragraph("English Learning Guide", _title_style))
    story.append(Paragraph(
        f"Generated {date.today().isoformat()} - vocabulary and idioms via the Free Dictionary API "
        "and Wiktionary, grammar via Wikibooks' \"English in Use\" (CC BY-SA).",
        _subtitle_style,
    ))
    story.append(Spacer(1, 0.3 * inch))
    story.append(Paragraph(
        f"Contents: {len(vocabulary)} vocabulary words &middot; "
        f"{len(grammar)} grammar chapters &middot; {len(idioms)} idioms",
        _body_style,
    ))
    story.append(PageBreak())

    if grammar:
        story.append(Paragraph("Grammar", _section_style))
        for chapter in grammar:
            story.append(Paragraph(_escape(chapter["chapter"]), _chapter_style))
            for para in chapter["text"].split("\n"):
                para = para.strip()
                if para:
                    story.append(Paragraph(_escape(para), _body_style))
        story.append(PageBreak())

    if vocabulary:
        story.append(Paragraph("Vocabulary", _section_style))
        for entry in vocabulary:
            header = _escape(entry["word"])
            if entry.get("phonetic"):
                header += f" <font color='#777777' size='9'>{_escape(entry['phonetic'])}</font>"
            story.append(Paragraph(header, _word_style))
            for meaning in entry["meanings"]:
                pos = f"<i>({_escape(meaning['part_of_speech'])})</i> " if meaning.get("part_of_speech") else ""
                story.append(Paragraph(f"{pos}{_escape(meaning['definition'])}", _body_style))
                if meaning.get("example"):
                    story.append(Paragraph(f"“{_escape(meaning['example'])}”", _example_style))
        story.append(PageBreak())

    if idioms:
        story.append(Paragraph("Idioms", _section_style))
        for idiom in idioms:
            story.append(Paragraph(_escape(idiom["phrase"]), _phrase_style))
            story.append(Paragraph(_escape(idiom["meaning"]), _body_style))

    doc.build(story)
    return out_path
