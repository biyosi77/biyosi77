import sys
import asyncio
import logging
from typing import List
from telegram import Bot
from telegram.error import TelegramError
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_MAX_MESSAGE_LENGTH

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


logger = logging.getLogger(__name__)

def split_message(text: str, max_length: int = TELEGRAM_MAX_MESSAGE_LENGTH) -> List[str]:
    """
    텔레그램 메시지 길이 제한(4,096자)을 고려하여 문단 또는 줄바꿈 단위로 
    안전하게 메시지를 분할하는 함수입니다.
    """
    if len(text) <= max_length:
        return [text]

    chunks = []
    current_chunk = ""
    
    # 1단계: 문단(\n\n) 단위 분할
    paragraphs = text.split("\n\n")

    for paragraph in paragraphs:
        # 단일 문단 자체가 max_length를 초과할 경우 줄바꿈(\n) 단위로 2차 분할
        if len(paragraph) > max_length:
            lines = paragraph.split("\n")
            for line in lines:
                if len(current_chunk) + len(line) + 1 > max_length:
                    if current_chunk.strip():
                        chunks.append(current_chunk.strip())
                    current_chunk = line + "\n"
                else:
                    current_chunk += line + "\n"
            current_chunk += "\n"
        else:
            if len(current_chunk) + len(paragraph) + 2 > max_length:
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                current_chunk = paragraph + "\n\n"
            else:
                current_chunk += paragraph + "\n\n"

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks

async def send_telegram_report_async(text: str) -> bool:
    """
    python-telegram-bot 라이브러리를 사용하여 텔레그램으로 분할 메시지를 전송합니다.
    """
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "your_telegram_bot_token_here":
        logger.error("TELEGRAM_BOT_TOKEN이 설정되지 않았습니다. .env 파일을 확인해 주세요.")
        print("⚠️ [텔레그램 전송 취소] TELEGRAM_BOT_TOKEN이 없어서 콘솔에 리포트를 출력합니다:\n")
        print(text)
        return False

    if not TELEGRAM_CHAT_ID or TELEGRAM_CHAT_ID == "your_telegram_chat_id_here":
        logger.error("TELEGRAM_CHAT_ID가 설정되지 않았습니다. .env 파일을 확인해 주세요.")
        print("⚠️ [텔레그램 전송 취소] TELEGRAM_CHAT_ID가 없어서 콘솔에 리포트를 출력합니다:\n")
        print(text)
        return False

    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        chunks = split_message(text)
        logger.info(f"총 {len(chunks)}개의 분할 메시지를 텔레그램으로 전송합니다.")

        for idx, chunk in enumerate(chunks, 1):
            try:
                # HTML 모드로 안전하게 전송 시도
                await bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text=chunk,
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
            except TelegramError as te:
                logger.warning(f"HTML 파싱 오류 발생 ({te}). 일반 텍스트 모드로 재전송합니다.")
                # HTML 태그 오류 시 일반 텍스트로 안전 재전송
                await bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text=chunk,
                    disable_web_page_preview=True
                )
            
            # 메시지 연속 전송 간 1초 대기 (텔레그램 API rate limit 대응)
            if idx < len(chunks):
                await asyncio.sleep(1)

        logger.info("텔레그램 메시지 전송이 성공적으로 완료되었습니다.")
        return True

    except Exception as e:
        logger.error(f"텔레그램 메시지 전송 중 오류 발생: {e}")
        return False

def send_telegram_report(text: str) -> bool:
    """
    동기 환경에서 send_telegram_report_async 호출을 위한 래퍼 함수
    """
    return asyncio.run(send_telegram_report_async(text))

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sample_text = "테스트 메시지입니다. " * 300
    split_result = split_message(sample_text, max_length=500)
    print(f"Original length: {len(sample_text)}, Split count: {len(split_result)}")
    for i, c in enumerate(split_result, 1):
        print(f"--- Chunk {i} ({len(c)} chars) ---\n{c[:50]}...")
