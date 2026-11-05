import re
import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
import requests
from youtube_transcript_api import YouTubeTranscriptApi
from config import TARGET_CHANNELS

logger = logging.getLogger(__name__)

NAMESPACES = {
    'atom': 'http://www.w3.org/2005/Atom',
    'yt': 'http://www.youtube.com/xml/schemas/2015',
    'media': 'http://search.yahoo.com/mrss/'
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
]

def fetch_rss_videos(channel_info: Dict[str, Any], hours: int = 36) -> List[Dict[str, Any]]:
    """
    공식 YouTube RSS 피드를 조회하여 최근 hours 이내 업로드된 영상 목록을 반환합니다.
    """
    channel_name = channel_info["name"]
    rss_url = channel_info.get("rss_url")
    if not rss_url:
        return []

    videos = []
    response_text = None
    for attempt in range(1, 4):
        try:
            headers = {
                "User-Agent": USER_AGENTS[(attempt - 1) % len(USER_AGENTS)],
                "Accept": "application/atom+xml,application/xml,text/xml;q=0.9,*/*;q=0.8"
            }
            res = requests.get(rss_url, headers=headers, timeout=12)
            if res.status_code == 200:
                response_text = res.text
                break
        except requests.RequestException as e:
            logger.warning(f"[{channel_name}] RSS 피드 요청 실패 ({attempt}/3): {e}")

    if not response_text:
        return videos

    try:
        root = ET.fromstring(response_text)
        now_utc = datetime.now(timezone.utc)
        cutoff_time = now_utc - timedelta(hours=hours)

        entries = root.findall('atom:entry', NAMESPACES)
        for entry in entries:
            title_elem = entry.find('atom:title', NAMESPACES)
            link_elem = entry.find('atom:link', NAMESPACES)
            published_elem = entry.find('atom:published', NAMESPACES)
            media_group = entry.find('media:group', NAMESPACES)

            title = title_elem.text if title_elem is not None else ""
            link = link_elem.attrib.get('href', '') if link_elem is not None else ""
            published_str = published_elem.text if published_elem is not None else ""

            # Extract video_id from link
            video_id = ""
            if "v=" in link:
                video_id = link.split("v=")[1].split("&")[0]

            description = ""
            if media_group is not None:
                media_desc = media_group.find('media:description', NAMESPACES)
                if media_desc is not None and media_desc.text:
                    description = media_desc.text.strip()

            if published_str:
                try:
                    pub_dt = datetime.fromisoformat(published_str.replace('Z', '+00:00'))
                    if pub_dt >= cutoff_time:
                        videos.append({
                            "channel_name": channel_name,
                            "video_id": video_id,
                            "title": title,
                            "link": link,
                            "published_at": pub_dt.strftime("%Y-%m-%d %H:%M:%S UTC"),
                            "description": description[:400]
                        })
                except Exception:
                    videos.append({
                        "channel_name": channel_name,
                        "video_id": video_id,
                        "title": title,
                        "link": link,
                        "published_at": published_str,
                        "description": description[:400]
                    })
    except Exception as e:
        logger.error(f"[{channel_name}] RSS 파싱 에러: {e}")

    return videos

def fetch_chesley_streams(hours: int = 48) -> List[Dict[str, Any]]:
    """
    체슬리TV는 라이브 스트리밍(/streams) 탭에 모닝브리프와 별주부전이 즉시 기록되므로,
    해당 페이지의 ytInitialData 메타데이터를 수집합니다.
    """
    url = "https://www.youtube.com/@chesleytv/streams"
    headers = {
        "User-Agent": USER_AGENTS[0],
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8"
    }
    videos = []
    try:
        res = requests.get(url, headers=headers, timeout=12)
        if res.status_code != 200:
            return videos
        html = res.text
        m = re.search(r'var ytInitialData = ({.*?});</script>', html)
        if not m:
            m = re.search(r'window\["ytInitialData"\] = ({.*?});</script>', html)
        if not m:
            return videos

        data = json.loads(m.group(1))
        lockups = []

        def find_lockups(obj):
            if isinstance(obj, dict):
                if 'lockupViewModel' in obj:
                    lockups.append(obj['lockupViewModel'])
                for v in obj.values():
                    find_lockups(v)
            elif isinstance(obj, list):
                for v in obj:
                    find_lockups(v)

        find_lockups(data)
        seen_ids = set()
        for lk in lockups:
            cid = lk.get('contentId', '')
            if not cid or cid in seen_ids:
                continue
            seen_ids.add(cid)

            meta = lk.get('metadata', {})
            title = meta.get('lockupMetadataViewModel', {}).get('title', {}).get('content', '')
            
            # published text snippet (e.g. 스트리밍 시간: 5시간 전)
            rows = []
            desc_rows = meta.get('lockupMetadataViewModel', {}).get('metadata', {}).get('contentMetadataViewModel', {}).get('metadataRows', [])
            for r in desc_rows:
                for p in r.get('metadataParts', []):
                    rows.append(p.get('text', {}).get('content', ''))
            time_text = " / ".join(rows)

            videos.append({
                "channel_name": "체슬리TV",
                "video_id": cid,
                "title": title,
                "link": f"https://www.youtube.com/watch?v={cid}",
                "published_at": time_text,
                "description": f"체슬리 라이브 스트리밍: {title} ({time_text})"
            })
            if len(videos) >= 10:
                break
    except Exception as e:
        logger.error(f"[체슬리TV] 스트림 수집 실패: {e}")

    return videos

def get_video_transcript(video_id: str, max_chars: int = 25000) -> str:
    """
    youtube_transcript_api를 활용하여 한국어 자막(수동/자동생성)을 추출하고 압축합니다.
    자막이 없거나 오류 발생 시 빈 문자열을 반환합니다.
    """
    if not video_id:
        return ""
    try:
        ytt = YouTubeTranscriptApi()
        res = ytt.fetch(video_id, languages=('ko', 'en'))
        if not res or not res.snippets:
            return ""
        
        full_text = " ".join([s.text for s in res.snippets if s.text and not s.text.startswith("[")])
        # 불필요 중복 공백 정리
        full_text = " ".join(full_text.split())
        if len(full_text) > max_chars:
            full_text = full_text[:max_chars] + " ... (이하 자막 요약용 생략)"
        return full_text
    except Exception as e:
        logger.warning(f"[{video_id}] 자막 추출 불가 ({e}). 메타데이터로 대체합니다.")
        return ""

def collect_daily_materials() -> Dict[str, Any]:
    """
    평일 오전 10:30 데일리 리포트를 위한 3대 핵심 채널(총 5개 파트)의 최근 영상과 자막을 수집합니다.
    1. 매경 월가월부 - 문지웅의 빅머니 (1P)
    2. 삼프로TV - 월스트리트 모닝 & 마켓인사이드 (1P)
    3. 삼프로TV - 클로징벨 라이브 & 여의도 인사이트 (1P)
    4. 체슬리TV - 체슬리 모닝브리프 (2P)
    """
    logger.info("=== 평일 데일리 5-Page 투자 리포트 자료 수집 시작 ===")
    materials = {
        "big_money": None,
        "sampro_morning": None,
        "sampro_market_inside": None,
        "sampro_closing": None,
        "sampro_yeouido": None,
        "chesley_morning": None
    }

    # 1. 매경 월가월부 (문지웅의 빅머니)
    mk_videos = fetch_rss_videos(TARGET_CHANNELS["mk_invest"], hours=36)
    for v in mk_videos:
        title = v["title"]
        if any(kw in title for kw in ["빅머니", "문지웅"]):
            v["transcript"] = get_video_transcript(v["video_id"], max_chars=15000)
            materials["big_money"] = v
            logger.info(f"✔ 문지웅의 빅머니 수집: {title}")
            break

    # 2. 삼프로TV 4대 코너
    sampro_videos = fetch_rss_videos(TARGET_CHANNELS["sampro"], hours=36)
    for v in sampro_videos:
        title = v["title"]
        # 월스트리트 모닝
        if not materials["sampro_morning"] and any(kw in title for kw in ["월스트리트", "모닝 브리핑", "모닝브리핑"]):
            v["transcript"] = get_video_transcript(v["video_id"], max_chars=18000)
            materials["sampro_morning"] = v
            logger.info(f"✔ 삼프로 월스트리트 수집: {title}")
        # 마켓인사이드
        elif not materials["sampro_market_inside"] and any(kw in title for kw in ["마켓인사이드", "마켓 인사이드"]):
            v["transcript"] = get_video_transcript(v["video_id"], max_chars=18000)
            materials["sampro_market_inside"] = v
            logger.info(f"✔ 삼프로 마켓인사이드 수집: {title}")
        # 클로징벨 라이브
        elif not materials["sampro_closing"] and any(kw in title for kw in ["클로징벨", "클로징 벨"]):
            v["transcript"] = get_video_transcript(v["video_id"], max_chars=18000)
            materials["sampro_closing"] = v
            logger.info(f"✔ 삼프로 클로징벨 수집: {title}")
        # 여의도 인사이트
        elif not materials["sampro_yeouido"] and any(kw in title for kw in ["여의도 인사이트", "여의도인사이트"]):
            v["transcript"] = get_video_transcript(v["video_id"], max_chars=18000)
            materials["sampro_yeouido"] = v
            logger.info(f"✔ 삼프로 여의도인사이트 수집: {title}")

    # 3. 체슬리TV 모닝브리프 (2시간 라이브 스트림)
    chesley_streams = fetch_chesley_streams(hours=48)
    for v in chesley_streams:
        title = v["title"]
        if any(kw in title for kw in ["모닝브리프", "운용회의"]):
            v["transcript"] = get_video_transcript(v["video_id"], max_chars=30000)
            materials["chesley_morning"] = v
            logger.info(f"✔ 체슬리 모닝브리프 수집: {title}")
            break

    logger.info("=== 평일 데일리 수집 완료 ===")
    return materials

def collect_weekend_materials() -> Dict[str, Any]:
    """
    주말 일요일 오전 10:00 스페셜 리포트를 위한 체슬리TV '별주부전' 영상을 수집합니다.
    """
    logger.info("=== 주말 별주부전 2-Page 심층 스터디 자료 수집 시작 ===")
    materials = {
        "chesley_weekend": None
    }
    chesley_streams = fetch_chesley_streams(hours=72)
    for v in chesley_streams:
        title = v["title"]
        if "별주부전" in title:
            v["transcript"] = get_video_transcript(v["video_id"], max_chars=35000)
            materials["chesley_weekend"] = v
            logger.info(f"✔ 체슬리 별주부전 수집: {title}")
            break

    return materials

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    data = collect_daily_materials()
    for k, v in data.items():
        if v:
            print(f"[{k}] {v['title']} (자막길이: {len(v.get('transcript', ''))}자)")
        else:
            print(f"[{k}] 영상 미발견")
