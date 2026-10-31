# 2027 국내주식 밸류에이션 자동화

## 운영 일정

밸류에이션 예약은 **하나**입니다. GitHub Actions가 `Asia/Seoul` 시간대 **화~토 10:47**에 실행해 **전날 거래일의 KRX 정규장 15:30 종가**로 보고서를 만들고 Telegram 채널 `@biyosi77`에 보냅니다. 토요일 실행은 금요일 종가를 처리합니다. 전날이 휴장일이면 보고서를 만들거나 보내지 않습니다. 11:30, 15:00, 당일 16:17, 18:17 예약은 없습니다. 수동 실행도 `close`만 선택할 수 있습니다.

이 시각은 KRX의 공식 게시 시각을 가정한 값이 아닙니다. 2026-10-30 종가 API는 당일 23:18 KST 실행에서 비어 있었고, 다음 날 10:17 KST 재검증에서 133종목 모두 확인됐습니다. 따라서 실제 관찰된 가용 시각 뒤에 하루 한 번 실행합니다. GitHub 예약은 지연되거나 누락될 수 있습니다. Actions의 **KRX 2027 valuation** 실행 목록과 Telegram 수신 여부를 확인하고, 누락된 날짜만 수동 실행하세요. [GitHub 예약 문법 및 시간대 설명](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onschedule)

## 가격 확인과 호출 수

1. 대상 거래일의 `YYYYMMDD_close` 전송 기록을 먼저 조회합니다. `sent`, `sending`, `market_closed`가 있으면 시세 API를 호출하지 않습니다.
2. KRX 코스피와 코스닥 **일별매매정보**를 각 1회 조회합니다. 각 종목의 `BAS_DD`, 종가, 상장주식 수를 검증합니다. 정상 실행은 KRX 시세 요청 **총 2회**이며 KIS 인증·휴장 조회를 하지 않습니다. 개별 종목, 분봉, 현재가, NXT, 시간외, 전일 가격을 대체 출처로 조회하지 않습니다.
3. KRX 두 자료가 모두 비어 있을 때만 KIS 휴장일 API로 대상 날짜를 확인합니다. 휴장이라면 조용히 건너뛰고, 거래일인데 종가가 아직 없다면 실패 알림만 보냅니다. 자료가 부분 누락된 경우에도 정상 보고서를 보내지 않습니다.
4. HTTP 429는 즉시 중단합니다. 인증 오류는 반복하지 않습니다. 일시적인 5xx·네트워크 오류만 요청 단위에서 최대 3회 시도하며, 수집 전체를 중첩 재시도하지 않습니다. 다음 예약 재시도는 없으며 운영자가 날짜를 지정해 수동 재작업합니다.
5. 133종목 코드를 기준으로 원본 템플릿의 이익 추정치·ROE·메모·서식을 보존합니다. 파일 생성 뒤 종목코드, 거래일, 주가·주식 수, 출처, 계산 결과를 다시 검증합니다. 이익 추정치가 없는 종목은 가격 확인에 성공해도 PER/POR이 미산출일 수 있습니다.

## 수동 실행과 전송 기록

Actions → **KRX 2027 valuation** → **Run workflow**에서 `trade_date`를 `YYYY-MM-DD`로 지정합니다. 기본값 `dry_run=true`는 파일 생성·검증만 하고 전송하지 않습니다. 실제 전송은 `dry_run=false`로 바꾸세요. 테스트 목적의 전송은 `test_send=true`로 두어 메시지에 `[테스트]`가 표시되게 합니다. 지난 거래일의 빠진 정규 보고서를 보내려면 날짜를 명시하고 `test_send=false`를 선택합니다. **이미 보냈거나 전송 결과가 불확실한 회차**만 채널과 기록을 확인한 뒤 `resend=true`로 명시적 재전송할 수 있습니다.

모든 회차는 `krx-valuation-delivery` 그룹에서 직렬 실행됩니다. `valuation-delivery-ledger` 브랜치의 `valuation-sends/YYYYMMDD_close.json`에 전송 전 `sending`, Telegram이 응답한 뒤 메시지 ID와 `sent`를 기록합니다. 문서 전송 후 응답이 유실되면 성공 여부를 알 수 없어 `sending`을 유지하고 자동 재전송하지 않습니다. 채널과 기록을 직접 대조한 뒤 수동 재전송을 결정합니다.

검증된 `valuation_YYYYMMDD_close.xlsx`와 비밀정보를 제외한 `run.json`은 각 실행의 Actions artifact에 저장됩니다. 보존기간 기본값은 **30일**이고 저장소 Variable `VALUATION_ARTIFACT_DAYS`로 변경할 수 있습니다. GitHub `upload-artifact@v4`의 허용 범위는 **1~90일**이며 저장소/조직/기업 보존 정책이 더 짧으면 그 상한이 적용됩니다. 저장소 Secret `KIS_APP_KEY`, `KIS_APP_SECRET`, `KRX_API_KEY`, `TELEGRAM_BOT_TOKEN`과 Variable `TELEGRAM_CHAT_ID=@biyosi77`가 필요합니다. 봇에는 채널의 **메시지 게시** 관리자 권한이 필요합니다.

## 로컬 테스트

```sh
pip install -r valuation/requirements.txt
python -m pytest valuation/tests -q
```

핵심 테스트는 정규장 시점, 휴장, KRX 2회 일괄 조회, 정상 실행의 KIS 호출 생략, 429 중단, 계산·종목 매핑, 전송 기록과 중복 차단을 다룹니다. GitHub 수동 실행에서는 테스트를 돌리고, 매일 예약 실행에서는 시세 작업에 필요한 의존성만 설치합니다.
