# 📈 유튜브 투자 영상 분석 & 텔레그램 데일리 리포트 자동화 시스템

삼프로TV, 한경 코리아마켓, 한경 글로벌마켓, 와이스트릿 등 주요 투자 유튜브 채널의 지난 24시간 신규 영상 데이터를 수집하여, Google Gemini AI를 통해 4대 핵심 관점(시장 시황, 산업 동향, 기업 분석, 거시경제 리스크)의 투자 리포트를 생성하고 매일 오전 07시 텔레그램으로 자동 발송하는 파이썬 시스템입니다.

---

## 🌟 주요 기능 및 특징

1. **자동 신규 영상 수집 (`youtube_collector.py`)**
   - 별도의 YouTube API Key 제한 없이 공식 RSS 피드를 기반으로 4개 주요 채널의 최근 24시간 신규 영상 정보(제목, 링크, 설명, 업로드 시각)를 실시간 수집합니다.
2. **Gemini AI 4대 관점 리포트 생성 (`analyzer.py`)**
   - 최신 `google-genai` SDK를 사용하여 수집된 영상 데이터를 바탕으로 아래 **4대 핵심 관점**을 구체적으로 분석합니다.
     - **시장 시황 (Market Overview)**
     - **산업 동향 (Industry Trends)**
     - **기업 분석 (Company Analysis)**
     - **거시경제 리스크 (Macroeconomic Risks)**
3. **텔레그램 메시지 안전 분할 전송 (`telegram_sender.py`)**
   - 텔레그램 단일 메시지 글자 수 제한(4,096자)을 고려하여 `split_message` 함수가 문단 및 줄바꿈 단위로 안전하게 메시지를 나눈 후 순차 전송합니다.
4. **정기 스케줄링 (`main.py`)**
   - `schedule` 라이브러리를 활용하여 **매일 오전 07시 00분**에 자동 실행됩니다.

---

## 🛠️ 설치 및 환경 설정 Guide

### 1. 패키지 설치
필요한 파이썬 라이브러리를 설치합니다:
```bash
pip install -r requirements.txt
```

### 2. `.env` 파일 환경변수 설정
프로젝트 루트 폴더의 `.env` 파일을 열고 본인의 API 토큰 정보를 입력합니다:

```env
# 텔레그램 봇 토큰 (BotFather를 통해 생성)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here

# 텔레그램 Chat ID (개인 Chat ID 또는 채널/그룹 Chat ID)
TELEGRAM_CHAT_ID=your_telegram_chat_id_here

# Google Gemini API Key
GEMINI_API_KEY=your_gemini_api_key_here
```

---

## 🚀 실행 방법

### 1. 즉시 리포트 수집 및 전송 테스트 (`--now`)
스케줄러 대기 없이 즉시 영상을 수집하고 리포트를 생성하여 텔레그램으로 전송합니다:
```bash
python main.py --now
```

### 2. 매일 오전 07시 스케줄러 실행
프로그램을 실행해 두면 매일 오전 07:00에 수집 및 전송 작업이 진행됩니다:
```bash
python main.py
```

---

## 📂 프로젝트 파일 구조

```
.
├── .env                 # API 토큰 및 설정값 보관 (보안 주의)
├── .env.example         # 환경변수 설정 예시 템플릿
├── config.py            # 채널 설정 및 환경변수 로더
├── youtube_collector.py # 유튜브 RSS 피드 수집 모듈
├── analyzer.py          # Gemini AI 리포트 생성 분석 모듈
├── telegram_sender.py   # 텔레그램 메시지 분할 & 전송 모듈
├── main.py              # 메인 스케줄러 실행 엔트리포인트
├── requirements.txt     # 파이썬 의존성 패키지 목록
└── README.md            # 사용 가이드 문서
```
