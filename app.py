import base64
import hashlib
import html
import io
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st
from openai import OpenAI
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image as PDFImage
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


BASE_DIR = Path(__file__).resolve().parent
PDF_FONT_REGULAR = BASE_DIR / "assets" / "fonts" / "NanumGothic-Regular.ttf"
PDF_FONT_BOLD = BASE_DIR / "assets" / "fonts" / "NanumGothic-Bold.ttf"
PDF_FONT_NAME = "NanumGothic"
PDF_FONT_BOLD_NAME = "NanumGothic-Bold"

SYSTEM_PROMPT = """
당신은 물리치료/운동 코치 보조 AI입니다.
입력된 사진 1장을 보고, 근골격계질환 예방 관점에서 자세 위험 신호를 추정해 운동을 제안하세요.
중요:
1) 진단이 아니라 예방 목적의 일반 가이드로 작성한다.
2) 사진만으로 확정할 수 없는 내용은 "추정"이라고 표현한다.
3) 위험하거나 통증 유발 가능성이 있는 과격한 운동은 피한다.
4) 초보자가 집에서 수행 가능한 운동 중심으로 작성한다.
5) 반드시 한국어로 작성한다.
6) 아래 JSON 형식으로만 응답한다. 코드블록 금지.

{
  "posture_summary": "한 문단 요약",
  "risk_level": "low 또는 medium 또는 high",
  "observed_signs": ["관찰/추정 신호1", "관찰/추정 신호2"],
  "recommended_exercises": [
    {
      "name": "운동명",
      "target": "주요 부위",
      "how_to": "수행 방법 1~2문장",
      "sets_reps": "예: 10회 x 2세트",
      "frequency": "예: 주 4~5회",
      "caution": "주의사항 1문장"
    }
  ],
  "daily_habits": ["생활 습관 교정 팁1", "팁2"],
  "warning": "통증/저림/마비 시 의료진 상담 권고 문구"
}
""".strip()


def initialize_state() -> None:
    defaults = {
        "analysis_result": None,
        "analysis_signature": None,
        "analysis_filename": None,
        "analysis_image_bytes": None,
        "analysis_timestamp": None,
        "analysis_model": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def apply_styles() -> None:
    st.markdown(
        """
        <style>
            @import url("https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Noto+Sans+KR:wght@400;500;700&display=swap");
            :root {
                --bg-top: #f7efe1;
                --bg-mid: #edf6f2;
                --panel: rgba(255, 255, 255, 0.82);
                --ink: #17352f;
                --muted: #60736d;
                --line: rgba(23, 53, 47, 0.12);
                --primary: #0f6a57;
                --primary-deep: #0a4a3d;
                --accent: #e97a5b;
                --shadow: 0 22px 48px rgba(15, 45, 39, 0.1);
            }
            html, body, [class*="css"] { font-family: "Noto Sans KR", sans-serif; }
            .stApp {
                background:
                    radial-gradient(circle at top left, rgba(247, 192, 123, 0.24), transparent 28%),
                    radial-gradient(circle at top right, rgba(77, 174, 144, 0.18), transparent 26%),
                    linear-gradient(180deg, var(--bg-top) 0%, var(--bg-mid) 34%, #f7fbfa 100%);
                color: var(--ink);
            }
            .main .block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 1180px; }
            h1, h2, h3 { color: var(--ink); letter-spacing: -0.02em; }
            .hero-shell {
                position: relative;
                overflow: hidden;
                border-radius: 28px;
                padding: 32px 32px 28px 32px;
                background: linear-gradient(135deg, rgba(15, 106, 87, 0.96), rgba(8, 65, 53, 0.96));
                color: #f6fbfa;
                box-shadow: var(--shadow);
                margin-bottom: 1.4rem;
                animation: rise-in 500ms ease-out;
            }
            .hero-shell::before {
                content: "";
                position: absolute;
                right: -80px;
                top: -70px;
                width: 240px;
                height: 240px;
                background: radial-gradient(circle, rgba(255, 255, 255, 0.18), rgba(255, 255, 255, 0));
                border-radius: 50%;
            }
            .hero-kicker {
                font-family: "Space Grotesk", "Noto Sans KR", sans-serif;
                font-size: 0.82rem;
                letter-spacing: 0.14em;
                text-transform: uppercase;
                opacity: 0.82;
                margin-bottom: 0.6rem;
            }
            .hero-title { margin: 0; font-size: clamp(2rem, 4vw, 3rem); line-height: 1.05; font-weight: 700; }
            .hero-copy { margin: 0.8rem 0 1rem 0; font-size: 1rem; line-height: 1.7; max-width: 760px; opacity: 0.94; }
            .hero-pills { display: flex; flex-wrap: wrap; gap: 0.55rem; }
            .hero-pill {
                display: inline-flex;
                align-items: center;
                padding: 0.42rem 0.75rem;
                border-radius: 999px;
                background: rgba(255, 255, 255, 0.13);
                border: 1px solid rgba(255, 255, 255, 0.14);
                font-size: 0.88rem;
            }
            .panel-title {
                font-family: "Space Grotesk", "Noto Sans KR", sans-serif;
                font-size: 1.05rem;
                font-weight: 700;
                color: var(--ink);
                margin-bottom: 0.35rem;
            }
            .panel-copy { color: var(--muted); line-height: 1.65; margin-bottom: 0.9rem; }
            .mini-note {
                background: rgba(15, 106, 87, 0.08);
                border: 1px solid rgba(15, 106, 87, 0.14);
                border-radius: 18px;
                padding: 0.9rem 1rem;
                color: var(--ink);
                line-height: 1.65;
            }
            .mini-note strong { display: block; margin-bottom: 0.25rem; }
            .feature-list { margin: 0; padding-left: 1.1rem; color: var(--muted); line-height: 1.85; }
            .section-heading { margin-top: 1.6rem; margin-bottom: 0.85rem; }
            .section-heading h2 { margin-bottom: 0.2rem; font-size: 1.45rem; }
            .section-heading p { margin: 0; color: var(--muted); }
            .metric-card, .content-card, .exercise-card, .warning-card, .empty-card {
                background: var(--panel);
                border: 1px solid var(--line);
                border-radius: 24px;
                box-shadow: var(--shadow);
                backdrop-filter: blur(14px);
                animation: rise-in 450ms ease-out;
            }
            .metric-card { padding: 1rem 1.1rem; min-height: 154px; }
            .metric-label { color: var(--muted); font-size: 0.86rem; margin-bottom: 0.45rem; }
            .metric-value {
                font-family: "Space Grotesk", "Noto Sans KR", sans-serif;
                font-size: 1.7rem;
                font-weight: 700;
                line-height: 1.1;
                color: var(--ink);
                margin-bottom: 0.38rem;
            }
            .metric-note { color: var(--muted); font-size: 0.92rem; line-height: 1.6; }
            .tone-low { border-top: 5px solid rgba(46, 139, 87, 0.9); }
            .tone-medium { border-top: 5px solid rgba(183, 121, 31, 0.9); }
            .tone-high { border-top: 5px solid rgba(200, 79, 70, 0.92); }
            .tone-neutral { border-top: 5px solid rgba(15, 106, 87, 0.9); }
            .content-card, .warning-card, .empty-card { padding: 1.2rem 1.25rem; }
            .content-eyebrow {
                font-family: "Space Grotesk", "Noto Sans KR", sans-serif;
                font-size: 0.75rem;
                letter-spacing: 0.12em;
                text-transform: uppercase;
                color: var(--primary);
                margin-bottom: 0.4rem;
            }
            .content-card h3, .warning-card h3, .empty-card h3 { margin-top: 0; margin-bottom: 0.4rem; font-size: 1.1rem; }
            .content-card p, .warning-card p, .empty-card p { color: var(--ink); line-height: 1.72; margin-bottom: 0; }
            .bullet-list { margin: 0.4rem 0 0 0; padding-left: 1.15rem; line-height: 1.85; color: var(--ink); }
            .bullet-list li + li { margin-top: 0.28rem; }
            .exercise-card {
                padding: 1.1rem 1.15rem 1rem 1.15rem;
                min-height: 270px;
                position: relative;
                overflow: hidden;
            }
            .exercise-card::after {
                content: "";
                position: absolute;
                top: -60px;
                right: -60px;
                width: 150px;
                height: 150px;
                border-radius: 50%;
                background: radial-gradient(circle, rgba(233, 122, 91, 0.12), rgba(233, 122, 91, 0));
            }
            .exercise-kicker {
                font-family: "Space Grotesk", "Noto Sans KR", sans-serif;
                font-size: 0.75rem;
                letter-spacing: 0.12em;
                text-transform: uppercase;
                color: var(--accent);
                margin-bottom: 0.45rem;
            }
            .exercise-name { font-size: 1.15rem; font-weight: 700; color: var(--ink); margin-bottom: 0.8rem; }
            .exercise-meta {
                display: grid;
                grid-template-columns: 84px 1fr;
                gap: 0.45rem 0.75rem;
                margin: 0;
                color: var(--ink);
                line-height: 1.7;
                position: relative;
                z-index: 1;
            }
            .exercise-meta dt { color: var(--muted); font-weight: 600; }
            .exercise-meta dd { margin: 0; }
            .warning-card {
                border-left: 6px solid rgba(233, 122, 91, 0.92);
                background: linear-gradient(135deg, rgba(255, 247, 241, 0.95), rgba(255, 255, 255, 0.96));
            }
            .empty-card { background: linear-gradient(180deg, rgba(255, 255, 255, 0.9), rgba(250, 253, 252, 0.94)); }
            .empty-card ul { margin: 0.55rem 0 0 0; padding-left: 1.15rem; line-height: 1.8; color: var(--muted); }
            div[data-testid="stFileUploaderDropzone"] {
                border-radius: 20px;
                border: 1.3px dashed rgba(15, 106, 87, 0.35);
                background: rgba(255, 255, 255, 0.56);
                padding: 0.5rem;
            }
            div[data-testid="stFileUploaderDropzone"] * { color: var(--ink) !important; }
            div[data-testid="stTextInputRootElement"] > div { border-radius: 16px; }
            div[data-testid="stButton"] button, div[data-testid="stDownloadButton"] button {
                width: 100%;
                border-radius: 999px;
                border: none;
                padding: 0.82rem 1.15rem;
                font-weight: 700;
                background: linear-gradient(135deg, var(--primary), var(--primary-deep));
                color: #ffffff;
                box-shadow: 0 14px 28px rgba(15, 106, 87, 0.18);
                transition: transform 180ms ease, box-shadow 180ms ease;
            }
            div[data-testid="stButton"] button:hover, div[data-testid="stDownloadButton"] button:hover {
                transform: translateY(-1px);
                box-shadow: 0 18px 30px rgba(15, 106, 87, 0.22);
            }
            @keyframes rise-in {
                from { opacity: 0; transform: translateY(10px); }
                to { opacity: 1; transform: translateY(0); }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def image_to_data_url(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=92)
    img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{img_base64}"


def image_to_jpeg_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=92)
    return buffer.getvalue()


def build_signature(raw_bytes: bytes) -> str:
    return hashlib.sha1(raw_bytes).hexdigest()


def extract_json_text(raw_text: str) -> Dict[str, Any]:
    raw_text = raw_text.strip()
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(raw_text[start : end + 1])
        raise


def analyze_posture(image: Image.Image, model: str) -> Dict[str, Any]:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    data_url = image_to_data_url(image)

    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": [{"type": "input_text", "text": SYSTEM_PROMPT}],
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "사진을 분석해 JSON으로 답변해줘."},
                    {"type": "input_image", "image_url": data_url},
                ],
            },
        ],
        temperature=0.2,
    )

    output_text = getattr(response, "output_text", None)
    if not output_text:
        output_text = ""
        for item in getattr(response, "output", []):
            for content in getattr(item, "content", []):
                if getattr(content, "type", "") == "output_text":
                    output_text += getattr(content, "text", "")

    if not output_text:
        raise RuntimeError("모델 응답 텍스트를 확인하지 못했습니다.")

    return extract_json_text(output_text)


def risk_meta(level: str) -> Dict[str, str]:
    normalized = str(level).lower()
    if normalized == "low":
        return {
            "label": "낮음",
            "tone": "low",
            "note": "현재 사진 기준으로는 비교적 안정적인 편입니다.",
            "pdf_color": "#2E8B57",
        }
    if normalized == "medium":
        return {
            "label": "중간",
            "tone": "medium",
            "note": "반복 누적 시 목과 어깨 부담이 커질 수 있습니다.",
            "pdf_color": "#B7791F",
        }
    if normalized == "high":
        return {
            "label": "높음",
            "tone": "high",
            "note": "예방 운동과 생활 습관 교정이 특히 중요해 보입니다.",
            "pdf_color": "#C84F46",
        }
    return {
        "label": str(level),
        "tone": "neutral",
        "note": "참고용 결과입니다.",
        "pdf_color": "#0F6A57",
    }


def format_html_text(value: str) -> str:
    return html.escape(str(value or "-")).replace("\n", "<br>")


def build_list_html(items: List[str], empty_text: str) -> str:
    if not items:
        return f"<ul class='bullet-list'><li>{html.escape(empty_text)}</li></ul>"
    bullets = "".join(f"<li>{format_html_text(item)}</li>" for item in items)
    return f"<ul class='bullet-list'>{bullets}</ul>"


def render_hero() -> None:
    st.markdown(
        """
        <section class="hero-shell">
            <div class="hero-kicker">Posture Insight Studio</div>
            <h1 class="hero-title">사진 한 장을<br>실행 가능한 예방 리포트로</h1>
            <p class="hero-copy">
                자세 사진을 분석해 목, 어깨, 흉추 중심의 부담 신호를 정리하고
                바로 실천할 수 있는 운동과 생활 습관을 보기 좋은 리포트로 제공합니다.
            </p>
            <div class="hero-pills">
                <span class="hero-pill">AI 자세 분석</span>
                <span class="hero-pill">보고서형 UI</span>
                <span class="hero-pill">PDF 다운로드</span>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_metric_card(label: str, value: str, note: str, tone: str) -> None:
    st.markdown(
        f"""
        <div class="metric-card tone-{html.escape(tone)}">
            <div class="metric-label">{html.escape(str(label))}</div>
            <div class="metric-value">{html.escape(str(value))}</div>
            <div class="metric-note">{html.escape(str(note))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_content_card(eyebrow: str, title: str, body_html: str) -> None:
    st.markdown(
        f"""
        <div class="content-card">
            <div class="content-eyebrow">{html.escape(str(eyebrow))}</div>
            <h3>{html.escape(str(title))}</h3>
            {body_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_exercise_card(exercise: Dict[str, Any]) -> None:
    st.markdown(
        f"""
        <div class="exercise-card">
            <div class="exercise-kicker">Recommended Exercise</div>
            <div class="exercise-name">{html.escape(str(exercise.get("name", "운동")))}</div>
            <dl class="exercise-meta">
                <dt>대상 부위</dt><dd>{format_html_text(exercise.get("target", "-"))}</dd>
                <dt>운동 방법</dt><dd>{format_html_text(exercise.get("how_to", "-"))}</dd>
                <dt>권장량</dt><dd>{format_html_text(exercise.get("sets_reps", "-"))}</dd>
                <dt>빈도</dt><dd>{format_html_text(exercise.get("frequency", "-"))}</dd>
                <dt>주의</dt><dd>{format_html_text(exercise.get("caution", "-"))}</dd>
            </dl>
        </div>
        """,
        unsafe_allow_html=True,
    )


def register_pdf_fonts() -> None:
    registered = set(pdfmetrics.getRegisteredFontNames())
    if PDF_FONT_NAME not in registered:
        pdfmetrics.registerFont(TTFont(PDF_FONT_NAME, str(PDF_FONT_REGULAR)))
    if PDF_FONT_BOLD_NAME not in registered:
        pdfmetrics.registerFont(TTFont(PDF_FONT_BOLD_NAME, str(PDF_FONT_BOLD)))


def pdf_text(value: Any) -> str:
    return html.escape(str(value or "-")).replace("\n", "<br/>")


def fit_pdf_image(image_bytes: bytes, max_width: float, max_height: float) -> PDFImage:
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    width, height = image.size
    scale = min(max_width / width, max_height / height, 1)
    draw_width = width * scale
    draw_height = height * scale

    jpeg_buffer = io.BytesIO()
    image.save(jpeg_buffer, format="JPEG", quality=92)
    jpeg_buffer.seek(0)

    return PDFImage(jpeg_buffer, width=draw_width, height=draw_height)


def build_pdf_styles() -> Dict[str, ParagraphStyle]:
    return {
        "title": ParagraphStyle(
            "title",
            fontName=PDF_FONT_BOLD_NAME,
            fontSize=20,
            leading=26,
            textColor=colors.HexColor("#16332D"),
            spaceAfter=6,
        ),
        "meta": ParagraphStyle(
            "meta",
            fontName=PDF_FONT_NAME,
            fontSize=9.4,
            leading=14,
            textColor=colors.HexColor("#60736D"),
            spaceAfter=8,
        ),
        "section": ParagraphStyle(
            "section",
            fontName=PDF_FONT_BOLD_NAME,
            fontSize=12.3,
            leading=16,
            textColor=colors.HexColor("#0F6A57"),
            spaceBefore=10,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "body",
            fontName=PDF_FONT_NAME,
            fontSize=10.4,
            leading=17,
            textColor=colors.HexColor("#1F2F2B"),
        ),
        "label": ParagraphStyle(
            "label",
            fontName=PDF_FONT_BOLD_NAME,
            fontSize=9.4,
            leading=14,
            textColor=colors.HexColor("#60736D"),
        ),
        "value": ParagraphStyle(
            "value",
            fontName=PDF_FONT_BOLD_NAME,
            fontSize=16,
            leading=21,
            textColor=colors.HexColor("#16332D"),
        ),
        "card_title": ParagraphStyle(
            "card_title",
            fontName=PDF_FONT_BOLD_NAME,
            fontSize=11.2,
            leading=16,
            textColor=colors.HexColor("#16332D"),
        ),
        "small": ParagraphStyle(
            "small",
            fontName=PDF_FONT_NAME,
            fontSize=9.6,
            leading=15,
            textColor=colors.HexColor("#1F2F2B"),
        ),
    }


def build_metric_table(data: Dict[str, Any], styles: Dict[str, ParagraphStyle]) -> Table:
    risk = risk_meta(data.get("risk_level", "unknown"))
    observed_count = len(data.get("observed_signs", []))
    exercise_count = len(data.get("recommended_exercises", []))

    metric_rows = [
        [
            Paragraph("예상 위험도", styles["label"]),
            Paragraph(pdf_text(risk["label"]), styles["value"]),
            Paragraph("관찰 신호 수", styles["label"]),
            Paragraph(str(observed_count), styles["value"]),
            Paragraph("추천 운동 수", styles["label"]),
            Paragraph(str(exercise_count), styles["value"]),
        ],
        [
            Paragraph(pdf_text(risk["note"]), styles["small"]),
            "",
            Paragraph("자세 이상 징후 추정 개수", styles["small"]),
            "",
            Paragraph("실행 가능한 운동 개수", styles["small"]),
            "",
        ],
    ]

    table = Table(
        metric_rows,
        colWidths=[31 * mm, 25 * mm, 31 * mm, 20 * mm, 31 * mm, 20 * mm],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (1, 1), colors.HexColor("#EAF4F0")),
                ("BACKGROUND", (2, 0), (3, 1), colors.HexColor("#F2F8F5")),
                ("BACKGROUND", (4, 0), (5, 1), colors.HexColor("#FFF2EA")),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#CADCD6")),
                ("INNERGRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#D8E6E2")),
                ("SPAN", (0, 1), (1, 1)),
                ("SPAN", (2, 1), (3, 1)),
                ("SPAN", (4, 1), (5, 1)),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return table


def build_bullet_table(title: str, items: List[str], styles: Dict[str, ParagraphStyle]) -> Table:
    if not items:
        items = ["관련 항목이 없습니다."]
    rows = [[Paragraph(title, styles["card_title"])]]
    rows.extend([[Paragraph(f"- {pdf_text(item)}", styles["body"])] for item in items])

    table = Table(rows, colWidths=[174 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EFF7F4")),
                ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#CADCD6")),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def build_exercise_table(exercise: Dict[str, Any], styles: Dict[str, ParagraphStyle]) -> Table:
    rows = [
        [Paragraph(pdf_text(exercise.get("name", "운동")), styles["card_title"])],
        [Paragraph(f"대상 부위: {pdf_text(exercise.get('target', '-'))}", styles["body"])],
        [Paragraph(f"운동 방법: {pdf_text(exercise.get('how_to', '-'))}", styles["body"])],
        [Paragraph(f"권장량: {pdf_text(exercise.get('sets_reps', '-'))}", styles["body"])],
        [Paragraph(f"빈도: {pdf_text(exercise.get('frequency', '-'))}", styles["body"])],
        [Paragraph(f"주의: {pdf_text(exercise.get('caution', '-'))}", styles["body"])],
    ]

    table = Table(rows, colWidths=[174 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FFF1EB")),
                ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#E6CFC4")),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def draw_pdf_footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#CADCD6"))
    canvas.line(doc.leftMargin, 12 * mm, A4[0] - doc.rightMargin, 12 * mm)
    canvas.setFont(PDF_FONT_NAME, 8.5)
    canvas.setFillColor(colors.HexColor("#60736D"))
    canvas.drawString(doc.leftMargin, 8.3 * mm, "사진 기반 근골격계 예방 운동 리포트")
    canvas.drawRightString(A4[0] - doc.rightMargin, 8.3 * mm, str(canvas.getPageNumber()))
    canvas.restoreState()


def build_pdf_report(
    report_data: Dict[str, Any],
    image_bytes: bytes,
    image_name: str,
    analyzed_at: str,
) -> bytes:
    register_pdf_fonts()
    styles = build_pdf_styles()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="근골격계 예방 분석 리포트",
    )

    story: List[Any] = []
    story.append(Paragraph("근골격계 예방 분석 리포트", styles["title"]))
    story.append(Paragraph(f"생성 시각: {pdf_text(analyzed_at)}", styles["meta"]))
    story.append(Paragraph(f"분석 파일: {pdf_text(image_name)}", styles["meta"]))
    story.append(Spacer(1, 4))
    story.append(fit_pdf_image(image_bytes, doc.width, 72 * mm))
    story.append(Spacer(1, 12))
    story.append(build_metric_table(report_data, styles))
    story.append(Spacer(1, 12))

    story.append(Paragraph("자세 요약", styles["section"]))
    story.append(Paragraph(pdf_text(report_data.get("posture_summary", "요약 정보가 없습니다.")), styles["body"]))
    story.append(Spacer(1, 10))

    story.append(build_bullet_table("관찰 및 추정 신호", report_data.get("observed_signs", []), styles))
    story.append(Spacer(1, 10))

    exercises = report_data.get("recommended_exercises", [])
    story.append(Paragraph("추천 운동", styles["section"]))
    if not exercises:
        story.append(Paragraph("추천 운동 정보가 없습니다.", styles["body"]))
    for exercise in exercises:
        story.append(build_exercise_table(exercise, styles))
        story.append(Spacer(1, 9))

    story.append(Spacer(1, 3))
    story.append(build_bullet_table("생활 습관 교정", report_data.get("daily_habits", []), styles))
    story.append(Spacer(1, 10))

    warning_text = report_data.get("warning", "통증이나 저림이 있으면 전문가 상담이 필요합니다.")
    warning_table = Table(
        [[Paragraph(pdf_text(warning_text), styles["body"])]],
        colWidths=[174 * mm],
    )
    warning_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF5EF")),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#E5C7BC")),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )

    story.append(Paragraph("주의", styles["section"]))
    story.append(warning_table)

    doc.build(story, onFirstPage=draw_pdf_footer, onLaterPages=draw_pdf_footer)
    return buffer.getvalue()


@st.cache_data(show_spinner=False)
def build_pdf_report_cached(
    report_json: str,
    image_bytes: bytes,
    image_name: str,
    analyzed_at: str,
) -> bytes:
    return build_pdf_report(json.loads(report_json), image_bytes, image_name, analyzed_at)


def build_download_filename(image_name: Optional[str]) -> str:
    stem = Path(image_name or "analysis").stem
    safe_stem = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in stem)
    return f"{safe_stem}_report.pdf"


def format_timestamp(iso_text: Optional[str]) -> str:
    if not iso_text:
        return "-"
    try:
        parsed = datetime.fromisoformat(iso_text)
        return parsed.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso_text


def render_result_dashboard(result: Dict[str, Any], pdf_bytes: Optional[bytes]) -> None:
    risk = risk_meta(result.get("risk_level", "unknown"))
    observed_signs = result.get("observed_signs", [])
    exercises = result.get("recommended_exercises", [])
    daily_habits = result.get("daily_habits", [])

    st.markdown(
        """
        <div class="section-heading">
            <h2>분석 리포트</h2>
            <p>화면에서 바로 확인하고, 필요하면 PDF로 내려받아 보관할 수 있습니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    heading_left, heading_right = st.columns([1.7, 1], gap="large")
    with heading_left:
        st.caption(
            f"분석 시각: {format_timestamp(st.session_state.get('analysis_timestamp'))} | "
            f"모델: {st.session_state.get('analysis_model', '-')}"
        )
    with heading_right:
        if pdf_bytes is not None:
            st.download_button(
                "PDF 보고서 다운로드",
                data=pdf_bytes,
                file_name=build_download_filename(st.session_state.get("analysis_filename")),
                mime="application/pdf",
                use_container_width=True,
            )

    metric_cols = st.columns(3, gap="medium")
    with metric_cols[0]:
        render_metric_card("예상 위험도", risk["label"], risk["note"], risk["tone"])
    with metric_cols[1]:
        render_metric_card(
            "관찰 신호",
            str(len(observed_signs)),
            "사진에서 추정된 신호 개수입니다.",
            "neutral",
        )
    with metric_cols[2]:
        render_metric_card(
            "추천 운동",
            str(len(exercises)),
            "바로 시작할 수 있는 운동 수입니다.",
            "neutral",
        )

    render_content_card(
        "Posture Summary",
        "자세 요약",
        f"<p>{format_html_text(result.get('posture_summary', '요약 정보가 없습니다.'))}</p>",
    )

    insight_cols = st.columns(2, gap="medium")
    with insight_cols[0]:
        render_content_card(
            "Observed Signs",
            "관찰 및 추정 신호",
            build_list_html(observed_signs, "관찰/추정 신호를 찾지 못했습니다."),
        )
    with insight_cols[1]:
        render_content_card(
            "Daily Habits",
            "생활 습관 교정",
            build_list_html(daily_habits, "생활 습관 교정 팁이 없습니다."),
        )

    st.markdown(
        """
        <div class="section-heading">
            <h2>추천 운동</h2>
            <p>부담이 적고 집이나 사무실에서 실천하기 쉬운 항목을 우선 정리했습니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not exercises:
        st.markdown(
            """
            <div class="empty-card">
                <div class="content-eyebrow">No Exercise</div>
                <h3>추천 운동 정보가 없습니다.</h3>
                <p>이미지를 다시 업로드하거나 다른 각도의 사진으로 한 번 더 분석해 보세요.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        exercise_cols = st.columns(2, gap="medium")
        for index, exercise in enumerate(exercises):
            with exercise_cols[index % 2]:
                render_exercise_card(exercise)

    warning_text = result.get("warning")
    if warning_text:
        st.markdown(
            f"""
            <div class="warning-card">
                <div class="content-eyebrow">Important</div>
                <h3>주의가 필요한 경우</h3>
                <p>{format_html_text(warning_text)}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )


def main() -> None:
    st.set_page_config(page_title="자세 기반 예방 운동 리포트", page_icon="🧍", layout="wide")
    initialize_state()
    apply_styles()
    render_hero()

    top_left, top_right = st.columns([1.25, 0.95], gap="large")
    uploaded = None
    image = None
    image_bytes: Optional[bytes] = None
    current_signature: Optional[str] = None

    with top_left:
        with st.container(border=True):
            st.markdown("<div class='panel-title'>사진 업로드</div>", unsafe_allow_html=True)
            st.markdown(
                "<div class='panel-copy'>정면 또는 측면에서 목, 어깨, 상체가 잘 보이는 사진을 올려주세요.</div>",
                unsafe_allow_html=True,
            )
            uploaded = st.file_uploader(
                "자세가 보이는 사진 업로드",
                type=["jpg", "jpeg", "png"],
                label_visibility="collapsed",
            )

            if uploaded is not None:
                image_bytes = uploaded.getvalue()
                current_signature = build_signature(image_bytes)
                image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                st.image(image, caption="업로드된 사진", use_container_width=True)

    with top_right:
        with st.container(border=True):
            st.markdown("<div class='panel-title'>분석 설정</div>", unsafe_allow_html=True)
            st.markdown(
                "<div class='panel-copy'>모델을 확인한 뒤 분석을 시작하세요. 분석 결과는 바로 보고서 형태로 정리됩니다.</div>",
                unsafe_allow_html=True,
            )
            default_model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
            model = st.text_input("OpenAI 모델", value=default_model, help="예: gpt-4.1-mini")
            st.caption("환경변수 `OPENAI_API_KEY`가 필요합니다.")
            analyze_clicked = st.button(
                "AI 분석 시작",
                type="primary",
                use_container_width=True,
                disabled=image is None,
            )

        st.markdown("<div style='height: 0.7rem'></div>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown(
                """
                <div class="mini-note">
                    <strong>이 앱이 해주는 일</strong>
                    사진에서 자세 위험 신호를 추정하고, 부위별 운동 방법, 권장량,
                    생활 습관 팁, 주의 문구까지 한 번에 정리합니다.
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(
                """
                <ul class="feature-list">
                    <li>결과를 보기 좋은 카드형 리포트로 표시</li>
                    <li>추천 운동 정보를 한글 PDF로 저장 가능</li>
                    <li>진단이 아닌 예방 목적의 참고 가이드 제공</li>
                </ul>
                """,
                unsafe_allow_html=True,
            )

    if analyze_clicked:
        if image is None or image_bytes is None or current_signature is None:
            st.error("먼저 사진을 업로드해 주세요.")
            st.stop()
        if not os.getenv("OPENAI_API_KEY"):
            st.error("`OPENAI_API_KEY` 환경변수가 설정되지 않았습니다.")
            st.stop()

        with st.spinner("사진을 분석하고 리포트를 정리하고 있습니다..."):
            try:
                result = analyze_posture(image, model=model)
                st.session_state["analysis_result"] = result
                st.session_state["analysis_signature"] = current_signature
                st.session_state["analysis_filename"] = uploaded.name if uploaded is not None else "image.jpg"
                st.session_state["analysis_image_bytes"] = image_to_jpeg_bytes(image)
                st.session_state["analysis_timestamp"] = datetime.now().isoformat(timespec="seconds")
                st.session_state["analysis_model"] = model
                st.success("분석이 완료되었습니다. 아래에서 결과를 확인하고 PDF로 내려받을 수 있습니다.")
            except Exception as exc:
                st.error(f"분석 중 오류가 발생했습니다: {exc}")

    active_result = st.session_state.get("analysis_result")
    active_signature = st.session_state.get("analysis_signature")

    if uploaded is not None and active_result and current_signature and active_signature != current_signature:
        st.info("새 사진이 업로드되었습니다. 최신 결과를 보려면 `AI 분석 시작` 버튼을 다시 눌러 주세요.")
        active_result = None

    if active_result and st.session_state.get("analysis_image_bytes"):
        pdf_bytes = None
        try:
            pdf_bytes = build_pdf_report_cached(
                json.dumps(active_result, ensure_ascii=False, sort_keys=True),
                st.session_state["analysis_image_bytes"],
                st.session_state.get("analysis_filename", "image.jpg"),
                format_timestamp(st.session_state.get("analysis_timestamp")),
            )
        except Exception as exc:
            st.warning(f"PDF 준비 중 문제가 발생했습니다: {exc}")

        render_result_dashboard(active_result, pdf_bytes)
    else:
        st.markdown(
            """
            <div class="section-heading">
                <h2>분석 전 안내</h2>
                <p>아래 조건을 맞추면 결과 품질이 더 좋아집니다.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            """
            <div class="empty-card">
                <div class="content-eyebrow">Preparation Tips</div>
                <h3>사진을 이렇게 준비해 보세요</h3>
                <p>몸통이 잘리거나 고개가 완전히 가려지지 않도록 촬영하면 더 정확한 추정에 도움이 됩니다.</p>
                <ul>
                    <li>목, 어깨, 등이 함께 보이는 구도 추천</li>
                    <li>앉은 자세라면 의자와 상체가 동시에 보이도록 촬영</li>
                    <li>어두운 사진보다 밝고 흔들림 없는 사진 사용</li>
                </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )


if __name__ == "__main__":
    main()
