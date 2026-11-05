import sys
import os
import asyncio
import logging
from typing import List, Optional
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

async def send_telegram_document_async(file_path: str, caption: str = "") -> bool:
    """
    생성된 PDF 리포트 파일을 텔레그램 채널로 전송합니다.
    """
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "your_telegram_bot_token_here":
        logger.error("TELEGRAM_BOT_TOKEN이 설정되지 않았습니다.")
        return False

    if not TELEGRAM_CHAT_ID or TELEGRAM_CHAT_ID == "your_telegram_chat_id_here":
        logger.error("TELEGRAM_CHAT_ID가 설정되지 않았습니다.")
        return False

    if not os.path.exists(file_path):
        logger.error(f"전송할 파일이 존재하지 않습니다: {file_path}")
        return False

    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        file_name = os.path.basename(file_path)
        logger.info(f"텔레그램으로 PDF 문서 전송 시작: {file_name} (수신 Chat ID: {TELEGRAM_CHAT_ID})")

        with open(file_path, "rb") as doc_file:
            await bot.send_document(
                chat_id=TELEGRAM_CHAT_ID,
                document=doc_file,
                filename=file_name,
                caption=caption[:1024] if caption else None,
                parse_mode="HTML" if caption else None
            )

        logger.info(f"✔ PDF 리포트 전송 성공: {file_name}")
        return True
    except Exception as e:
        logger.error(f"텔레그램 문서 전송 중 오류 발생: {e}", exc_info=True)
        return False

def send_telegram_document(file_path: str, caption: str = "") -> bool:
    """
    동기 환경에서 send_telegram_document_async 호출 래퍼
    """
    return asyncio.run(send_telegram_document_async(file_path, caption=caption))

def split_message(text: str, max_length: int = TELEGRAM_MAX_MESSAGE_LENGTH) -> List[str]:
    """
    텔레그램 메시지 분할 함수 (텍스트 메시지용)
    """
    if len(text) <= max_length:
        return [text]

    chunks = []
    current_chunk = ""
    paragraphs = text.split("\n\n")

    for paragraph in paragraphs:
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
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        chunks = split_message(text)
        for idx, chunk in enumerate(chunks, 1):
            try:
                await bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text=chunk,
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
            except TelegramError:
                await bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text=chunk,
                    disable_web_page_preview=True
                )
            if idx < len(chunks):
                await asyncio.sleep(1)
        return True
    except Exception as e:
        logger.error(f"메시지 전송 실패: {e}")
        return False

def send_telegram_report(text: str) -> bool:
    return asyncio.run(send_telegram_report_async(text))
