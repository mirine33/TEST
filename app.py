import base64
import io
import json
import os
from typing import Any, Dict

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
                    {
                        "type": "input_text",
                        "text": "사진을 분석해 JSON으로 답변해줘.",
                    },
                    {"type": "input_image", "image_url": data_url},
                ],
            },
        ],
        temperature=0.2,
    )

    output_text = getattr(response, "output_text", None)
    if not output_text:
        # SDK 버전에 따라 output_text가 없을 수 있어 fallback 처리
        output_text = ""
        for item in getattr(response, "output", []):
            for content in getattr(item, "content", []):
                if getattr(content, "type", "") == "output_text":
                    output_text += getattr(content, "text", "")

    if not output_text:
        raise RuntimeError("모델 응답을 텍스트로 읽지 못했습니다.")

    return extract_json_text(output_text)


def render_result(data: Dict[str, Any]) -> None:
    st.subheader("분석 요약")
    st.write(data.get("posture_summary", "요약 정보 없음"))

    risk_level = data.get("risk_level", "unknown")
    risk_label = {
        "low": "낮음",
        "medium": "중간",
        "high": "높음",
    }.get(str(risk_level).lower(), str(risk_level))
    st.metric("예상 위험도", risk_label)

    st.subheader("관찰/추정 신호")
    for sign in data.get("observed_signs", []):
        st.write(f"- {sign}")

    st.subheader("추천 운동")
    exercises = data.get("recommended_exercises", [])
    if not exercises:
        st.info("추천 운동 정보가 없습니다.")
    for ex in exercises:
        with st.expander(ex.get("name", "운동")):
            st.write(f"대상 부위: {ex.get('target', '-')}")
            st.write(f"방법: {ex.get('how_to', '-')}")
            st.write(f"권장량: {ex.get('sets_reps', '-')}")
            st.write(f"빈도: {ex.get('frequency', '-')}")
            st.write(f"주의사항: {ex.get('caution', '-')}")

    st.subheader("생활 습관 교정")
    for habit in data.get("daily_habits", []):
        st.write(f"- {habit}")

    warning = data.get("warning")
    if warning:
        st.warning(warning)


def main() -> None:
    st.set_page_config(page_title="근골격계질환 예방 운동 추천", page_icon="🧍", layout="centered")
    st.title("사진 기반 근골격계질환 예방 운동 추천")
    st.caption("사진을 기반으로 자세를 추정해 예방 운동을 제안합니다. 의료 진단 서비스가 아닙니다.")

    with st.sidebar:
        st.header("설정")
        default_model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        model = st.text_input("OpenAI 모델", value=default_model)
        st.write("환경변수 `OPENAI_API_KEY` 가 필요합니다.")

    uploaded = st.file_uploader("자세가 보이는 전신/상반신 사진 업로드", type=["jpg", "jpeg", "png"])

    if uploaded:
        image = Image.open(uploaded).convert("RGB")
        st.image(image, caption="업로드된 사진", use_container_width=True)

        if st.button("분석하고 운동 추천 받기", type="primary"):
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
