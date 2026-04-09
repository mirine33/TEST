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

PHOTO_SLOTS = (
    {
        "key": "front",
        "title": "정면 사진",
        "description": "어깨와 골반의 좌우 높이, 몸통 중심 정렬을 확인하기 좋습니다.",
        "short": "정면",
    },
    {
        "key": "side",
        "title": "측면 사진",
        "description": "고개 전방 자세, 흉추 굴곡, 골반 기울기 추정에 도움이 됩니다.",
        "short": "측면",
    },
    {
        "key": "seated",
        "title": "의자에 앉은 자세",
        "description": "업무 자세, 허리 지지, 앉은 상태의 좌우 밸런스를 확인합니다.",
        "short": "앉은 자세",
    },
)

SYSTEM_PROMPT = """
당신은 물리치료/운동 코치 보조 AI입니다.
입력으로 정면 사진, 측면 사진, 의자에 앉은 자세 사진 총 3장이 제공됩니다.
이 3장을 함께 보고 근골격계질환 예방 관점에서 자세 위험 신호를 추정하고 운동을 제안하세요.

중요:
1) 진단이 아니라 예방 목적의 일반 가이드로 작성한다.
2) 사진만으로 확정할 수 없는 내용은 반드시 "추정"이라고 표현한다.
3) 좌우 밸런스(어깨 높이, 몸통 기울기, 체중 분배, 골반 수평 추정)를 반드시 체크한다.
4) 전체 결과는 1단계~5단계로 세분화한다.
5) 단계 의미는 다음과 같다.
   - 1단계: 매우 양호
   - 2단계: 경미한 불균형
   - 3단계: 주의 필요
   - 4단계: 교정 필요
   - 5단계: 집중 관리 필요
6) 과격한 운동은 피하고 초보자가 집이나 사무실에서 할 수 있는 운동을 우선 추천한다.
7) 반드시 한국어로 작성한다.
8) 아래 JSON 형식으로만 응답한다. 코드블록 금지.
9) 각 사진별 분석은 front, side, seated 키에 맞춰 작성한다.

{
  "overall_summary": "전체 자세 한 문단 요약",
  "overall_level": 1,
  "overall_reason": "왜 이 단계를 판단했는지 1~2문장",
  "observed_signs": ["전체 관점 핵심 신호1", "핵심 신호2"],
  "left_right_balance": {
    "level": 1,
    "summary": "좌우 밸런스 한 문단 요약",
    "findings": ["좌우 밸런스 관련 관찰/추정 1", "관찰/추정 2"]
  },
  "view_analysis": {
    "front": {
      "summary": "정면 사진 요약",
      "findings": ["정면 관찰/추정 1", "정면 관찰/추정 2"]
    },
    "side": {
      "summary": "측면 사진 요약",
      "findings": ["측면 관찰/추정 1", "측면 관찰/추정 2"]
    },
    "seated": {
      "summary": "앉은 자세 사진 요약",
      "findings": ["앉은 자세 관찰/추정 1", "앉은 자세 관찰/추정 2"]
    }
  },
  "priority_areas": ["우선 관리 부위1", "우선 관리 부위2"],
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
        "analysis_filenames": None,
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


def build_bundle_signature(image_bytes_map: Dict[str, bytes]) -> str:
    digest = hashlib.sha1()
    for slot in PHOTO_SLOTS:
        slot_key = slot["key"]
        digest.update(slot_key.encode("utf-8"))
        digest.update(image_bytes_map[slot_key])
    return digest.hexdigest()


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


def analyze_posture(images: Dict[str, Image.Image], model: str) -> Dict[str, Any]:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    content = [
        {
            "type": "input_text",
            "text": (
                "정면, 측면, 앉은 자세 사진을 함께 분석해서 "
                "좌우 밸런스와 5단계 결과를 포함한 JSON으로 답변해줘."
            ),
        }
    ]

    for slot in PHOTO_SLOTS:
        slot_key = slot["key"]
        content.append(
            {
                "type": "input_text",
                "text": f"{slot['title']}입니다. 이 관점의 특징을 반영해 분석해줘.",
            }
        )
        content.append(
            {
                "type": "input_image",
                "image_url": image_to_data_url(images[slot_key]),
            }
        )

    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": [{"type": "input_text", "text": SYSTEM_PROMPT}],
            },
            {
                "role": "user",
                "content": content,
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


def risk_meta(level: Any) -> Dict[str, str]:
    try:
        normalized = int(level)
    except (TypeError, ValueError):
        normalized = 3

    if normalized <= 1:
        return {
            "label": "1단계",
            "title": "매우 양호",
            "badge": "1단계 · 매우 양호",
            "tone": "low",
            "note": "현재 사진 기준으로는 큰 불균형이 적은 편으로 보입니다.",
            "pdf_color": "#2E8B57",
        }
    if normalized == 2:
        return {
            "label": "2단계",
            "title": "경미한 불균형",
            "badge": "2단계 · 경미한 불균형",
            "tone": "low",
            "note": "작은 불균형이 보여 생활 습관과 가벼운 교정 운동이 도움이 됩니다.",
            "pdf_color": "#4C9E68",
        }
    if normalized == 3:
        return {
            "label": "3단계",
            "title": "주의 필요",
            "badge": "3단계 · 주의 필요",
            "tone": "medium",
            "note": "누적 피로와 통증 예방을 위해 정기적인 관리가 필요해 보입니다.",
            "pdf_color": "#B7791F",
        }
    if normalized == 4:
        return {
            "label": "4단계",
            "title": "교정 필요",
            "badge": "4단계 · 교정 필요",
            "tone": "high",
            "note": "자세 교정과 운동 습관 개선을 더 적극적으로 시작하는 것이 좋습니다.",
            "pdf_color": "#D16A33",
        }
    return {
        "label": "5단계",
        "title": "집중 관리 필요",
        "badge": "5단계 · 집중 관리 필요",
        "tone": "high",
        "note": "불균형이 비교적 뚜렷해 보여 집중적인 예방 관리가 필요해 보입니다.",
        "pdf_color": "#C84F46",
    }


def get_view_data(result: Dict[str, Any], key: str) -> Dict[str, Any]:
    return result.get("view_analysis", {}).get(key, {})


def count_observed_signs(result: Dict[str, Any]) -> int:
    total = len(result.get("observed_signs", []))
    balance = result.get("left_right_balance", {})
    total += len(balance.get("findings", []))
    for slot in PHOTO_SLOTS:
        total += len(get_view_data(result, slot["key"]).get("findings", []))
    return total


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
            <h1 class="hero-title">세 방향 사진을<br>정밀한 예방 리포트로</h1>
            <p class="hero-copy">
                정면, 측면, 앉은 자세 사진을 함께 분석해 좌우 밸런스와 자세 습관을 더 세밀하게 읽고
                5단계 결과와 실행 가능한 교정 가이드를 보고서처럼 정리합니다.
            </p>
            <div class="hero-pills">
                <span class="hero-pill">3면 사진 분석</span>
                <span class="hero-pill">좌우 밸런스 체크</span>
                <span class="hero-pill">5단계 결과</span>
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
    overall = risk_meta(data.get("overall_level", 3))
    balance = risk_meta(data.get("left_right_balance", {}).get("level", 3))
    observed_count = count_observed_signs(data)

    metric_rows = [
        [
            Paragraph("전체 분석 단계", styles["label"]),
            Paragraph(pdf_text(overall["label"]), styles["value"]),
            Paragraph("좌우 밸런스", styles["label"]),
            Paragraph(pdf_text(balance["label"]), styles["value"]),
            Paragraph("관찰 포인트 수", styles["label"]),
            Paragraph(str(observed_count), styles["value"]),
        ],
        [
            Paragraph(pdf_text(f"{overall['title']} · {overall['note']}"), styles["small"]),
            "",
            Paragraph(
                pdf_text(
                    f"{balance['title']} · "
                    f"{data.get('left_right_balance', {}).get('summary', '좌우 밸런스 요약 정보가 없습니다.')}"
                ),
                styles["small"],
            ),
            "",
            Paragraph("전체 시야와 사진별 관찰을 합산한 참고 개수입니다.", styles["small"]),
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
    image_bytes_map: Dict[str, bytes],
    image_names: Dict[str, str],
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
    story.append(Paragraph("분석 자료: 정면, 측면, 앉은 자세 3종", styles["meta"]))
    story.append(build_metric_table(report_data, styles))
    story.append(Spacer(1, 12))

    story.append(Paragraph("전체 자세 요약", styles["section"]))
    story.append(Paragraph(pdf_text(report_data.get("overall_summary", "요약 정보가 없습니다.")), styles["body"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph(pdf_text(report_data.get("overall_reason", "판단 이유 정보가 없습니다.")), styles["body"]))
    story.append(Spacer(1, 10))

    story.append(build_bullet_table("핵심 관찰 신호", report_data.get("observed_signs", []), styles))
    story.append(Spacer(1, 10))
    story.append(build_bullet_table("우선 관리 부위", report_data.get("priority_areas", []), styles))
    story.append(Spacer(1, 10))

    balance = report_data.get("left_right_balance", {})
    balance_header = f"좌우 밸런스 ({risk_meta(balance.get('level', 3))['badge']})"
    story.append(Paragraph(balance_header, styles["section"]))
    story.append(Paragraph(pdf_text(balance.get("summary", "좌우 밸런스 요약 정보가 없습니다.")), styles["body"]))
    story.append(Spacer(1, 8))
    story.append(build_bullet_table("좌우 밸런스 세부 관찰", balance.get("findings", []), styles))
    story.append(Spacer(1, 10))

    story.append(Paragraph("사진별 분석", styles["section"]))
    for slot in PHOTO_SLOTS:
        slot_data = get_view_data(report_data, slot["key"])
        story.append(Paragraph(slot["title"], styles["card_title"]))
        story.append(Paragraph(pdf_text(image_names.get(slot["key"], "-")), styles["meta"]))
        if slot["key"] in image_bytes_map:
            story.append(fit_pdf_image(image_bytes_map[slot["key"]], doc.width, 56 * mm))
            story.append(Spacer(1, 6))
        story.append(Paragraph(pdf_text(slot_data.get("summary", "요약 정보가 없습니다.")), styles["body"]))
        story.append(Spacer(1, 6))
        story.append(build_bullet_table(f"{slot['short']} 관찰 포인트", slot_data.get("findings", []), styles))
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
    front_image_bytes: bytes,
    side_image_bytes: bytes,
    seated_image_bytes: bytes,
    front_image_name: str,
    side_image_name: str,
    seated_image_name: str,
    analyzed_at: str,
) -> bytes:
    return build_pdf_report(
        json.loads(report_json),
        {
            "front": front_image_bytes,
            "side": side_image_bytes,
            "seated": seated_image_bytes,
        },
        {
            "front": front_image_name,
            "side": side_image_name,
            "seated": seated_image_name,
        },
        analyzed_at,
    )


def build_download_filename(image_name: Optional[Any]) -> str:
    if isinstance(image_name, dict):
        image_name = image_name.get("front") or image_name.get("side") or image_name.get("seated")
    stem = Path(str(image_name or "analysis")).stem
    safe_stem = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in stem)
    return f"{safe_stem}_multiview_report.pdf"


def format_timestamp(iso_text: Optional[str]) -> str:
    if not iso_text:
        return "-"
    try:
        parsed = datetime.fromisoformat(iso_text)
        return parsed.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso_text


def render_result_dashboard(result: Dict[str, Any], pdf_bytes: Optional[bytes]) -> None:
    overall = risk_meta(result.get("overall_level", 3))
    balance = result.get("left_right_balance", {})
    balance_meta = risk_meta(balance.get("level", 3))
    observed_signs = result.get("observed_signs", [])
    exercises = result.get("recommended_exercises", [])
    daily_habits = result.get("daily_habits", [])
    priority_areas = result.get("priority_areas", [])

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
        render_metric_card("전체 분석 단계", overall["badge"], overall["note"], overall["tone"])
    with metric_cols[1]:
        render_metric_card(
            "좌우 밸런스",
            balance_meta["badge"],
            balance.get("summary", "좌우 밸런스 요약 정보가 없습니다."),
            balance_meta["tone"],
        )
    with metric_cols[2]:
        render_metric_card(
            "추천 운동",
            str(len(exercises)),
            "바로 시작할 수 있는 운동 수입니다.",
            "neutral",
        )

    render_content_card(
        "Overall Summary",
        "전체 자세 요약",
        (
            f"<p>{format_html_text(result.get('overall_summary', '요약 정보가 없습니다.'))}</p>"
            f"<p style='margin-top:0.7rem'>{format_html_text(result.get('overall_reason', '판단 이유 정보가 없습니다.'))}</p>"
        ),
    )

    insight_cols = st.columns(2, gap="medium")
    with insight_cols[0]:
        render_content_card(
            "Observed Signs",
            "핵심 관찰 신호",
            build_list_html(observed_signs, "관찰/추정 신호를 찾지 못했습니다."),
        )
    with insight_cols[1]:
        render_content_card(
            "Priority Areas",
            "우선 관리 부위",
            build_list_html(priority_areas, "우선 관리 부위 정보가 없습니다."),
        )

    st.markdown(
        """
        <div class="section-heading">
            <h2>사진별 분석</h2>
            <p>정면, 측면, 앉은 자세를 각각 나누어 관찰 포인트를 정리했습니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    view_cols = st.columns(3, gap="medium")
    for index, slot in enumerate(PHOTO_SLOTS):
        slot_data = get_view_data(result, slot["key"])
        with view_cols[index]:
            render_content_card(
                slot["short"],
                slot["title"],
                (
                    f"<p>{format_html_text(slot_data.get('summary', '요약 정보가 없습니다.'))}</p>"
                    f"{build_list_html(slot_data.get('findings', []), '세부 관찰 포인트가 없습니다.')}"
                ),
            )

    balance_cols = st.columns(2, gap="medium")
    with balance_cols[0]:
        render_content_card(
            "Balance Check",
            "좌우 밸런스 세부 관찰",
            build_list_html(balance.get("findings", []), "좌우 밸런스 세부 관찰 정보가 없습니다."),
        )
    with balance_cols[1]:
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

    st.markdown(
        """
        <div class="section-heading">
            <h2>사진 업로드</h2>
            <p>정면, 측면, 의자에 앉은 자세 사진을 모두 올리면 좌우 밸런스와 5단계 결과를 함께 분석합니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    upload_cols = st.columns(3, gap="medium")
    uploaded_files: Dict[str, Any] = {}
    images: Dict[str, Image.Image] = {}
    image_bytes_map: Dict[str, bytes] = {}
    current_signature: Optional[str] = None

    for index, slot in enumerate(PHOTO_SLOTS):
        with upload_cols[index]:
            with st.container(border=True):
                st.markdown(f"<div class='panel-title'>{slot['title']}</div>", unsafe_allow_html=True)
                st.markdown(
                    f"<div class='panel-copy'>{slot['description']}</div>",
                    unsafe_allow_html=True,
                )
                uploaded = st.file_uploader(
                    slot["title"],
                    type=["jpg", "jpeg", "png"],
                    key=f"upload_{slot['key']}",
                    label_visibility="collapsed",
                )
                uploaded_files[slot["key"]] = uploaded

                if uploaded is not None:
                    raw_bytes = uploaded.getvalue()
                    image_bytes_map[slot["key"]] = raw_bytes
                    images[slot["key"]] = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
                    st.image(images[slot["key"]], caption=uploaded.name, use_container_width=True)
                else:
                    st.caption("아직 업로드되지 않았습니다.")

    if len(image_bytes_map) == len(PHOTO_SLOTS):
        current_signature = build_bundle_signature(image_bytes_map)

    control_left, control_right = st.columns([1.15, 0.85], gap="large")
    with control_left:
        with st.container(border=True):
            st.markdown("<div class='panel-title'>분석 설정</div>", unsafe_allow_html=True)
            st.markdown(
                "<div class='panel-copy'>세 장의 사진이 모두 준비되면 좌우 비대칭과 자세 습관을 종합해서 분석합니다.</div>",
                unsafe_allow_html=True,
            )
            default_model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
            model = st.text_input("OpenAI 모델", value=default_model, help="예: gpt-4.1-mini")
            st.caption("환경변수 `OPENAI_API_KEY`가 필요합니다.")
            analyze_clicked = st.button(
                "3면 자세 분석 시작",
                type="primary",
                use_container_width=True,
                disabled=len(images) != len(PHOTO_SLOTS),
            )

            if len(images) != len(PHOTO_SLOTS):
                st.info("정면, 측면, 의자에 앉은 자세 사진을 모두 업로드하면 분석 버튼이 활성화됩니다.")
            else:
                st.success("세 장의 사진이 준비되었습니다. 분석을 시작할 수 있습니다.")

    with control_right:
        with st.container(border=True):
            st.markdown("<div class='panel-title'>분석 포인트</div>", unsafe_allow_html=True)
            st.markdown(
                "<div class='panel-copy'>사진 세 장을 종합해 아래 항목을 함께 판단합니다.</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                """
                <div class="mini-note">
                    <strong>이 앱이 해주는 일</strong>
                    정면에서 좌우 높이 차를 보고, 측면에서 머리와 등 정렬을 보고,
                    앉은 자세에서 업무 습관과 체중 분배를 함께 추정합니다.
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(
                """
                <ul class="feature-list">
                    <li>전체 자세를 1단계부터 5단계까지 세분화</li>
                    <li>좌우 밸런스를 별도 단계로 정리</li>
                    <li>정면, 측면, 앉은 자세별 관찰 포인트 제공</li>
                    <li>추천 운동과 PDF 보고서까지 한 번에 생성</li>
                </ul>
                """,
                unsafe_allow_html=True,
            )

    if analyze_clicked:
        if len(images) != len(PHOTO_SLOTS) or current_signature is None:
            st.error("정면, 측면, 의자에 앉은 자세 사진을 모두 업로드해 주세요.")
            st.stop()
        if not os.getenv("OPENAI_API_KEY"):
            st.error("`OPENAI_API_KEY` 환경변수가 설정되지 않았습니다.")
            st.stop()

        with st.spinner("세 장의 사진을 분석하고 리포트를 정리하고 있습니다..."):
            try:
                result = analyze_posture(images, model=model)
                st.session_state["analysis_result"] = result
                st.session_state["analysis_signature"] = current_signature
                st.session_state["analysis_filename"] = {
                    slot["key"]: uploaded_files[slot["key"]].name
                    for slot in PHOTO_SLOTS
                }
                st.session_state["analysis_filenames"] = st.session_state["analysis_filename"]
                st.session_state["analysis_image_bytes"] = {
                    slot["key"]: image_to_jpeg_bytes(images[slot["key"]])
                    for slot in PHOTO_SLOTS
                }
                st.session_state["analysis_timestamp"] = datetime.now().isoformat(timespec="seconds")
                st.session_state["analysis_model"] = model
                st.success("분석이 완료되었습니다. 아래에서 결과를 확인하고 PDF로 내려받을 수 있습니다.")
            except Exception as exc:
                st.error(f"분석 중 오류가 발생했습니다: {exc}")

    active_result = st.session_state.get("analysis_result")
    active_signature = st.session_state.get("analysis_signature")

    if active_result and any(uploaded_files.values()) and len(images) != len(PHOTO_SLOTS):
        st.info("새 분석용 사진을 업로드하는 중입니다. 세 장이 모두 준비되면 다시 분석해 주세요.")
        active_result = None

    if active_result and current_signature and active_signature != current_signature:
        st.info("업로드된 사진이 바뀌었습니다. 최신 결과를 보려면 `3면 자세 분석 시작` 버튼을 다시 눌러 주세요.")
        active_result = None

    if active_result and st.session_state.get("analysis_image_bytes"):
        pdf_bytes = None
        try:
            stored_images = st.session_state["analysis_image_bytes"]
            stored_names = st.session_state.get("analysis_filenames") or st.session_state.get("analysis_filename") or {}
            pdf_bytes = build_pdf_report_cached(
                json.dumps(active_result, ensure_ascii=False, sort_keys=True),
                stored_images["front"],
                stored_images["side"],
                stored_images["seated"],
                stored_names.get("front", "front.jpg"),
                stored_names.get("side", "side.jpg"),
                stored_names.get("seated", "seated.jpg"),
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
                <p>세 장의 사진이 서로 다른 관점을 보완해 줄수록 결과 품질이 좋아집니다.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            """
            <div class="empty-card">
                <div class="content-eyebrow">Preparation Tips</div>
                <h3>사진을 이렇게 준비해 보세요</h3>
                <p>정면, 측면, 앉은 자세를 각각 또렷하게 보여주면 좌우 밸런스와 습관성 자세를 더 잘 읽을 수 있습니다.</p>
                <ul>
                    <li>정면 사진은 어깨와 골반이 모두 보이게 촬영</li>
                    <li>측면 사진은 귀, 어깨, 골반 선이 보이게 촬영</li>
                    <li>앉은 자세 사진은 의자와 상체가 함께 보이게 촬영</li>
                    <li>어두운 사진보다 밝고 흔들림 없는 사진 사용</li>
                </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )


if __name__ == "__main__":
    main()
