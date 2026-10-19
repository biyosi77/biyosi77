# 2027 국내주식 밸류에이션 자동화

> 운영 상태 (2026-10-19): 코드가 기본 브랜치에 반영되었으며 수동 실행만 가능합니다. 실제 데이터 dry-run에서 KIS 토큰 `EGW00105`(AppSecret 오류)와 KRX HTTP 401이 확인되어 예약 실행과 파일 전송을 보류했습니다. 텔레그램 채널 게시 권한은 확인했습니다. 두 데이터 인증을 수정한 뒤 실제 데이터 dry-run, `[테스트]` 전송을 확인하고 아래 예약을 활성화합니다.

`valuation/template/2027_valuation_20261015_close.xlsx`의 90종목을 기준으로 별도 보고서를 만듭니다. 기존 유튜브 리포트의 `.github/workflows/daily_report.yml`, `main.py`, 루트 의존성은 수정하지 않습니다. 보고서는 `valuation_YYYYMMDD_1130.xlsx` 또는 `valuation_YYYYMMDD_close.xlsx`이며 원본 템플릿을 덮어쓰지 않습니다.

## 데이터와 계산

| 항목 | 조회 기준 |
| --- | --- |
| 거래일 | 한국투자증권(KIS) 국내휴장일조회 `opnd_yn=Y`; 날짜 응답이 없으면 실패 |
| 11:30 가격 | KIS **KRX 시장 코드 `J`**의 거래일 지정 분봉. 정확히 11:30이 없으면 09:00~11:30의 마지막 분봉. 실제 분봉 시각을 `원자료`에 기록 |
| 종가 | 한국거래소(KRX) 유가증권/코스닥 **해당 거래일** 일별매매정보 `TDD_CLSPRC`. 16:00에 아직 공표되지 않았으면 제한 재조회 후 실패 알림 |
| 상장주식 수 | 11:30: KRX 해당 거래일 종목기본정보 `LIST_SHRS`. 당일 KRX 기본정보가 아직 없을 때에만 KIS `J` 현재가 응답 `lstn_stcn`을 사용하고 출처에 표시. 과거일 재실행에는 이 대체를 금지. 종가: KRX 해당 거래일 일별매매정보 `LIST_SHRS` |

NXT·통합시세·시간외·전일 가격으로 대체하지 않습니다. 종목별 가격 또는 주식 수를 확인하지 못하면 `미확인`, 시가총액·PER·POR은 `미산출`로 표시합니다. 전체 수집 실패나 엑셀 검증 실패는 정상 보고서로 전송하지 않습니다. 기존 27E 순이익·영업이익·ROE는 원자료에서 보존합니다. 시가총액(억원) = 가격 × 상장주식 수 ÷ 100,000,000; PER = 시가총액 ÷ 순이익; POR = 시가총액 ÷ 영업이익입니다. 이익이 없거나 0 이하인 배수도 미산출입니다. 원자료 T:W열에 가격 출처·실제 기준시각·조회시각·예외 사유를 기록합니다. 수식과 검증된 계산 캐시를 함께 저장합니다.

KIS REST API의 `J` 시장 코드와 거래일 지정 분봉은 [한국투자증권 공식 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_time_dailychartprice/inquire_time_dailychartprice.py)에, 휴장일 조회는 [공식 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/chk_holiday/chk_holiday.py)에 나옵니다. KRX는 [유가증권 일별매매정보](https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES002_S2.cmd?BO_ID=JvJFzlAENzZlPBDNGAWC), [코스닥 일별매매정보](https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES002_S2.cmd?BO_ID=hZjGpkllgCBCWqeTsYFj), [유가증권 종목기본정보](https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES002_S2.cmd?BO_ID=PiwgMdTwmsenXhmqqxuj), [코스닥 종목기본정보](https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES002_S2.cmd?BO_ID=CifLHplnUFMgpHIMMPXs)를 사용합니다.

## GitHub 설정

1. 저장소 **Settings → Secrets and variables → Actions → Secrets**에 `TELEGRAM_BOT_TOKEN`, `KIS_APP_KEY`, `KIS_APP_SECRET`, `KRX_API_KEY`를 등록합니다. KRX 키에 위 네 API의 사용 승인이 있어야 합니다. 토큰이나 키를 이슈·채팅·커밋·로그에 넣지 마세요. 기존 유튜브 자동화의 Secret은 유지합니다.
2. 같은 메뉴의 **Variables**에 `TELEGRAM_CHAT_ID`를 `@biyosi77`로 등록합니다. 기존 워크플로는 동명의 Secret을 사용하므로 서로 충돌하지 않습니다. 선택 변수 `VALUATION_ARTIFACT_DAYS`의 기본값은 **30일**입니다. 공개 저장소는 1~90일, 비공개 저장소는 1~400일이며 저장소·조직 정책의 더 낮은 한도가 우선합니다. 범위를 넘으면 artifact 업로드가 실패합니다. [GitHub 보존기간 문서](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository).
3. `@biyosi77` 채널에 봇을 관리자로 추가하고 **메시지 게시** 권한만 부여합니다. 실행 전 `getMe`/`getChatMember`로 해당 권한을 확인합니다. 다른 관리자 권한은 필요하지 않습니다.
4. 기본 브랜치에서 GitHub Actions를 활성화합니다. 워크플로는 `contents: write`만 요청합니다. 이는 전송 기록용 `valuation-delivery-ledger` 브랜치에 파일을 쓰기 위한 권한이며, 기존 워크플로 권한을 변경하지 않습니다. 저장소 정책이 `GITHUB_TOKEN`의 쓰기를 막으면 이를 허용해야 합니다.

## 실행 및 확인

GitHub Actions의 [공식 예약 문법](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onschedule)에 따라 최종 활성화할 예약은 `timezone: Asia/Seoul`과 평일 **12:00**, **16:00** cron입니다. 현재는 데이터 인증 검증 전이므로 예약이 비활성화되어 있습니다. 12:00 실행은 11:30 분봉을, 16:00 실행은 KRX 정규장 종가를 요청합니다. 실제 실행이 늦어져도 지정 회차의 분봉/종가만 선택하며, 자정이나 주말을 넘긴 지연은 가장 최근 평일의 해당 회차로 귀속합니다. GitHub 예약 이벤트는 원래 예정일을 별도로 전달하지 않으므로 **다음 동일 회차 예약까지 넘는 장기 지연**은 자동으로 원래 날짜를 확정할 수 없습니다. 이 경우 실행 기록을 확인하고 누락일을 수동 지정해야 합니다. 휴장일은 생성·전송을 건너뜁니다.

**Actions → KRX 2027 valuation → Run workflow**에서 `trade_date`(YYYY-MM-DD, 비우면 KST 오늘), `slot`(`1130`/`close`)을 지정할 수 있습니다. 기본 `dry_run=true`는 파일 생성·검증만 하고 텔레그램으로 보내지 않습니다. 실제 시험 전송은 `dry_run=false`, `test_send=true`로 실행하면 메시지에 `[테스트]`가 붙습니다. `resend=true`는 기존 전송 기록을 확인한 뒤에만 명시적으로 사용하세요. 과거 날짜의 11:30 분봉은 KIS 제공 가능 기간에 제한될 수 있으며, 없으면 미확인 처리합니다.

각 실행의 검증된 엑셀과 비밀정보 없는 `run.json`은 해당 실행의 **Artifacts**에 저장됩니다. 워크플로 실패 시에도 만들어진 파일과 로그는 업로드를 시도합니다. 로컬에서는 `pip install -r valuation/requirements.txt` 후 `python -m pytest valuation/tests -q`로 핵심 테스트를 실행할 수 있습니다. `python -m valuation.run --trade-date 2026-10-15 --slot close --dry-run --fixture-template-prices`는 **원본 템플릿 값만 사용하는 테스트**로, 실거래 시세 검증이 아닙니다. 생성 파일에 `테스트 / 실제 시세 검증 없음`이 표시됩니다.

## 중복·실패 처리

워크플로 전체를 직렬화하고, 텔레그램 전송 전에 별도 Git 브랜치의 `valuation-sends/YYYYMMDD_slot.json`에 `sending`을 기록합니다. 텔레그램 `sendDocument`가 `ok=true`와 메시지 ID를 반환한 뒤에만 `sent`로 갱신합니다. `sent` 또는 `sending` 기록이 있으면 자동 재전송을 차단합니다. 네트워크 응답 유실이나 기록 갱신 실패 시 `sending`이 유지되어 **전송 여부 불명확**으로 처리합니다. 이때 채널과 GitHub 기록을 직접 확인하고 수동 `resend=true`를 선택해야 합니다. Telegram의 명확한 429 제한 응답만 최대 2회 재시도합니다. 다른 전송 오류는 중복 위험 때문에 자동 재시도하지 않으며 실패 알림을 시도합니다. 파일은 artifact로 보존합니다.

GitHub [예약 실행은 지연되거나 누락될 수 있고](https://docs.github.com/en/actions/how-tos/troubleshoot-workflows#scheduled-workflows-running-at-unexpected-times), 기본 브랜치의 워크플로만 실행됩니다. 공개 저장소는 60일 비활동 시 예약이 비활성화될 수 있습니다. 매 거래일 Actions 실행 목록에서 두 회차의 `run.json` 상태와 artifact를 확인하고, 누락 시 날짜·회차를 지정해 수동 실행하세요. `sending` 기록이 있으면 먼저 텔레그램 채널 게시 여부를 확인하세요.
