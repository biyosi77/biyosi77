import os
import sys
import time
import argparse
import logging
from datetime import datetime
import pytz
import schedule

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from youtube_collector import collect_daily_materials, collect_weekend_materials
from analyzer import generate_daily_5page_report, generate_weekend_2page_report
from pdf_generator import build_pdf_document
from telegram_sender import send_telegram_document

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("InvestmentMasterBot")

def get_kst_now() -> datetime:
    return datetime.now(pytz.timezone('Asia/Seoul'))

def run_daily_job(max_retries: int = 2) -> bool:
    """
    평일 오전 10:30 데일리 마스터 투자 리포트 (총 5-Page PDF) 생성 및 텔레그램 발송
    """
    kst_now = get_kst_now()
    date_str = kst_now.strftime("%Y.%m.%d")
    logger.info(f"=== [평일 데일리 5-Page 투자 리포트] 시작 (KST: {kst_now.strftime('%Y-%m-%d %H:%M:%S')}) ===")

    for attempt in range(1, max_retries + 1):
        try:
            # 1. 3대 채널 5대 코너 영상 및 자막 수집
            logger.info(f"1단계: 유튜브 3대 채널 핵심 코너 수집 (시도 {attempt}/{max_retries})")
            materials = collect_daily_materials()

            # 2. Gemini 4단계 심층 분석 (5-Page 데이터 구성)
            logger.info("2단계: Gemini AI 4단계 심층 분석 및 5페이지 구조화 데이터 생성 중...")
            pages_data = generate_daily_5page_report(materials, date_str)

            # 3. 고품질 A4 정밀 5-Page PDF 빌드
            os.makedirs("reports", exist_ok=True)
            pdf_filename = f"reports/Daily_Master_Investment_Report_{kst_now.strftime('%Y%m%d')}.pdf"
            logger.info(f"3단계: 5-Page PDF 리포트 빌드 중 ({pdf_filename})...")
            build_pdf_document(pdf_filename, pages_data, "DAILY MASTER INVESTMENT REPORT")

            # 4. 텔레그램 채널로 문서 발송
            caption = (
                f"📊 <b>[데일리 마스터 투자 리포트] {date_str}</b>\n\n"
                f"• Page 1: 매경 월가월부 문지웅의 빅머니 뉴욕 브리핑\n"
                f"• Page 2: 삼프로TV 월스트리트 모닝 & 마켓인사이드\n"
                f"• Page 3: 삼프로TV 클로징벨 라이브 & 여의도 인사이트\n"
                f"• Page 4: 체슬리TV 박세익 전무의 매크로 나침반 & 운용회의\n"
                f"• Page 5: 체슬리TV 섹터별 딥다이브 & 실전 교체 매매(Swap)\n\n"
                f"💡 <i>총 5페이지의 고밀도 투자 리서치 PDF가 첨부되었습니다.</i>"
            )
            logger.info("4단계: 텔레그램 채널로 PDF 리포트 발송 중...")
            success = send_telegram_document(pdf_filename, caption=caption)
            if success:
                logger.info(f"=== 데일리 5-Page 리포트 발송 성공 ({pdf_filename}) ===")
                return True
            else:
                logger.warning(f"텔레그램 발송 실패 (시도 {attempt}/{max_retries})")
                if attempt < max_retries:
                    time.sleep(10)
        except Exception as e:
            logger.error(f"데일리 프로세스 실행 중 예외 발생: {e}", exc_info=True)
            if attempt < max_retries:
                time.sleep(10)

    logger.error("❌ 데일리 리포트 프로세스 최종 실패.")
    return False

def run_weekend_job(max_retries: int = 2) -> bool:
    """
    매주 일요일 오전 10:00 주말특집 별주부전 심층 스터디 (총 2-Page PDF) 생성 및 발송
    """
    kst_now = get_kst_now()
    date_str = kst_now.strftime("%Y.%m.%d")
    logger.info(f"=== [주말특집 체슬리TV 별주부전 2-Page 심층 스터디] 시작 (KST: {kst_now.strftime('%Y-%m-%d %H:%M:%S')}) ===")

    for attempt in range(1, max_retries + 1):
        try:
            # 1. 별주부전 영상 및 자막 수집
            logger.info(f"1단계: 체슬리TV 별주부전 풀영상 수집 (시도 {attempt}/{max_retries})")
            materials = collect_weekend_materials()

            # 2. Gemini 심층 분석 (2-Page 데이터 구성)
            logger.info("2단계: 별주부전 메가트렌드 & 밸류에이션 2페이지 데이터 생성 중...")
            pages_data = generate_weekend_2page_report(materials, date_str)

            # 3. PDF 빌드
            os.makedirs("reports", exist_ok=True)
            pdf_filename = f"reports/Weekend_Chesley_Study_{kst_now.strftime('%Y%m%d')}.pdf"
            logger.info(f"3단계: 2-Page PDF 리포트 빌드 중 ({pdf_filename})...")
            build_pdf_document(pdf_filename, pages_data, "WEEKEND SPECIAL: CHESLEY DEEP STUDY")

            # 4. 텔레그램 발송
            caption = (
                f"📚 <b>[주말특집 체슬리TV 별주부전 심층 스터디] {date_str}</b>\n\n"
                f"• Page 1: 메가트렌드 특강 & 글로벌 산업 밸류체인 해부\n"
                f"• Page 2: 집중 분석 기업 Top-picks & 3~5년 중장기 로드맵\n\n"
                f"💡 <i>토요일 3.5시간 풀영상 완벽 압축 2-Page PDF가 첨부되었습니다.</i>"
            )
            logger.info("4단계: 텔레그램 채널로 PDF 리포트 발송 중...")
            success = send_telegram_document(pdf_filename, caption=caption)
            if success:
                logger.info(f"=== 주말 별주부전 2-Page 리포트 발송 성공 ({pdf_filename}) ===")
                return True
            else:
                logger.warning(f"텔레그램 발송 실패 (시도 {attempt}/{max_retries})")
                if attempt < max_retries:
                    time.sleep(10)
        except Exception as e:
            logger.error(f"주말 프로세스 실행 중 예외 발생: {e}", exc_info=True)
            if attempt < max_retries:
                time.sleep(10)

    logger.error("❌ 주말 스페셜 리포트 프로세스 최종 실패.")
    return False

def main():
    parser = argparse.ArgumentParser(description="유튜브 핵심 투자 채널 분석 & 텔레그램 PDF 리포트 자동화 시스템")
    parser.add_argument("--daily", action="store_true", help="평일 데일리 5-Page 투자 리포트 즉시 생성 및 발송")
    parser.add_argument("--weekend", action="store_true", help="주말 별주부전 2-Page 심층 스터디 리포트 즉시 생성 및 발송")
    parser.add_argument("--now", action="store_true", help="--daily의 레거시 호환 별칭")
    args = parser.parse_args()

    if args.daily or args.now:
        success = run_daily_job()
        if not success:
            sys.exit(1)
        return

    if args.weekend:
        success = run_weekend_job()
        if not success:
            sys.exit(1)
        return

    # 로컬 스케줄러 모드 (항시 실행 시)
    logger.info("⏰ 로컬 스케줄러 모드 시작:")
    logger.info(" - 평일(월~금) 매일 10:30 KST : 데일리 5-Page 리포트 발송")
    logger.info(" - 주말(일요일) 매주 10:00 KST : 별주부전 2-Page 리포트 발송")

    schedule.every().monday.at("10:30").do(run_daily_job)
    schedule.every().tuesday.at("10:30").do(run_daily_job)
    schedule.every().wednesday.at("10:30").do(run_daily_job)
    schedule.every().thursday.at("10:30").do(run_daily_job)
    schedule.every().friday.at("10:30").do(run_daily_job)
    schedule.every().sunday.at("10:00").do(run_weekend_job)

    while True:
        try:
            schedule.run_pending()
            time.sleep(30)
        except KeyboardInterrupt:
            logger.info("스케줄러가 종료되었습니다.")
            break
        except Exception as e:
            logger.error(f"스케줄러 루프 예외: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
