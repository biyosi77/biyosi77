# 2027 국내주식 밸류에이션 자동화

> 운영 상태 (2026-10-20): 신규 YoY 양식 적용 후 10/19 11:30 예약은 17:20 KST에 지연 실행되어 90/90종목 전송에 성공했습니다. 10/19 종가 예약은 23:13 KST에 실행됐으나 KRX 일별 데이터가 비어 실패했습니다. 10/20 12:30 KST 재조회에서는 90/90종목이 확인되어 종가 보고서를 수동 전송했고 메시지 ID 157 및 전송 기록 `sent`를 확인했습니다. 10/20 정오 예약 이벤트는 12:30 KST까지 생성되지 않아 11:30 보고서를 수동 전송했고 메시지 ID 158 및 전송 기록 `sent`를 확인했습니다. 정시 예약과 별도 재확인 회차, KRX 일별 데이터가 없을 때 날짜·시장 검증을 거친 KIS KRX 일봉 대체 경로를 추가했습니다. 10/19 삼성전자 종가는 두 출처에서 218,000원으로 일치했습니다.

`valuation/template/2027_valuation_20261020_133.xlsx`의 **133종목**과 26E·YoY 열을 기준으로 별도 보고서를 만듭니다. 기존 90종목 템플릿은 이력으로 보존했습니다. 2026-10-20에 요청받은 43종목의 코드와 시장은 [KRX 상장법인 목록](https://kind.krx.co.kr/corpgeneral/corpList.do?method=download)에서 대조했으며 매핑은 `valuation/template/additions_20261020.json`에 기록했습니다. 요청의 `한야이엔지`는 상장명 `한양이엔지`(045100)로, `삼화콘덴서`는 상장법인 `삼화콘덴서공업`(001820)의 종목 표시명으로 연결했습니다. `SFA`(056190)와 기존 `SFA반도체`(036540)는 각각 별도 종목입니다. 기존 유튜브 리포트의 `.github/workflows/daily_report.yml`, `main.py`, 루트 의존성은 수정하지 않습니다. 보고서는 `valuation_YYYYMMDD_1130.xlsx` 또는 `valuation_YYYYMMDD_close.xlsx`이며 원본 템플릿을 덮어쓰지 않습니다.

## 데이터와 계산

| 항목 | 조회 기준 |
| --- | --- |
| 거래일 | 한국투자증권(KIS) 국내휴장일조회 `opnd_yn=Y`; 날짜 응답이 없으면 실패 |
| 11:30 가격 | KIS **KRX 시장 코드 `J`**의 거래일 지정 분봉. 정확히 11:30이 없으면 09:00~11:30의 마지막 분봉. 실제 분봉 시각을 `원자료`에 기록 |
| 종가 | 우선 KRX 유가증권/코스닥 **해당 거래일** 일별매매정보 `TDD_CLSPRC`. 비어 있거나 일부 종목이 빠지면 KIS **KRX 시장 코드 `J`**의 날짜 지정 일봉 원주가 `stck_clpr`를 조회하고 응답의 영업일자가 요청일과 정확히 일치할 때만 사용. 원자료에 실제 출처 표시 |
| 상장주식 수 | 우선 KRX 해당 거래일 일별매매정보 또는 종목기본정보 `LIST_SHRS`. 당일 KRX 기본정보가 아직 없을 때에만 KIS `J` 현재가 응답 `lstn_stcn`을 사용하고 출처에 표시. 과거일 재실행에는 이 대체를 금지 |

NXT·통합시세·시간외·전일 가격으로 대체하지 않습니다. 종목별 가격 또는 주식 수를 확인하지 못하면 `미확인`, 시가총액·PER·POR은 `미산출`로 표시합니다. 전체 수집 실패나 엑셀 검증 실패는 정상 보고서로 전송하지 않습니다. 원자료의 26E·27E 순이익·영업이익, ROE, 출처 및 메모를 보존합니다. 시가총액(억원) = 가격 × 상장주식 수 ÷ 100,000,000; PER = 시가총액 ÷ 27E 순이익; POR = 시가총액 ÷ 27E 영업이익입니다. 이익이 없거나 0 이하인 배수도 미산출입니다. 새 YoY 열은 템플릿의 수식과 흑자전환·적자전환·손익분기 규칙을 유지합니다. 원자료 T:X열은 신규 26E 추정치·출처 등이므로 보존하고, Y:AB열에 가격 출처·실제 기준시각·조회시각·예외 사유를 기록합니다. 모든 행은 종목코드 기준으로 연결하며 수식과 검증된 계산 캐시를 함께 저장합니다.

추가한 43종목에는 사용자가 제공한 26E·27E 이익 추정치와 ROE가 없습니다. 해당 원자료 칸은 빈값으로 유지합니다. 가격과 상장주식 수가 조회되면 시가총액은 계산하지만, 이익 추정치가 필요한 PER·POR·YoY는 `미산출` 또는 `미확인`으로 표시합니다. 추정치나 ROE를 0으로 채우거나 자동 추측하지 않습니다. 추후 승인된 추정치를 템플릿의 해당 **종목코드 행**에 입력하면 다음 실행부터 계산됩니다. 템플릿은 `python -m valuation.template.expand_20261020`으로 기존 90종목 파일과 매핑 목록에서 재생성할 수 있습니다. 단, 직접 입력한 추정치가 있다면 재생성 전에 별도로 보존해야 합니다.

KIS REST API의 `J` 시장 코드와 거래일 지정 분봉은 [한국투자증권 공식 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_time_dailychartprice/inquire_time_dailychartprice.py)에, 날짜 지정 일봉 원주가는 [공식 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_daily_itemchartprice/inquire_daily_itemchartprice.py)에, 휴장일 조회는 [공식 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/chk_holiday/chk_holiday.py)에 나옵니다. KRX는 [유가증권 일별매매정보](https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES002_S2.cmd?BO_ID=JvJFzlAENzZlPBDNGAWC), [코스닥 일별매매정보](https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES002_S2.cmd?BO_ID=hZjGpkllgCBCWqeTsYFj), [유가증권 종목기본정보](https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES002_S2.cmd?BO_ID=PiwgMdTwmsenXhmqqxuj), [코스닥 종목기본정보](https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES002_S2.cmd?BO_ID=CifLHplnUFMgpHIMMPXs)를 사용합니다.

## GitHub 설정

1. 저장소 **Settings → Secrets and variables → Actions → Secrets**에 `TELEGRAM_BOT_TOKEN`, `KIS_APP_KEY`, `KIS_APP_SECRET`, `KRX_API_KEY`를 등록합니다. KRX 키에 위 네 API의 사용 승인이 있어야 합니다. 토큰이나 키를 이슈·채팅·커밋·로그에 넣지 마세요. 기존 유튜브 자동화의 Secret은 유지합니다.
2. 같은 메뉴의 **Variables**에 `TELEGRAM_CHAT_ID`를 `@biyosi77`로 등록합니다. 기존 워크플로는 동명의 Secret을 사용하므로 서로 충돌하지 않습니다. 선택 변수 `VALUATION_ARTIFACT_DAYS`의 기본값은 **30일**입니다. 공개 저장소는 1~90일, 비공개 저장소는 1~400일이며 저장소·조직 정책의 더 낮은 한도가 우선합니다. 범위를 넘으면 artifact 업로드가 실패합니다. [GitHub 보존기간 문서](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository).
3. `@biyosi77` 채널에 봇을 관리자로 추가하고 **메시지 게시** 권한만 부여합니다. 실행 전 `getMe`/`getChatMember`로 해당 권한을 확인합니다. 다른 관리자 권한은 필요하지 않습니다.
4. 기본 브랜치에서 GitHub Actions를 활성화합니다. 워크플로는 `contents: write`만 요청합니다. 이는 전송 기록용 `valuation-delivery-ledger` 브랜치에 파일을 쓰기 위한 권한이며, 기존 워크플로 권한을 변경하지 않습니다. 저장소 정책이 `GITHUB_TOKEN`의 쓰기를 막으면 이를 허용해야 합니다.

## 실행 및 확인

GitHub Actions의 [공식 예약 문법](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onschedule)에 따라 `timezone: Asia/Seoul`과 평일 **12:00**, **16:00** 기본 예약을 설정했습니다. 12:00 실행은 11:30 분봉을, 16:00 실행은 KRX 정규장 종가를 요청합니다. GitHub 예약 이벤트가 지연·누락될 수 있어 11:30 회차는 **12:17·13:17**, 종가 회차는 **16:17·18:17**에 재확인합니다. 전날 종가가 여전히 미전송이면 월~토 **09:17·12:47**에도 확인합니다. 이미 `sent`로 기록된 회차는 시세 조회 전에 건너뛰고, 재확인 회차의 일시적인 실패는 반복 알림을 보내지 않습니다. KIS 토큰 발급 제한 `EGW00133`은 65초 기다린 뒤 한 번 재시도합니다.

지연 실행에서도 지정 회차의 분봉 또는 날짜가 일치하는 정규장 종가만 사용합니다. GitHub 예약 이벤트는 예정 날짜를 별도로 전달하지 않으므로 **다음 동일 회차 예약까지 넘는 장기 지연**은 원래 날짜를 확정할 수 없습니다. 이 경우 실행 기록을 확인하고 누락일을 수동 지정해야 합니다. 한국 증시 휴장일에는 생성·전송을 건너뜁니다. GitHub 예약은 정확한 분 단위 실행을 보장하지 않으며, 재확인 회차도 지연·누락될 수 있습니다.

**Actions → KRX 2027 valuation → Run workflow**에서 `trade_date`(YYYY-MM-DD, 비우면 KST 오늘), `slot`(`1130`/`close`)을 지정할 수 있습니다. 기본 `dry_run=true`는 파일 생성·검증만 하고 텔레그램으로 보내지 않습니다. 실제 시험 전송은 `dry_run=false`, `test_send=true`로 실행하면 메시지에 `[테스트]`가 붙습니다. `resend=true`는 기존 전송 기록을 확인한 뒤에만 명시적으로 사용하세요. 과거 날짜의 11:30 분봉은 KIS 제공 가능 기간에 제한될 수 있으며, 없으면 미확인 처리합니다.

각 실행의 검증된 엑셀과 비밀정보 없는 `run.json`은 해당 실행의 **Artifacts**에 저장됩니다. 워크플로 실패 시에도 만들어진 파일과 로그는 업로드를 시도합니다. 로컬에서는 `pip install -r valuation/requirements.txt` 후 `python -m pytest valuation/tests -q`로 핵심 테스트를 실행할 수 있습니다. `python -m valuation.run --trade-date 2026-10-16 --slot close --dry-run --fixture-template-prices`는 **원본 템플릿 값만 사용하는 테스트**로, 실거래 시세 검증이 아닙니다. 생성 파일에 `테스트 / 실제 시세 검증 없음`이 표시됩니다.

## 중복·실패 처리

워크플로 전체를 직렬화하고, 텔레그램 전송 전에 별도 Git 브랜치의 `valuation-sends/YYYYMMDD_slot.json`에 `sending`을 기록합니다. 텔레그램 `sendDocument`가 `ok=true`와 메시지 ID를 반환한 뒤에만 `sent`로 갱신합니다. `sent` 또는 `sending` 기록이 있으면 자동 재전송을 차단합니다. 네트워크 응답 유실이나 기록 갱신 실패 시 `sending`이 유지되어 **전송 여부 불명확**으로 처리합니다. 이때 채널과 GitHub 기록을 직접 확인하고 수동 `resend=true`를 선택해야 합니다. Telegram의 명확한 429 제한 응답만 최대 2회 재시도합니다. 다른 전송 오류는 중복 위험 때문에 자동 재시도하지 않으며 실패 알림을 시도합니다. 파일은 artifact로 보존합니다.

GitHub [예약 실행은 지연되거나 누락될 수 있고](https://docs.github.com/en/actions/how-tos/troubleshoot-workflows#scheduled-workflows-running-at-unexpected-times), 특히 매시 정각은 부하가 높을 수 있습니다. 기본 브랜치의 워크플로만 예약 실행되며 공개 저장소는 60일 비활동 시 예약이 비활성화될 수 있습니다. 매 거래일 Actions 실행 목록에서 두 회차의 `run.json` 상태와 artifact를 확인하고, 누락 시 날짜·회차를 지정해 수동 실행하세요. `sending` 기록이 있으면 먼저 텔레그램 채널 게시 여부를 확인하세요.
