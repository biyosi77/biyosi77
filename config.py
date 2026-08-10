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

# Gemini 모델 설정 (기본: gemini-3.6-flash 또는 gemini-flash-latest)
GEMINI_MODEL_NAME = "gemini-3.6-flash"


# 모니터링 대상 유튜브 채널 목록 (검증된 Channel ID)
TARGET_CHANNELS = [
    {
        "name": "삼프로TV",
        "channel_id": "UChlv4GSd7OQl3js-jkLOnFA",
        "rss_url": "https://www.youtube.com/feeds/videos.xml?channel_id=UChlv4GSd7OQl3js-jkLOnFA"
    },
    {
        "name": "한경 코리아마켓",
        "channel_id": "UC7cF2ZYvGm_zgrX-xCV88mA",
        "rss_url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC7cF2ZYvGm_zgrX-xCV88mA"
    },
    {
        "name": "한경 글로벌마켓",
        "channel_id": "UCWskYkV4c4S9D__rsfOl2JA",
        "rss_url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCWskYkV4c4S9D__rsfOl2JA"
    },
    {
        "name": "와이스트릿",
        "channel_id": "UCupslRq5jW95UGzPjOZz0FA",
        "rss_url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCupslRq5jW95UGzPjOZz0FA"
    }
]

# 텔레그램 메시지 길이 제한
TELEGRAM_MAX_MESSAGE_LENGTH = 4000
