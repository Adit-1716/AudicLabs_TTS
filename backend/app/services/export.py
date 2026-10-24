import html
import io
from datetime import datetime, timedelta, timezone

from docx import Document


def as_txt(segments: list, speakers: dict, raw: str, is_lyrics: bool = False) -> bytes:
    if segments:
        lines = []
        if is_lyrics:
            lines.append("=" * 48)
            lines.append("SONG LYRICS & VOCAL CAPTIONS")
            lines.append("=" * 48)
            lines.append("")
        for s in segments:
            speaker = s.get("speaker") or speakers.get(str(s.get("speaker_id")), "Vocalist" if is_lyrics else "Speaker")
            start_ts = _ts(s.get("start", 0))
            text = (s.get("text") or "").strip()
            if is_lyrics:
                lines.append(f"[{start_ts}] ({speaker}) {text}")
            else:
                lines.append(f"[{start_ts}] {speaker}: {text}")
        return "\n".join(lines).encode("utf-8")
    return (raw or "").encode("utf-8")


def as_srt(segments: list, raw: str) -> bytes:
    if not segments:
        segments = [{"start": 0, "end": 5, "text": raw}]
    blocks = []
    for i, s in enumerate(segments, 1):
        start = _srt(s.get("start") or 0)
        end = _srt(s.get("end") or (s.get("start") or 0) + 2)
        speaker = s.get("speaker")
        text = s.get("text") or ""
        if speaker:
            text = f"{speaker}: {text}"
        blocks.append(f"{i}\n{start} --> {end}\n{text}\n")
    return "\n".join(blocks).encode("utf-8")


def as_docx(title: str, segments: list, raw: str, is_lyrics: bool = False) -> bytes:
    doc = Document()
    doc.add_heading(title, 1)
    if is_lyrics:
        p_sub = doc.add_paragraph("Song Lyrics & Audio Captions · AudicLabs Hub")
        p_sub.style = "Subtitle"
    else:
        doc.add_paragraph("Official Audio Transcription · AudicLabs Hub")

    if segments:
        for s in segments:
            p = doc.add_paragraph()
            speaker = s.get("speaker") or ("Vocalist" if is_lyrics else "Speaker")
            run = p.add_run(f"{speaker}  [{_ts(s.get('start', 0))}]")
            run.bold = True
            p_text = doc.add_paragraph(s.get("text") or "")
            if is_lyrics:
                p_text.paragraph_format.space_after = 6
    else:
        doc.add_paragraph(raw or "")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def as_pdf(title: str, segments: list, raw: str, is_lyrics: bool = False) -> bytes:
    """Generate a high-quality PDF document using reportlab with pure-Python fallback."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=letter,
            rightMargin=0.75 * inch,
            leftMargin=0.75 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
        )

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "DocTitle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#1e293b"),
            spaceAfter=4,
        )
        subtitle_style = ParagraphStyle(
            "DocSubtitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#64748b"),
            spaceAfter=12,
        )
        tag_style = ParagraphStyle(
            "SpeakerTag",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#4f46e5" if is_lyrics else "#0f766e"),
            spaceBefore=8,
            spaceAfter=2,
        )
        text_style = ParagraphStyle(
            "LineText",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=11,
            leading=16,
            textColor=colors.HexColor("#334155"),
            spaceAfter=6,
        )

        story = []
        story.append(Paragraph(html.escape(title or "Transcript"), title_style))
        subtitle_text = "Song Lyrics & Vocal Synchronization" if is_lyrics else "Audio Transcription & Review Transcript"
        date_str = datetime.now(timezone.utc).strftime("%B %d, %Y")
        story.append(Paragraph(f"{subtitle_text} · {date_str}", subtitle_style))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#e2e8f0"), spaceBefore=0, spaceAfter=14))

        if segments:
            for s in segments:
                speaker = html.escape(s.get("speaker") or ("Vocalist" if is_lyrics else "Speaker"))
                ts_str = _ts(s.get("start", 0))
                tag_line = f"🎵 {speaker} &nbsp;&nbsp;[{ts_str}]" if is_lyrics else f"<b>{speaker}</b> &nbsp;&nbsp;[{ts_str}]"
                story.append(Paragraph(tag_line, tag_style))
                story.append(Paragraph(html.escape(s.get("text") or ""), text_style))
        else:
            story.append(Paragraph(html.escape(raw or "No content recorded."), text_style))

        def add_footer(canvas, doc):
            canvas.saveState()
            canvas.setFont("Helvetica", 9)
            canvas.setFillColor(colors.HexColor("#94a3b8"))
            canvas.drawString(0.75 * inch, 0.4 * inch, "Generated by AudicLabs Transcribe Hub")
            canvas.drawRightString(8.5 * inch - 0.75 * inch, 0.4 * inch, f"Page {canvas.getPageNumber()}")
            canvas.restoreState()

        doc.build(story, onFirstPage=add_footer, onLaterPages=add_footer)
        return buf.getvalue()
    except Exception as exc:
        print("[PDF generation fallback]", exc)
        return _fallback_pdf(title, segments, raw, is_lyrics)


def _fallback_pdf(title: str, segments: list, raw: str, is_lyrics: bool = False) -> bytes:
    lines = [f"{title} - {'Lyrics' if is_lyrics else 'Transcript'}"]
    lines.append("-" * 40)
    if segments:
        for s in segments:
            speaker = s.get("speaker") or ("Vocalist" if is_lyrics else "Speaker")
            lines.append(f"[{_ts(s.get('start', 0))}] {speaker}: {s.get('text', '')}")
    else:
        lines.append(raw or "")

    stream_content = "BT\n/F1 12 Tf\n50 750 Td\n15 TL\n"
    for line in lines[:50]:
        clean_line = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream_content += f"({clean_line}) '\n"
    stream_content += "ET"
    stream_bytes = stream_content.encode("latin-1", errors="replace")

    pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj <</Type /Catalog /Pages 2 0 R>> endobj\n"
        b"2 0 obj <</Type /Pages /Kids [3 0 R] /Count 1>> endobj\n"
        b"3 0 obj <</Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /MediaBox [0 0 612 792] /Contents 5 0 R>> endobj\n"
        b"4 0 obj <</Type /Font /Subtype /Type1 /BaseFont /Helvetica>> endobj\n"
        b"5 0 obj <</Length " + str(len(stream_bytes)).encode("ascii") + b">> stream\n" + stream_bytes + b"\nendstream\nendobj\n"
        b"xref\n0 6\n0000000000 65535 f \n"
        b"trailer <</Size 6 /Root 1 0 R>>\nstartxref\n500\n%%EOF"
    )
    return pdf


def _ts(seconds: float) -> str:
    seconds = float(seconds or 0)
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _srt(seconds: float) -> str:
    td = timedelta(seconds=float(seconds or 0))
    total = int(td.total_seconds())
    ms = int((float(seconds or 0) - total) * 1000)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
