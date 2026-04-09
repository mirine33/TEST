# 사진 기반 근골격계 예방 운동 리포트

사진을 업로드하면 자세 위험 신호를 추정하고, 근골격계질환 예방을 위한 운동과 생활 습관을 한국어 리포트로 보여주는 Streamlit 앱입니다.

## 주요 기능

- 사진 기반 자세 분석
- 카드형 결과 화면
- 운동 추천, 생활 습관 가이드, 주의 문구 제공
- 분석 결과 PDF 다운로드

## 설치

```bash
pip install -r requirements.txt
```

## 환경변수

PowerShell 예시:

```powershell
$env:OPENAI_API_KEY="your_api_key_here"
$env:OPENAI_MODEL="gpt-4.1-mini"
```

## 실행

```bash
streamlit run app.py
```

## 참고

- `assets/fonts/` 아래의 NanumGothic 폰트를 사용해 PDF에서 한글이 보이도록 구성했습니다.
- 이 앱은 의료 진단이 아니라 예방 목적의 참고 가이드입니다.
