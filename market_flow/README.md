# 한국 증시 수급·옵션 데일리 브리프 (4주 파일럿)

운영 기간: 2026-11-05 ~ 2026-12-03 (KST, 거래일만)

## 범위와 시간

- 현물: KOSPI, KOSDAQ의 지수 종가·투자자별 순매수·프로그램 차익/비차익 순매수
- 파생: KOSPI200, KOSDAQ150의 주간 선물·월물/위클리 옵션 종가와 미결제약정
- 기준: 현물 15:30, 파생상품 통상 15:45 종료. 만기일에는 해당 계약의 최종거래 시각을 따로 확인
- 실행 권장: 거래일 16:20 KST 이후. 종가 데이터와 투자자별 수급의 공개 시차가 있으면 실제 자료 확인 뒤 실행
- 결과: A4 최대 2쪽 PDF. 데이터 날짜·출처·조회 시각을 명기

## 분석 원칙

1. 당일 순매수는 **포지션 잔고가 아닌 거래 흐름**으로 표기한다.
2. 옵션 미결제약정과 그릭만 있으면 행사가별 **총 감마/델타 민감도 규모**만 추정한다. 보유자의 매수·매도 방향이 없으므로 시장 순감마·순델타나 딜러 헤지 방향을 단정하지 않는다.
3. 변곡점은 예측치가 아니라 **경계 신호**로 표기한다. 현물 가격과 외국인 선물, 프로그램 흐름이 어긋나는지 확인하고 반증 조건을 함께 적는다.
4. '왜 포지션을 잡았는지'는 관측 데이터에서 가능한 설명을 **가설**로 적고, 확인되지 않은 동기나 인과를 사실로 표현하지 않는다.

## 입력

매일 `data/YYYY-MM-DD.json`을 `example_input.json` 형식으로 채운다. 각 출처의 `asof_kst`는 해당 거래일 주간장 종료 이후 실제 조회 시각으로 설정한다. 다음 날 재조회했으면 다음 날 시각을 그대로 기록한다. 옵션 그릭은 같은 기초지수·같은 장마감 스냅샷이어야 한다. JSON의 `demo`가 `true`면 PDF 시험 생성은 가능하나 텔레그램 발송은 금지된다.

`collect.py`는 KRX 지수 종가와 KIS 투자자별 현물 순매수·프로그램 차익/비차익 순매수를 자동 수집한다. 거래일·자료 날짜를 확인하고 KRX/KIS 종가를 대조한다. 결과 JSON에는 `derivatives: {}`가 남으며 PDF 생성기는 이를 거부한다. 두 파생 지수에 대한 검증된 주간장 종가, 외국인 선물 순매수, 옵션 행사가·미결제약정·그릭·승수가 채워진 후에만 보고서를 발송한다.

2026-11-05 연결 시험 결과, 현재 `KRX_API_KEY`는 KRX 지수 API에 접근하지만 `drv/fut_bydd_trd`, `drv/opt_bydd_trd`에서는 HTTP 401을 받는다. 사용자가 두 서비스 이용 권한을 신청하기로 했다. KIS 옵션 전광판은 조회 당시 델타·감마·미결제약정을 반환하지만, 전일 종가 스냅샷이나 외국인 선물 순매수의 검증된 대체 경로는 아직 확인되지 않았다. 따라서 **자동 발송 예약 작업은 아직 활성화하지 않았다.**

## 실행

```powershell
$python = 'C:\Users\PC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $python .\collect.py --date 2026-11-05 --output .\data\2026-11-05.json
& $python .\daily_brief.py --input .\data\2026-11-05.json --output .\reports
```

발송 전에 사용자 환경변수 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`를 설정하고 봇을 본인만 접근하는 비공개 수신처에 추가한다. `MARKET_FLOW_PRIVATE_RECIPIENT=1`을 명시한 경우에만 `--send`를 사용할 수 있으며 `@채널명` 주소는 차단한다. 같은 날짜/같은 PDF의 중복 발송은 발송 영수증 파일로 막는다.

`@biyosi77`은 공개채널이다. KRX Open API 약관 제11조는 제공 정보를 제3자에게 제공하는 것을 제한하며, KIS Open API 안내는 개인 고객의 시세정보를 본인 투자 목적에만 사용하고 제3자 제공을 금지한다. 현재 API 키로 만든 데이터 PDF를 그 공개채널에 게시하는 경로는 활성화하지 않는다. 별도 재배포 권한이 확인되면 발송 경로를 재검토한다.

데이터가 누락되거나 시각이 맞지 않으면 프로그램은 실패하고 PDF를 전송하지 않는다. PC가 꺼져 있으면 로컬 예약 실행도 작동하지 않는다.

## 연동 체크포인트

- KRX 선물·옵션 두 API 권한 활성화 및 데이터 필드 확인
- 외국인 선물 순매수와 KOSDAQ150 옵션 그릭·행사가의 자동 데이터 경로 확인
- 데이터 공급처 및 계약/사용 범위 확인 (특히 텔레그램 채널 재배포)
- 모든 필수 필드가 16:20 KST까지 제공되는지 실측
- 봇 토큰/채널 ID를 환경변수에 저장하고 시험 채널에서 1회 발송 검증
- 거래일/휴장일 캘린더 및 수집 재시도 추가 후 예약 작업 활성화

## 공식 자료

- KRX 거래시간: https://global.krx.co.kr/contents/GLB/06/0603/0603010300/GLB0603010300.jsp
- KRX KOSPI200 옵션: https://global.krx.co.kr/contents/GLB/02/0201/0201040202/GLB0201040202.jsp
- KRX Open API 목록: https://openapi.krx.co.kr/contents/OPP/INFO/service/OPPINFO004.cmd
- KRX 종가 데이터 제공시각: https://openapi.krx.co.kr/contents/OPP/DATA/OPPDATA002.jsp
- Telegram sendDocument: https://core.telegram.org/bots/api#senddocument
- KRX Open API 이용약관: https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO002.jsp
- KIS Open API 서비스 소개: https://apiportal.koreainvestment.com/about-open-api

