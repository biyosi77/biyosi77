import os
import sys
import logging
from datetime import datetime
from typing import List, Dict, Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    KeepTogether,
    HRFlowable
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)

# 폰트 등록 (Windows 맑은 고딕 & Linux 나눔고딕 완벽 지원)
def register_korean_fonts() -> tuple[str, str]:
    regular_font_candidates = [
        "C:\\Windows\\Fonts\\malgun.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/nanum/NanumGothic.ttf",
        "NanumGothic.ttf"
    ]
    bold_font_candidates = [
        "C:\\Windows\\Fonts\\malgunbd.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "/usr/share/fonts/nanum/NanumGothicBold.ttf",
        "NanumGothicBold.ttf"
    ]

    reg_name = "Helvetica"
    for path in regular_font_candidates:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("KoreanReg", path))
                reg_name = "KoreanReg"
                break
            except Exception as e:
                logger.warning(f"폰트 로드 실패 ({path}): {e}")

    bold_name = reg_name
    for path in bold_font_candidates:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("KoreanBold", path))
                bold_name = "KoreanBold"
                break
            except Exception as e:
                logger.warning(f"볼드 폰트 로드 실패 ({path}): {e}")

    return reg_name, bold_name

KOREAN_REG, KOREAN_BOLD = register_korean_fonts()

# 색상 팔레트 (기관 투자 리서치 리포트 스타일)
PRIMARY_NAVY = colors.HexColor("#1A365D")
SECONDARY_BLUE = colors.HexColor("#2B6CB0")
ACCENT_BLUE = colors.HexColor("#3182CE")
LIGHT_BG = colors.HexColor("#F7FAFC")
BORDER_COLOR = colors.HexColor("#E2E8F0")
TEXT_DARK = colors.HexColor("#2D3748")
TEXT_MUTED = colors.HexColor("#718096")
HIGHLIGHT_RED = colors.HexColor("#C53030")

class NumberedCanvas:
    """
    각 페이지 상단 헤더와 하단 푸터(페이지 번호 'Page X of Y')를 동적으로 렌더링하는 커스텀 캔버스
    """
    def __init__(self, *args, **kwargs):
        pass

def create_report_styles():
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName=KOREAN_BOLD,
        fontSize=15,
        leading=19,
        textColor=PRIMARY_NAVY,
        spaceAfter=3
    )

    page_header_style = ParagraphStyle(
        'PageHeaderBadge',
        parent=styles['Normal'],
        fontName=KOREAN_BOLD,
        fontSize=10,
        leading=13,
        textColor=colors.white
    )

    section_header_style = ParagraphStyle(
        'SectionHeader',
        parent=styles['Normal'],
        fontName=KOREAN_BOLD,
        fontSize=11,
        leading=15,
        textColor=PRIMARY_NAVY,
        spaceBefore=5,
        spaceAfter=4
    )

    body_style = ParagraphStyle(
        'BodyDark',
        parent=styles['Normal'],
        fontName=KOREAN_REG,
        fontSize=8.5,
        leading=12.5,
        textColor=TEXT_DARK,
        spaceAfter=3
    )

    bullet_style = ParagraphStyle(
        'BulletPoint',
        parent=styles['Normal'],
        fontName=KOREAN_REG,
        fontSize=8.2,
        leading=11.8,
        textColor=TEXT_DARK,
        leftIndent=8,
        firstLineIndent=-8,
        spaceAfter=2
    )

    footer_style = ParagraphStyle(
        'FooterText',
        parent=styles['Normal'],
        fontName=KOREAN_REG,
        fontSize=7,
        leading=9,
        textColor=TEXT_MUTED
    )

    return {
        "title": title_style,
        "badge": page_header_style,
        "section": section_header_style,
        "body": body_style,
        "bullet": bullet_style,
        "footer": footer_style
    }

def build_page_header(page_title: str, subtitle: str, page_num: int, total_pages: int, styles: Dict) -> List:
    """
    각 페이지 상단에 들어가는 정갈한 기관 리포트 헤더 바 테이블을 생성합니다.
    """
    header_data = [
        [
            Paragraph(f"<b>{page_title}</b>", styles["badge"]),
            Paragraph(f"<font size=8>{subtitle} | Page {page_num} of {total_pages}</font>", styles["badge"])
        ]
    ]
    header_table = Table(header_data, colWidths=[120*mm, 70*mm])
    header_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), PRIMARY_NAVY),
        ('PADDING', (0, 0), (-1, -1), 4),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    return [header_table, Spacer(1, 3*mm)]

def build_card_box(title: str, content_paragraphs: List[Paragraph], styles: Dict) -> Table:
    """
    내용을 깔끔한 테두리와 옅은 배경색의 카드 박스로 감싸는 컴포넌트
    """
    card_elements = []
    if title:
        card_elements.append(Paragraph(f"<b>■ {title}</b>", styles["section"]))
        card_elements.append(HRFlowable(width="100%", thickness=0.8, color=BORDER_COLOR, spaceBefore=1, spaceAfter=2))
    
    card_elements.extend(content_paragraphs)

    card_data = [[card_elements]]
    card_table = Table(card_data, colWidths=[190*mm])
    card_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), LIGHT_BG),
        ('BOX', (0, 0), (-1, -1), 0.6, BORDER_COLOR),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    return card_table

def build_pdf_document(output_path: str, pages_data: List[Dict[str, Any]], main_title: str) -> str:
    """
    구조화된 페이지 데이터(List of Dict)를 기반으로 정확한 페이지 수(5P or 2P)의 PDF 문서를 빌드합니다.
    각 page dict: {
        "header_title": str,
        "subtitle": str,
        "sections": [
            {
                "title": str,
                "bullets": List[str]
            }
        ],
        "footer_link": Optional[str]
    }
    """
    styles = create_report_styles()
    total_pages = len(pages_data)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=10*mm,
        rightMargin=10*mm,
        topMargin=10*mm,
        bottomMargin=10*mm
    )

    story = []

    for idx, pdata in enumerate(pages_data, 1):
        # 1. 헤더 바
        header_elems = build_page_header(
            pdata.get("header_title", main_title),
            pdata.get("subtitle", f"AI Investment Report"),
            idx,
            total_pages,
            styles
        )
        story.extend(header_elems)

        # 2. 섹션 박스들
        sections = pdata.get("sections", [])
        for sec in sections:
            sec_title = sec.get("title", "")
            bullets = sec.get("bullets", [])
            bullet_paras = []
            for b in bullets:
                # bold formatting check
                bullet_paras.append(Paragraph(f"• {b}", styles["bullet"]))
            
            card = build_card_box(sec_title, bullet_paras, styles)
            story.append(card)
            story.append(Spacer(1, 2.5*mm))

        # 3. 페이지 하단 링크 및 안내
        footer_link = pdata.get("footer_link", "")
        if footer_link:
            story.append(Spacer(1, 1*mm))
            story.append(Paragraph(f"🔗 원문 방송 링크: <font color='#2B6CB0'>{footer_link}</font>", styles["footer"]))

        # 다음 페이지로 강제 넘김 (마지막 페이지 제외)
        if idx < total_pages:
            story.append(PageBreak())

    doc.build(story)
    logger.info(f"PDF 파일 생성 완료 (총 {total_pages} 페이지): {output_path}")
    return output_path

if __name__ == "__main__":
    sample_pages = [
        {
            "header_title": "매경 월가월부 | 문지웅의 빅머니",
            "subtitle": "2026.11.05 뉴욕증시 마감 브리핑",
            "sections": [
                {
                    "title": "뉴욕 3대 지수 & 핵심 매크로 지표 변동",
                    "bullets": [
                        "<b>지수 흐름</b>: 다우 +0.2%, S&P500 -0.1%, 나스닥 -0.4% 혼조세 마감.",
                        "<b>국채 금리 & 환율</b>: 미 국채 10년물 4.38%로 상승하며 고금리 장기화 우려 자극.",
                        "<b>월가 자금 동향</b>: 대형 빅테크에서 가치주 및 방어주로 단기 로테이션 감지."
                    ]
                },
                {
                    "title": "구체적 종목 특징 및 월가 큰손 시각",
                    "bullets": [
                        "<b>엔비디아(-1.8%)</b>: 차세대 칩 양산 지연 우려 일부 해소되었으나 단기 차익 실현 출회.",
                        "<b>테슬라(+3.5%)</b>: 자율주행 및 에너지 저장장치(ESS) 수주 확대 기대감으로 반등 주도."
                    ]
                }
            ],
            "footer_link": "https://youtu.be/sample1"
        },
        {
            "header_title": "삼프로TV | 월스트리트 모닝 & 마켓인사이드",
            "subtitle": "2026.11.05 글로벌 매크로 분석",
            "sections": [
                {
                    "title": "글로벌 공급망 및 원자재 시장 구조 점검",
                    "bullets": [
                        "<b>원유 & 원자재</b>: WTI 배럴당 72달러선 횡보, 중동 지정학 리스크 완화 반영.",
                        "<b>주요 IB 투자의견</b>: 골드만삭스, 신흥국 주식 비중 확대 권고 유지."
                    ]
                }
            ],
            "footer_link": "https://youtu.be/sample2"
        }
    ]
    out = build_pdf_document("test_sample_output.pdf", sample_pages, "DAILY MASTER REPORT")
    print("Test build complete:", out)
