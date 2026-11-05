import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 환경 변수 및 자동 포맷 정화 (따옴표 제거 & 채널 ID 마이너스(-) 자동 보정)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip().strip('"').strip("'")
_raw_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip().strip('"').strip("'")
if _raw_chat_id and _raw_chat_id.startswith("100") and not _raw_chat_id.startswith("-"):
    _raw_chat_id = "-" + _raw_chat_id
TELEGRAM_CHAT_ID = _raw_chat_id
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'")

# Gemini 모델 설정 (기본: gemini-3.8-flash 또는 gemini-flash-latest)
GEMINI_MODEL_NAME = "gemini-3.8-flash"

# 모니터링 대상 3대 핵심 투자 채널 설정
TARGET_CHANNELS = {
    "mk_invest": {
        "name": "매경 월가월부",
        "channel_id": "UCIipmgxpUxDmPP-ma3Ahvbw",
        "rss_url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCIipmgxpUxDmPP-ma3Ahvbw",
        "keywords": ["빅머니", "문지웅"]
    },
    "sampro": {
        "name": "삼프로TV",
        "channel_id": "UChlv4GSd7OQl3js-jkLOnFA",
        "rss_url": "https://www.youtube.com/feeds/videos.xml?channel_id=UChlv4GSd7OQl3js-jkLOnFA",
        "programs": {
            "wallstreet": ["월스트리트", "모닝 브리핑", "모닝브리핑"],
            "closingbell": ["클로징벨", "클로징 벨"],
            "yeouido": ["여의도 인사이트", "여의도인사이트"],
            "market_inside": ["마켓인사이드", "마켓 인사이드"]
        }
    },
    "chesley": {
        "name": "체슬리TV",
        "handle": "@chesleytv",
        "channel_id": "UCXST0Hq6CAmG0dmo3jgrlEw",
        "streams_url": "https://www.youtube.com/@chesleytv/streams",
        "programs": {
            "morning": ["모닝브리프", "운용회의"],
            "weekend": ["별주부전"]
        }
    }
}

# 텔레그램 메시지 길이 제한
TELEGRAM_MAX_MESSAGE_LENGTH = 4000
