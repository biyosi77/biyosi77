import json
import logging
from typing import Dict, Any, List
from google import genai
from google.genai import types
from config import GEMINI_API_KEY, GEMINI_MODEL_NAME

logger = logging.getLogger(__name__)

def _call_gemini_json(prompt: str) -> Any:
    """
    Gemini API를 호출하여 구조화된 JSON 결과를 반환받습니다.
    1차: GEMINI_MODEL_NAME, 실패 시 fallback: gemini-flash-latest
    """
    if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here":
        raise ValueError("GEMINI_API_KEY가 유효하지 않습니다.")

    client = genai.Client(api_key=GEMINI_API_KEY)
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.2
    )

    try:
        res = client.models.generate_content(
            model=GEMINI_MODEL_NAME,
            contents=prompt,
            config=config
        )
        return json.loads(res.text)
    except Exception as e:
        logger.warning(f"모델 {GEMINI_MODEL_NAME} 호출 실패 ({e}). fallback 모델(gemini-flash-latest)로 재시도합니다.")
        res = client.models.generate_content(
            model="gemini-flash-latest",
            contents=prompt,
            config=config
        )
        return json.loads(res.text)

def generate_daily_5page_report(materials: Dict[str, Any], date_str: str) -> List[Dict[str, Any]]:
    """
    수집된 3대 채널 5개 파트 자료를 [현상 ➔ 원인·배경 ➔ 구체적 종목/섹터 특징 ➔ 향후 영향·전망] 프레임워크로 분석하여
    정확히 5페이지 PDF를 위한 구조화된 데이터를 생성합니다.
    """
    # 텍스트 컨텍스트 구성
    context = ""
    for k, v in materials.items():
        if v:
            context += f"\n=== [프로그램: {k} | 제목: {v['title']}] ===\n"
            context += f"링크: {v['link']}\n"
            if v.get("transcript"):
                context += f"자막 발췌: {v['transcript'][:15000]}\n"
            else:
                context += f"설명 요약: {v.get('description', '')}\n"

    prompt = f"""
당신은 대한민국 최고 수준의 기관 투자 리서치 센터장입니다.
아래 제공된 수집 자료(매경 월가월부 문지웅의 빅머니, 삼프로TV 4대 코너, 체슬리TV 모닝브리프)를 바탕으로
총 5페이지 분량의 [데일리 마스터 투자 리포트]를 작성해야 합니다.

[분석 핵심 원칙]
단순한 헤드라인 요약이나 피상적인 나열을 절대 금지합니다.
각 섹션마다 다음 4단계 구조화 분석을 매우 구체적으로 작성하세요:
1. [현상 및 지표 움직임 (What)]: 구체적 수치(지수, 금리, 환율, 등락률 등)와 시장 수급 동향
2. [구조적 원인 및 배경 (Why)]: 발표된 거시 지표, 연준 발언, 기업 가이던스, 지정학적 배경 등
3. [구체적 종목 및 섹터 특징 (Stocks)]: 언급된 대표 기업명(티커), 등락 이유, 밸류에이션 변화 팩트체크
4. [향후 영향·전망 및 실전 운용 전략 (Outlook & Strategy)]: 전문가들이 제시한 지수 하단, 교체 매매 기준, 포트폴리오 비중 전략

반드시 아래 JSON 스키마를 만족하는 리스트 형태로 반환하세요:
[
  {{
    "header_title": "매경 월가월부 | 문지웅의 빅머니",
    "subtitle": "{date_str} 뉴욕 현지 시각 & 월가 스마트머니 동향",
    "sections": [
      {{
        "title": "뉴욕 3대 지수 & 핵심 매크로 지표 변동 현상",
        "bullets": ["<b>지수 & 금리 흐름</b>: ...", "<b>환율 & 원자재</b>: ...", "<b>수급 쏠림</b>: ..."]
      }},
      {{
        "title": "현지 특파원 시각: 구조적 원인 & 월가 큰손 자금 흐름",
        "bullets": ["<b>연준 통화정책 기대감</b>: ...", "<b>인플레이션 & 경기 지표</b>: ...", "<b>기관 자금 이동</b>: ..."]
      }},
      {{
        "title": "M7 및 주요 개별 종목 구체적 특징점",
        "bullets": ["<b>대표 종목 A</b>: ...", "<b>대표 종목 B</b>: ...", "<b>실적 가이던스 요약</b>: ..."]
      }},
      {{
        "title": "뉴욕 증시 향후 전망 및 주요 관전 포인트",
        "bullets": ["<b>단기 리스크 요인</b>: ...", "<b>실전 대응 전략</b>: ..."]
      }}
    ],
    "footer_link": "{materials.get('big_money', {}).get('link', '') if materials.get('big_money') else ''}"
  }},
  {{
    "header_title": "삼프로TV | 월스트리트 모닝 & 마켓인사이드",
    "subtitle": "{date_str} 글로벌 매크로 & 산업 구조 분석",
    "sections": [
      {{
        "title": "[월스트리트 모닝] 글로벌 채권·외환 시장 및 IB 자산 배분",
        "bullets": ["<b>글로벌 금리 환경</b>: ...", "<b>주요 IB 하우스 뷰</b>: ..."]
      }},
      {{
        "title": "[마켓인사이드] 글로벌 공급망 재편 및 산업 구조 변화",
        "bullets": ["<b>핵심 산업 사이클</b>: ...", "<b>원자재 & 통상 환경</b>: ..."]
      }},
      {{
        "title": "[마켓인사이드] 주요국 정책 변화와 국내 수출 기업 영향",
        "bullets": ["<b>국내 파급 영향</b>: ...", "<b>전략적 대응 방안</b>: ..."]
      }}
    ],
    "footer_link": "{materials.get('sampro_morning', {}).get('link', '') if materials.get('sampro_morning') else ''}"
  }},
  {{
    "header_title": "삼프로TV | 클로징벨 라이브 & 여의도 인사이트",
    "subtitle": "{date_str} 국내 증시 마감 복기 & 기관 전문가 전략",
    "sections": [
      {{
        "title": "[클로징벨] 전일 국내 증시 마감 & 외국인·기관 수급 복기",
        "bullets": ["<b>코스피/코스닥 마감</b>: ...", "<b>수급 주체별 매매 동향</b>: ..."]
      }},
      {{
        "title": "[클로징벨] 당일 주도 섹터 vs 소외 섹터 종목별 등락 요인",
        "bullets": ["<b>주도 섹터(상승)</b>: ...", "<b>조정 섹터(하락)</b>: ..."]
      }},
      {{
        "title": "[여의도 인사이트] 여의도 기관 운용역 심층 인터뷰 & 밸류에이션",
        "bullets": ["<b>핵심 논점 및 논리</b>: ...", "<b>실적 턴어라운드 종목 선별 기준</b>: ..."]
      }},
      {{
        "title": "[여의도 인사이트] 실전 포트폴리오 리밸런싱 전략 제언",
        "bullets": ["<b>지수 하단 지지력</b>: ...", "<b>현금 비중 및 분할 매수 팁</b>: ..."]
      }}
    ],
    "footer_link": "{materials.get('sampro_closing', {}).get('link', '') if materials.get('sampro_closing') else ''}"
  }},
  {{
    "header_title": "체슬리TV | 체슬리 모닝브리프 (Part 1)",
    "subtitle": "{date_str} 박세익 전무의 매크로 나침반 & 펀드 운용 철학",
    "sections": [
      {{
        "title": "박세익 전무의 매크로 나침반: 시장 위치 & 심리 지표 점검",
        "bullets": ["<b>시장 국면 진단</b>: ...", "<b>역사적 밸류에이션 밴드</b>: ...", "<b>공포·탐욕 지표</b>: ..."]
      }},
      {{
        "title": "팀 체슬리 펀드 운용 원칙 및 현금 비중 가이드",
        "bullets": ["<b>현금 비중 원칙</b>: ...", "<b>자산 배분 프레임워크</b>: ..."]
      }},
      {{
        "title": "펀드매니저 실시간 운용회의 3대 핵심 토론 & 팩트체크",
        "bullets": ["<b>핵심 화두 1</b>: ...", "<b>핵심 화두 2</b>: ...", "<b>시장 오해와 진실</b>: ..."]
      }}
    ],
    "footer_link": "{materials.get('chesley_morning', {}).get('link', '') if materials.get('chesley_morning') else ''}"
  }},
  {{
    "header_title": "체슬리TV | 체슬리 모닝브리프 (Part 2)",
    "subtitle": "{date_str} 섹터별 딥다이브 & 실전 교체 매매(Swap) 전략",
    "sections": [
      {{
        "title": "핵심 섹터별 펀더멘털 점검 (반도체/AI/전력/2차전지/바이오/금융)",
        "bullets": ["<b>주도 섹터 코멘트</b>: ...", "<b>바닥 통과 섹터 코멘트</b>: ..."]
      }},
      {{
        "title": "구체적 종목별 특징점 및 체슬리 관심 종목군",
        "bullets": ["<b>종목 1</b>: ...", "<b>종목 2</b>: ...", "<b>종목 3</b>: ..."]
      }},
      {{
        "title": "펀드매니저 실전 운용 조언: 교체 매매(Swap) & 분할 매수 전략",
        "bullets": ["<b>약세장 대응 원칙</b>: ...", "<b>핵심 코어 종목 비중 조절</b>: ..."]
      }},
      {{
        "title": "💡 오늘의 핵심 투자 격언 (Takeaway)",
        "bullets": ["<b>원라인 메시지</b>: ..."]
      }}
    ],
    "footer_link": "{materials.get('chesley_morning', {}).get('link', '') if materials.get('chesley_morning') else ''}"
  }}
]

각 페이지의 bullets는 bullet 당 1~2문장으로 매우 밀도 있고 명확하게 작성하세요.
HTML 태그는 <b>키워드</b>만 사용하세요.

자료:
{context}
"""
    logger.info("Gemini를 통한 5-Page 데일리 리포트 데이터 생성 호출 중...")
    pages = _call_gemini_json(prompt)
    if not isinstance(pages, list) or len(pages) != 5:
        logger.warning(f"Gemini 반환 페이지 수 불일치 ({len(pages)}개). 5개 페이지로 보정합니다.")
        while len(pages) < 5:
            pages.append({
                "header_title": "데일리 투자 인사이트",
                "subtitle": date_str,
                "sections": [{"title": "보조 브리핑", "bullets": ["<b>자료 준비 중</b>: 상세 분석 데이터 정리."]}]
            })
        pages = pages[:5]
    return pages

def generate_weekend_2page_report(materials: Dict[str, Any], date_str: str) -> List[Dict[str, Any]]:
    """
    주말 체슬리TV '별주부전' 풀영상을 바탕으로 2페이지 심층 분석 데이터를 생성합니다.
    """
    v = materials.get("chesley_weekend")
    context = ""
    if v:
        context += f"제목: {v['title']}\n링크: {v['link']}\n"
        context += f"자막 발췌: {v.get('transcript', '')[:25000]}\n"

    prompt = f"""
당신은 대한민국 최고 수준의 기관 투자 리서치 센터장입니다.
아래 제공된 체슬리TV 주말 특집 [별주부전] 풀영상 자료를 바탕으로
총 2페이지 분량의 [별주부전 주말 심층 스터디 리포트]를 작성해야 합니다.

[작성 지침]
Page 1: 메가트렌드 산업 구조 분석 및 글로벌 밸류체인 해부
Page 2: 집중 분석 종목(Top-picks) 펀더멘털 및 3~5년 중장기 투자 로드맵

반드시 2개 항목으로 구성된 JSON 리스트로 반환하세요:
[
  {{
    "header_title": "체슬리TV | 주말특집 별주부전 (Part 1)",
    "subtitle": "{date_str} 메가트렌드 특강 & 글로벌 산업 밸류체인 해부",
    "sections": [
      {{
        "title": "금주의 메가트렌드 테마: 산업 패러다임 변화와 배경",
        "bullets": ["<b>테마 선정 배경</b>: ...", "<b>시장 규모(TAM) & 성장률</b>: ..."]
      }},
      {{
        "title": "글로벌 산업 밸류체인 해부 & 독점적 해자(Moat)",
        "bullets": ["<b>원천 기술 및 진입장벽</b>: ...", "<b>글로벌 1위 기업의 경쟁력</b>: ..."]
      }},
      {{
        "title": "매크로 변수(금리·환율·정책)와 산업 사이클의 상관관계",
        "bullets": ["<b>거시 경제 파급 효과</b>: ...", "<b>정책적 수혜 요인</b>: ..."]
      }}
    ],
    "footer_link": "{v.get('link', '') if v else ''}"
  }},
  {{
    "header_title": "체슬리TV | 주말특집 별주부전 (Part 2)",
    "subtitle": "{date_str} 집중 분석 기업 펀더멘털 & 중장기 실전 로드맵",
    "sections": [
      {{
        "title": "집중 분석 기업(Top-picks) 펀더멘털 & 질적 실적 분석",
        "bullets": ["<b>핵심 기업 A 비즈니스 모델</b>: ...", "<b>핵심 기업 B 성장 모멘텀</b>: ..."]
      }},
      {{
        "title": "밸류에이션 매력도 & 다운사이드 리스크 점검",
        "bullets": ["<b>Peer 대비 할인율</b>: ...", "<b>리스크 요인 & 모니터링 체크리스트</b>: ..."]
      }},
      {{
        "title": "박세익 전무의 별주부전 3~5년 중장기 투자 로드맵",
        "bullets": ["<b>분할 매수 밴드</b>: ...", "<b>목표 수익률 및 분할 매도 원칙</b>: ...", "<b>핵심 지표(KPI)</b>: ..."]
      }},
      {{
        "title": "💡 주말 스터디 결론 (Closing Message)",
        "bullets": ["<b>핵심 인사이트</b>: ..."]
      }}
    ],
    "footer_link": "{v.get('link', '') if v else ''}"
  }}
]

자료:
{context}
"""
    logger.info("Gemini를 통한 2-Page 주말 별주부전 리포트 데이터 생성 호출 중...")
    pages = _call_gemini_json(prompt)
    if not isinstance(pages, list) or len(pages) != 2:
        pages = pages[:2] if len(pages) >= 2 else pages + [pages[0]]
    return pages
