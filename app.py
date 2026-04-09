import base64
import io
import json
import os
from typing import Any, Dict, List

import streamlit as st
from openai import OpenAI
from PIL import Image


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


def apply_styles() -> None:
    st.markdown(
        """
        <style>
            :root {
                --bg: #f6fbf9;
                --panel: #ffffff;
                --primary: #127b62;
                --primary-soft: #d7efe7;
                --text: #11322b;
                --warn: #f7b500;
                --danger: #e24a4a;
            }
            .stApp {
                background: radial-gradient(circle at 20% 0%, #e7f6f0 0, var(--bg) 55%);
                color: var(--text);
            }
            .hero {
                background: linear-gradient(125deg, #106b56, #1a8f71);
                color: white;
                border-radius: 14px;
                padding: 18px 18px 14px 18px;
                margin-bottom: 12px;
            }
            .hero h1 {
                margin: 0;
                font-size: 1.45rem;
                letter-spacing: -0.3px;
            }
            .hero p {
                margin: 6px 0 0 0;
                opacity: 0.95;
                font-size: 0.95rem;
            }
            .step {
                background: var(--panel);
                border: 1px solid #dbe7e2;
                border-left: 4px solid var(--primary);
                border-radius: 10px;
                padding: 10px 12px;
                margin: 6px 0;
                font-size: 0.92rem;
            }
            .risk-badge {
                display: inline-block;
                border-radius: 999px;
                padding: 4px 10px;
                font-size: 0.83rem;
                font-weight: 700;
            }
            .risk-low { background: #d7f3e5; color: #0f6c49; }
            .risk-medium { background: #fff1cf; color: #8e5d00; }
            .risk-high { background: #ffd8d8; color: #9f1f1f; }
            .exercise-card {
                background: var(--panel);
                border: 1px solid #dbe7e2;
                border-radius: 12px;
                padding: 12px;
                margin-bottom: 10px;
            }
            .exercise-title {
                color: var(--primary);
                font-size: 1.02rem;
                font-weight: 700;
                margin-bottom: 4px;
            }
            .label {
                font-weight: 700;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def image_to_data_url(image: Image.Image) -> str:
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG")
    img_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{img_base64}"


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
    low_level = str(level).lower()
    if low_level == "low":
        return {"label": "낮음", "class": "risk-low", "emoji": "🟢"}
    if low_level == "medium":
        return {"label": "중간", "class": "risk-medium", "emoji": "🟠"}
    if low_level == "high":
        return {"label": "높음", "class": "risk-high", "emoji": "🔴"}
    return {"label": str(level), "class": "risk-medium", "emoji": "🟠"}


def render_list(items: List[str], empty_text: str) -> None:
    if not items:
        st.info(empty_text)
        return
    for item in items:
        st.markdown(f"- {item}")


def render_result(data: Dict[str, Any]) -> None:
    st.markdown("## 분석 결과")
    posture_summary = data.get("posture_summary", "요약 정보가 없습니다.")
    risk = risk_meta(data.get("risk_level", "unknown"))

    col1, col2 = st.columns([2, 1], gap="small")
    with col1:
        st.write(posture_summary)
    with col2:
        st.metric("예상 위험도", f"{risk['emoji']} {risk['label']}")
        st.markdown(
            f"<span class='risk-badge {risk['class']}'>예방 관리 권장</span>",
            unsafe_allow_html=True,
        )

    tab1, tab2, tab3 = st.tabs(["관찰 신호", "추천 운동", "생활 습관"])

    with tab1:
        render_list(
            data.get("observed_signs", []),
            "관찰/추정 신호를 찾지 못했습니다.",
        )

    with tab2:
        exercises = data.get("recommended_exercises", [])
        if not exercises:
            st.info("추천 운동 정보가 없습니다.")
        for ex in exercises:
            st.markdown(
                (
                    "<div class='exercise-card'>"
                    f"<div class='exercise-title'>{ex.get('name', '운동')}</div>"
                    f"<div><span class='label'>대상 부위</span>: {ex.get('target', '-')}</div>"
                    f"<div><span class='label'>방법</span>: {ex.get('how_to', '-')}</div>"
                    f"<div><span class='label'>권장량</span>: {ex.get('sets_reps', '-')}</div>"
                    f"<div><span class='label'>빈도</span>: {ex.get('frequency', '-')}</div>"
                    f"<div><span class='label'>주의</span>: {ex.get('caution', '-')}</div>"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )

    with tab3:
        render_list(data.get("daily_habits", []), "생활 습관 교정 팁이 없습니다.")

    warning = data.get("warning")
    if warning:
        st.warning(warning)


def main() -> None:
    st.set_page_config(page_title="자세 기반 예방 운동 추천", page_icon="🧍", layout="wide")
    apply_styles()

    st.markdown(
        """
        <div class="hero">
            <h1>사진 기반 근골격계 예방 운동 추천</h1>
            <p>사진 한 장으로 자세 위험 신호를 추정하고, 바로 실천할 수 있는 운동을 안내합니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    left, right = st.columns([1.15, 1], gap="large")

    with left:
        st.markdown("### 사용 순서")
        st.markdown("<div class='step'>1) 자세가 잘 보이는 사진을 업로드하세요.</div>", unsafe_allow_html=True)
        st.markdown("<div class='step'>2) 분석 버튼을 누르고 5~10초 기다리세요.</div>", unsafe_allow_html=True)
        st.markdown("<div class='step'>3) 위험도와 운동/생활 습관 가이드를 확인하세요.</div>", unsafe_allow_html=True)

        uploaded = st.file_uploader(
            "자세가 보이는 사진 업로드 (jpg, jpeg, png)",
            type=["jpg", "jpeg", "png"],
        )

        if uploaded:
            image = Image.open(uploaded).convert("RGB")
            st.image(image, caption="업로드된 사진", use_container_width=True)
            run = st.button("분석하고 운동 추천 받기", type="primary", use_container_width=True)
        else:
            image = None
            run = False

    with right:
        st.markdown("### 설정")
        default_model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        model = st.text_input("OpenAI 모델", value=default_model, help="예: gpt-4.1-mini")
        st.caption("환경변수 `OPENAI_API_KEY`가 필요합니다.")
        st.info("이 서비스는 의료 진단이 아닌 예방 목적의 참고 가이드입니다.")

    if run and image is not None:
        if not os.getenv("OPENAI_API_KEY"):
            st.error("`OPENAI_API_KEY` 환경변수가 설정되지 않았습니다.")
            st.stop()

        with st.spinner("사진을 분석하고 있습니다..."):
            try:
                result = analyze_posture(image, model=model)
                render_result(result)
            except Exception as exc:
                st.error(f"분석 중 오류가 발생했습니다: {exc}")


if __name__ == "__main__":
    main()
