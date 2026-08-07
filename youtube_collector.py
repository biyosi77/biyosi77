import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import requests
import logging
from typing import List, Dict, Any
from config import TARGET_CHANNELS

logger = logging.getLogger(__name__)

# XML 네임스페이스 정의
NAMESPACES = {
    'atom': 'http://www.w3.org/2005/Atom',
    'yt': 'http://www.youtube.com/xml/schemas/2015',
    'media': 'http://search.yahoo.com/mrss/'
}

import time

def fetch_channel_videos(channel_info: Dict[str, str], hours: int = 24) -> List[Dict[str, Any]]:
    """
    단일 유튜브 채널의 RSS 피드를 수집하여 지정된 시간(기본 24시간) 이내 업로드된 영상을 반환합니다.
    """
    channel_name = channel_info["name"]
    rss_url = channel_info["rss_url"]
    recent_videos = []

    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0"
    ]

    response_text = None
    for attempt in range(1, 4):
        try:
            headers = {
                "User-Agent": user_agents[(attempt - 1) % len(user_agents)],
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
            }
            response = requests.get(rss_url, headers=headers, timeout=12)
            if response.status_code == 200:
                response_text = response.text
                break
            else:
                logger.warning(f"[{channel_name}] RSS 피드 재시도 {attempt}/3 (상태 코드: {response.status_code})")
                time.sleep(2)
        except requests.RequestException as e:
            logger.warning(f"[{channel_name}] RSS 피드 요청 시도 {attempt}/3 실패: {e}")
            time.sleep(2)

    if not response_text:
        logger.error(f"[{channel_name}] RSS 피드 수집 실패 (3회 재시도 초과)")
        return recent_videos

    try:
        root = ET.fromstring(response_text)
        now_utc = datetime.now(timezone.utc)
        cutoff_time = now_utc - timedelta(hours=hours)

        entries = root.findall('atom:entry', NAMESPACES)
        logger.info(f"[{channel_name}] RSS 피드에서 총 {len(entries)}개 영상 수집됨.")

        for entry in entries:
            title_elem = entry.find('atom:title', NAMESPACES)
            link_elem = entry.find('atom:link', NAMESPACES)
            published_elem = entry.find('atom:published', NAMESPACES)
            media_group = entry.find('media:group', NAMESPACES)

            title = title_elem.text if title_elem is not None else "제목 없음"
            link = link_elem.attrib.get('href', '') if link_elem is not None else ""
            published_str = published_elem.text if published_elem is not None else ""

            # 영상 설명 (description)
            description = ""
            if media_group is not None:
                media_desc = media_group.find('media:description', NAMESPACES)
                if media_desc is not None and media_desc.text:
                    description = media_desc.text.strip()

            # 시간 파싱 및 24시간 이내 필터링
            if published_str:
                try:
                    # ISO 8601 형식 파싱 ('Z' -> '+00:00')
                    pub_dt = datetime.fromisoformat(published_str.replace('Z', '+00:00'))
                    
                    if pub_dt >= cutoff_time:
                        recent_videos.append({
                            "channel_name": channel_name,
                            "title": title,
                            "link": link,
                            "published_at": pub_dt.strftime("%Y-%m-%d %H:%M:%S UTC"),
                            "description": description[:300]  # 요약을 위한 앞 300자 추출
                        })
                except ValueError as e:
                    logger.warning(f"[{channel_name}] 날짜 파싱 실패 ({published_str}): {e}")
                    # 날짜 파싱 실패 시 기본 추가
                    recent_videos.append({
                        "channel_name": channel_name,
                        "title": title,
                        "link": link,
                        "published_at": published_str,
                        "description": description[:300]
                    })

    except requests.RequestException as e:
        logger.error(f"[{channel_name}] RSS 피드 요청 실패: {e}")
    except ET.ParseError as e:
        logger.error(f"[{channel_name}] XML 파싱 실패: {e}")
    except Exception as e:
        logger.error(f"[{channel_name}] 알 수 없는 오류 발생: {e}")

    return recent_videos

def collect_all_recent_videos(hours: int = 24) -> List[Dict[str, Any]]:
    """
    모든 대상 채널의 신규 영상을 수집합니다.
    지정된 hours 이내 영상이 없을 경우 주말/공휴일을 고려하여 48시간, 72시간으로 자동 확장 수집합니다.
    """
    all_videos = []
    current_hours = hours

    for channel in TARGET_CHANNELS:
        videos = fetch_channel_videos(channel, hours=current_hours)
        all_videos.extend(videos)

    # 24시간 내 수집된 영상이 0건이면 48시간, 72시간으로 자동 확장 시도
    if not all_videos and current_hours < 72:
        for fallback_hours in [48, 72]:
            logger.info(f" recent {current_hours}시간 내 영상 없음. 수집 범위를 {fallback_hours}시간으로 확장 시도합니다...")
            all_videos = []
            for channel in TARGET_CHANNELS:
                videos = fetch_channel_videos(channel, hours=fallback_hours)
                all_videos.extend(videos)
            if all_videos:
                logger.info(f"{fallback_hours}시간 확장 수집 성공: 총 {len(all_videos)}개 영상 수집됨.")
                break

    logger.info(f"전체 채널에서 총 {len(all_videos)}개의 신규 영상 수집 완료.")
    return all_videos

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Recent Videos Collection Test:")
    results = collect_all_recent_videos(hours=24)
    for idx, item in enumerate(results, 1):
        print(f"{idx}. [{item['channel_name']}] {item['title']} ({item['link']})")
