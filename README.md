# 사진 기반 근골격계질환 예방 운동 추천 프로그램

업로드한 사진을 바탕으로 자세 위험 신호를 추정하고, 근골격계질환 예방을 위한 운동/생활습관 가이드를 한국어로 제공합니다.

## 1) 설치

```bash
pip install -r requirements.txt
```

## 2) 환경변수 설정

`OPENAI_API_KEY`를 설정하세요.

PowerShell 예시:

```powershell
$env:OPENAI_API_KEY="your_api_key_here"
```

선택: 모델 지정

```powershell
$env:OPENAI_MODEL="gpt-4.1-mini"
```

## 3) 실행

```bash
streamlit run app.py
```

## 4) 사용 방법

1. 자세가 잘 보이는 사진(jpg/png)을 업로드합니다.
2. `분석하고 운동 추천 받기` 버튼을 누릅니다.
3. 위험도, 관찰 신호, 추천 운동, 생활 습관 교정 팁을 확인합니다.

## 주의

- 이 프로그램은 예방 목적의 일반 가이드이며 의료 진단이 아닙니다.
- 통증, 저림, 감각 이상, 근력 저하가 있으면 의료진 상담이 필요합니다.
