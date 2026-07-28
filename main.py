import sys
import time
import argparse
import logging
import schedule
from datetime import datetime

# Windows 콘솔 이모지/UTF-8 인코딩 방어 설정
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


from youtube_collector import collect_all_recent_videos
from analyzer import generate_daily_investment_report
from telegram_sender import send_telegram_report

import pytz

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("DailyReportBot")

def get_kst_now() -> datetime:
    return datetime.now(pytz.timezone('Asia/Seoul'))

def run_daily_investment_report_job(hours: int = 24):
    """
    데일리 투자 리포트 자동화 메인 작업 (수집 -> 분석 -> 발송)
    """
    start_time = get_kst_now()
    logger.info(f"=== 데일리 투자 리포트 자동화 프로세스 시작 (KST: {start_time.strftime('%Y-%m-%d %H:%M:%S')}) ===")
    
    try:
        # 1. 유튜브 신규 영상 수집 (지난 24시간)
        logger.info("1단계: 유튜브 4대 채널 신규 영상 수집 중...")
        videos = collect_all_recent_videos(hours=hours)
        
        # 2. Gemini AI 투자 리포트 분석 및 생성
        logger.info("2단계: Gemini AI를 활용한 4대 관점 데일리 리포트 생성 중...")
        report_text = generate_daily_investment_report(videos)
        
        # 3. 텔레그램 메시지 전송 (4,096자 자동 분할 처리)
        logger.info("3단계: 텔레그램 리포트 메시지 발송 중...")
        success = send_telegram_report(report_text)
        
        elapsed = (get_kst_now() - start_time).total_seconds()
        if success:
            logger.info(f"=== 데일리 투자 리포트 발송 완료 (소요시간: {elapsed:.2f}초) ===")
        else:
            logger.warning(f"=== 리포트가 생성되었으나 텔레그램 발송 실패/대체 (소요시간: {elapsed:.2f}초) ===")

    except Exception as e:
        logger.error(f"프로세스 실행 중 예외 발생: {e}", exc_info=True)

def main():
    parser = argparse.ArgumentParser(description="유튜브 투자 영상 분석 및 텔레그램 데일리 리포트 자동화 시스템")
    parser.add_argument("--now", action="store_true", help="스케줄 대기 없이 즉시 리포트 수집 및 전송 실행")
    parser.add_argument("--hours", type=int, default=24, help="수집할 최근 시간 범위 (기본값: 24시간)")
    args = parser.parse_args()

    if args.now:
        logger.info("즉시 실행(--now) 옵션이 감지되었습니다.")
        run_daily_investment_report_job(hours=args.hours)
        return

    # 매일 오전 07:00 스케줄 등록
    target_time = "07:00"
    schedule.every().day.at(target_time).do(run_daily_investment_report_job, hours=24)
    now_kst = get_kst_now().strftime('%Y-%m-%d %H:%M:%S')
    logger.info(f"⏰ 스케줄러가 등록되었습니다 (현재 KST 시각: {now_kst})")
    logger.info(f"⏰ 매일 한국시간 오전 {target_time}에 자동으로 리포트를 발송합니다.")
    logger.info("프로그램을 종료하려면 Ctrl+C를 누르세요.")

    while True:
        try:
            schedule.run_pending()
            time.sleep(30)
        except KeyboardInterrupt:
            logger.info("스케줄러가 사용자에 의해 정지되었습니다.")
            break
        except Exception as e:
            logger.error(f"스케줄러 루프 예외 발생: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
