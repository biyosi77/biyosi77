# 2027 국내주식 밸류에이션 자동화

## 당일 종가 운영

밸류에이션 예약은 **평일 15:47 KST 한 건**입니다. 대상은 **그날 KRX 정규장 15:30 종가**이며, 보고서를 같은 날 **17:00 KST 전까지** Telegram 채널 `@biyosi77`에 보내는 것이 목표입니다. GitHub Actions에는 다른 밸류에이션 예약이 없습니다. 휴장일에는 보고서를 만들거나 보내지 않습니다. 과거 거래일 재작업은 수동 실행에서 날짜를 명시합니다.

KRX Open API의 당일 일별매매정보는 2026-10-30 23:18 KST에도 비어 있었으므로, 당일 가격은 한국투자증권(KIS)의 `J`(KRX) 시장 **정확한 15:30 분봉**으로 확인합니다. 대상 날짜의 `stck_cntg_hour=153000`과 가격을 요구하며, 상장주식 수는 KIS 현재가 응답의 `lstn_stcn`만 사용합니다. 현재가 응답의 가격은 사용하지 않습니다. 2026-10-30 삼성전자에서 KIS 일봉 가격은 220,500원으로 KRX 정규장 확정 종가 225,000원과 달랐고, KIS 15:30 분봉은 225,000원으로 일치했습니다. 따라서 KIS 일봉 `stck_clpr`, NXT, 통합 시세, 시간외, 전일 가격을 대체값으로 사용하지 않습니다. 과거 날짜 재작업에는 KRX 코스피·코스닥 일별매매정보 일괄 조회를 사용합니다.

2026-10-30 자료를 대상으로 GitHub Actions에서 전체 133종목을 대조했을 때, 15:30 분봉이 확인된 132종목의 가격은 모두 KRX 확정 종가와 일치했습니다. 1종목(`172670`)은 정확한 15:30 분봉이 없어 미확인 처리 대상입니다. 이 대조는 **다음 날 과거 분봉 조회**로 수행했으며, 당일 15:47 실시간 수집 성공 여부는 첫 거래일 예약 실행으로 확인해야 합니다.

[한국투자증권 공식 분봉 API 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_time_itemchartprice/inquire_time_itemchartprice.py) · [KIS 시장 코드 설명](https://github.com/koreainvestment/open-trading-api/blob/main/MCP/Kis%20Trading%20MCP/configs/domestic_stock.json) · [GitHub 예약 문법과 시간대](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onschedule)

## 조회 및 실패 처리

1. `YYYYMMDD_close` 전송 기록에 `sent`, `sending`, `market_closed`가 있으면 시세 API 호출 전에 종료합니다.
2. 당일에는 KIS 휴장일 API를 한 번 확인합니다. 거래일이면 대표 종목 한 개의 당일 KRX 15:30 분봉과 상장주식 수를 확인합니다. 자료가 아직 없으면 16:45 KST까지 최대 5분 간격으로 그 종목만 다시 조회합니다.
3. 대표 종목이 확인되면 나머지 종목의 15:30 분봉과 상장주식 수를 각각 조회합니다. 종목 간 0.2초 간격을 두며 한 실행의 토큰을 재사용합니다. 누락 종목만 20초 뒤 한 번 재조회합니다. 정상 경로는 토큰 1회, 휴장 조회 1회, 분봉 133회, 주식 수 133회입니다. KIS의 [실전계좌 초당 호출 제한](https://apiportal.koreainvestment.com/community/10000000-0000-0011-0000-000000000001/post/d0d1a83f-6f8d-4437-9700-6d26702fd989)보다 낮은 속도로 조회합니다.
4. 당일 날짜·KRX 시장·정확한 15:30 시각·가격·상장주식 수를 검증합니다. 일부 종목만 실패하면 해당 값과 시가총액·PER·POR을 `미확인`/`미산출`로 두고 메시지에 부분 누락을 표시합니다. 전체 실패나 파일 검증 실패면 정상 보고서를 보내지 않고 실패 알림을 보냅니다. HTTP 429·인증 오류는 수집을 중단하고 반복 요청하지 않습니다.
5. 133종목 코드로 원본 템플릿의 이익 추정치·ROE·메모·서식을 보존하고, 생성 후 코드·날짜·가격·출처·계산 결과를 다시 검증합니다. 이익 추정치가 없는 종목은 가격 확인에 성공해도 PER/POR이 미산출일 수 있습니다.

**17:00 전송은 GitHub Actions가 제때 시작하고 KIS 당일 일봉이 제때 제공될 때 달성할 수 있습니다.** GitHub 예약은 지연·누락될 수 있어 정시 전송을 보장하지 않습니다. 17:00 뒤에 전송되면 메시지에 `[17시 이후 지연]`을 표시합니다. [Actions 실행 목록](https://github.com/biyosi77/biyosi77/actions/workflows/valuation.yml)에서 실행 여부를 확인할 수 있습니다. 내부 자료 확인은 한 예약 실행 안에서만 수행하며 별도 재시도 예약은 없습니다.

## 수동 실행과 중복 방지

Actions → **KRX 2027 valuation** → **Run workflow**에서 `trade_date`를 `YYYY-MM-DD`로 지정할 수 있습니다. 기본값 `dry_run=true`는 파일 생성·검증만 합니다. 실제 전송은 `dry_run=false`로 바꾸세요. 테스트 전송은 `test_send=true`로 표시합니다. 이미 보냈거나 전송 결과가 불확실한 회차는 채널과 기록을 확인한 뒤 `resend=true`로 명시적으로 재전송할 수 있습니다.

모든 회차는 `krx-valuation-delivery` 그룹에서 직렬 실행됩니다. `valuation-delivery-ledger` 브랜치의 `valuation-sends/YYYYMMDD_close.json`에 전송 전 `sending`, Telegram 응답 후 메시지 ID와 `sent`를 기록합니다. 문서 전송 응답이 유실되면 자동 재전송하지 않습니다.

검증된 `valuation_YYYYMMDD_close.xlsx`와 비밀정보를 제외한 `run.json`은 Actions artifact에 저장됩니다. 기본 보존기간은 **30일**, 저장소 Variable `VALUATION_ARTIFACT_DAYS`로 조정 가능하며 GitHub 허용 범위는 **1~90일**입니다. 저장소 Secret `KIS_APP_KEY`, `KIS_APP_SECRET`, `KRX_API_KEY`, `TELEGRAM_BOT_TOKEN`과 Variable `TELEGRAM_CHAT_ID=@biyosi77`가 필요합니다. 봇에는 채널의 메시지 게시 관리자 권한이 필요합니다.

## 테스트

```sh
pip install -r valuation/requirements.txt
python -m pytest valuation/tests -q
```

테스트는 당일 시점 선택, 휴장, 날짜·시장 검증, 누락 처리, 종목 매핑·계산, 중복 전송 방지를 확인합니다. 수동 실행에서는 테스트를 돌리고, 정기 실행에서는 시세 작업만 수행합니다.
