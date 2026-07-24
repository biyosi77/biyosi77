import sys
import logging
from typing import List, Dict, Any
from google import genai
from google.genai import types
from config import GEMINI_API_KEY, GEMINI_MODEL_NAME

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


logger = logging.getLogger(__name__)

def generate_daily_investment_report(videos: List[Dict[str, Any]]) -> str:
    """
    수집된 지난 24시간 유튜브 영상 정보 목록을 입력 받아 
    Gemini AI를 활용하여 4대 관점의 데일리 투자 리포트를 생성합니다.
    """
    if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here":
        logger.error("GEMINI_API_KEY가 설정되지 않았습니다. .env 파일을 확인해주세요.")
        return "⚠️ [오류] GEMINI_API_KEY가 설정되지 않아 리포트를 생성할 수 없습니다. .env 파일을 확인해 주세요."

    if not videos:
        logger.info("최근 24시간 내 수집된 신규 영상이 없습니다.")
        return "📊 **[데일리 투자 리포트]**\n\n지난 24시간 동안 삼프로TV, 한경 코리아마켓, 한경 글로벌마켓, 와이스트릿에서 새롭게 업로드된 영상이 없습니다."

    # 유튜브 영상 데이터 포맷팅
    video_content_str = ""
    for idx, video in enumerate(videos, 1):
        video_content_str += f"{idx}. [{video['channel_name']}] {video['title']}\n"
        video_content_str += f"   - 링크: {video['link']}\n"
        if video.get("description"):
            # 줄바꿈 정리
            desc_clean = " ".join(video["description"].split())
            video_content_str += f"   - 요약/설명: {desc_clean[:200]}\n"
        video_content_str += "\n"

    # Gemini 프롬프트 구성
    prompt = f"""
당신은 금융 투자 전문가입니다. 
아래 수집된 4개 주요 투자 채널(삼프로TV, 한경 코리아마켓, 한경 글로벌마켓, 와이스트릿)의 최근 영상 정보를 바탕으로 정갈하고 가독성이 뛰어난 요약 리포트를 작성해 주세요.

---
수집된 최근 영상 목록:
{video_content_str}
---

[작성 지침]
1. 리포트 제목은 반드시 "📊 데일리 투자리포트(요약)"으로 시작하세요.
2. 과도한 마크다운 기호(##, ###, 불필요한 ** 남발)를 절대 사용하지 마세요. 깔끔한 제목 구분과 불릿 기호(•) 및 적절한 이모지만 사용하세요.
3. 리포트는 아래 4가지 포인트별로 핵심 메시지를 키워드 중심으로 깔끔하게 작성하세요:
   - 시장시황
   - 산업동향
   - 주요기업 이슈
   - 거시경제 및 리스크
4. 리포트 말미에는 반드시 "💡 오늘의 핵심 인사이트" 요약을 작성하세요.
5. 전체 리포트 분량은 하단 링크를 포함하여 반드시 **1,500자 이내**가 되도록 작성하세요.

[출력 구조 예시]
📊 데일리 투자리포트(요약)

1. 시장시황
• (핵심 키워드 중심 시장 흐름 요약)

2. 산업동향
• (주목받은 산업 및 섹터 핵심 요약)

3. 주요기업 이슈
• (대표 기업 핵심 이슈 요약)

4. 거시경제 및 리스크
• (금리, 환율, 통화정책 등 거시 리스크 핵심 요약)

💡 오늘의 핵심 인사이트
• (오늘 꼭 기억해야 할 핵심 인사이트 1줄)
"""

    try:
        logger.info(f"Gemini API 호출 시작 (모델: {GEMINI_MODEL_NAME})...")
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        # primary model try
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL_NAME,
                contents=prompt
            )
        except Exception as model_err:
            logger.warning(f"모델 {GEMINI_MODEL_NAME} 호출 실패 ({model_err}). fallback 모델(gemini-flash-latest)로 시도합니다.")
            response = client.models.generate_content(
                model="gemini-flash-latest",
                contents=prompt
            )

        report_text = response.text.strip()
        logger.info("Gemini 리포트 생성 성공.")

        # 핵심 영상 링크만 부록으로 추가 (상위 핵심 영상 2~3개)
        sources_footer = ""
        if videos:
            sources_footer = "\n\n🔗 핵심 영상 링크\n"
            for video in videos[:3]:
                sources_footer += f"• [{video['channel_name']}] {video['title']}\n  {video['link']}\n"

        return report_text + sources_footer

    except Exception as e:
        logger.error(f"Gemini API 호출 중 오류 발생: {e}")
        return f"⚠️ **[오류]** Gemini 리포트 생성 실패: {str(e)}"

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sample_videos = [
        {
            "channel_name": "삼프로TV",
            "title": "[시황] 코스피 반등 성공? 반도체와 이차전지 수급 집중 분석",
            "link": "https://www.youtube.com/watch?v=sample1",
            "description": "오늘 주식시장에서 코스피가 반등세를 나타냈습니다."
        },
        {
            "channel_name": "한경 글로벌마켓",
            "title": "Fed 금리 인하 시그널? 연준 의장 발언 및 뉴욕증시 동향",
            "link": "https://www.youtube.com/watch?v=sample2",
            "description": "뉴욕증시가 연준 의장의 매파적 발언 완화에 환호하며 상승했습니다."
        }
    ]
    print("--- Test Daily Report Generation ---")
    print(generate_daily_investment_report(sample_videos))
