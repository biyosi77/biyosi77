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

def _select_representative_videos(videos: List[Dict[str, Any]], max_count: int = 4) -> List[Dict[str, Any]]:
    """
    하단 핵심 영상 링크에 특정 채널만 편중되지 않도록 매경 월가월부(빅머니) 영상을 우선 포함하고,
    채널별로 고르게 대표 영상을 선택합니다.
    """
    selected = []
    seen_links = set()

    # 1. 매경 월가월부(문지웅의 빅머니) 영상 우선 포함
    for v in videos:
        if v.get("channel_name") == "매경 월가월부" and v.get("link") not in seen_links:
            selected.append(v)
            seen_links.add(v.get("link"))

    # 2. 각 채널별 대표 영상 1개씩 순차 추가
    seen_channels = {v.get("channel_name") for v in selected}
    for v in videos:
        if len(selected) >= max_count:
            break
        ch = v.get("channel_name")
        link = v.get("link")
        if ch not in seen_channels and link not in seen_links:
            selected.append(v)
            seen_channels.add(ch)
            seen_links.add(link)

    # 3. 자리가 남으면 나머지 영상 중 순서대로 채움
    for v in videos:
        if len(selected) >= max_count:
            break
        link = v.get("link")
        if link not in seen_links:
            selected.append(v)
            seen_links.add(link)

    return selected

def generate_daily_investment_report(videos: List[Dict[str, Any]]) -> str:
    """
    수집된 지난 24시간 유튜브 영상 정보 목록을 입력 받아 
    Gemini AI를 활용하여 데일리 투자 리포트를 생성합니다.
    """
    if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here":
        logger.error("GEMINI_API_KEY가 설정되지 않았습니다. .env 파일을 확인해주세요.")
        return "⚠️ [오류] GEMINI_API_KEY가 설정되지 않아 리포트를 생성할 수 없습니다. .env 파일을 확인해 주세요."

    if not videos:
        logger.info("최근 24시간 내 수집된 신규 영상이 없습니다.")
        return "📊 <b>[데일리 투자 리포트]</b>\n\n지난 24시간 동안 삼프로TV, 한경 코리아마켓, 한경 글로벌마켓, 와이스트릿, 매경 월가월부(빅머니)에서 새롭게 업로드된 영상이 없습니다."

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
아래 수집된 5개 주요 투자 채널(삼프로TV, 한경 코리아마켓, 한경 글로벌마켓, 와이스트릿, 매경 월가월부 '문지웅의 빅머니')의 최근 영상 정보를 바탕으로 정갈하고 가독성이 뛰어난 요약 리포트를 작성해 주세요.

---
수집된 최근 영상 목록:
{video_content_str}
---

[작성 지침]
1. 리포트 제목은 반드시 "📊 데일리 투자리포트(요약)"으로 시작하세요.
2. 마크다운 기호(#, ##, **)나 특수 기호를 사용하지 말고, 제목은 <b>제목</b> 형태의 HTML 태그나 불릿 기호(•) 및 적절한 이모지만 사용하세요.
3. 리포트는 아래 포인트별로 핵심 메시지를 키워드 중심으로 깔끔하게 작성하세요:
   - 시장시황
   - 산업동향
   - 주요기업 이슈
   - 거시경제 및 리스크
   - 매경 월가월부 (문지웅의 빅머니) 핵심 요약 (수집 목록에 매경 월가월부/빅머니 영상이 있을 경우 핵심 내용을 별도 항목으로 요약하고, 없으면 생략)
4. 리포트 말미에는 반드시 "💡 오늘의 핵심 인사이트" 요약을 작성하세요.
5. 전체 리포트 분량은 하단 링크를 포함하여 반드시 1,800자 이내가 되도록 작성하세요.

[출력 구조 예시]
📊 <b>데일리 투자리포트(요약)</b>

<b>1. 시장시황</b>
• (핵심 키워드 중심 시장 흐름 요약)

<b>2. 산업동향</b>
• (주목받은 산업 및 섹터 핵심 요약)

<b>3. 주요기업 이슈</b>
• (대표 기업 핵심 이슈 요약)

<b>4. 거시경제 및 리스크</b>
• (금리, 환율, 통화정책 등 거시 리스크 핵심 요약)

<b>5. 문지웅의 빅머니 브리핑</b> (해당 영상 존재 시)
• (월가월부 빅머니 클립 핵심 이슈 및 월가 시각 요약)

💡 <b>오늘의 핵심 인사이트</b>
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

        # 핵심 영상 링크만 부록으로 추가 (매경 월가월부 빅머니 포함 상위 핵심 영상 최대 4개)
        sources_footer = ""
        if videos:
            rep_videos = _select_representative_videos(videos, max_count=4)
            sources_footer = "\n\n🔗 <b>핵심 영상 링크</b>\n"
            for video in rep_videos:
                sources_footer += f"• [{video['channel_name']}] {video['title']}\n  {video['link']}\n"

        return report_text + sources_footer

    except Exception as e:
        logger.error(f"Gemini API 호출 중 오류 발생: {e}")
        return f"⚠️ <b>[오류]</b> Gemini 리포트 생성 실패: {str(e)}"

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
            "channel_name": "매경 월가월부",
            "title": "[문지웅의 빅머니] 월가 큰손들이 주목한 AI 전력주와 연준 금리 시나리오",
            "link": "https://www.youtube.com/watch?v=sample2",
            "description": "뉴욕증시 마감 브리핑과 빅머니 흐름을 짚어봅니다."
        }
    ]
    print("--- Test Daily Report Generation ---")
    print(generate_daily_investment_report(sample_videos))
