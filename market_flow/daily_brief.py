"""Two-page Korean market-flow brief. Input is a verified end-of-day JSON snapshot."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import date, datetime, time
from html import escape
from pathlib import Path
from urllib import error, request

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, KeepTogether, PageBreak, PageTemplate, Paragraph,
    Spacer, Table, TableStyle,
)

def font_files():
    choices = [
        (Path(r"C:\Windows\Fonts\malgun.ttf"), Path(r"C:\Windows\Fonts\malgunbd.ttf")),
        (Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"), Path("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf")),
    ]
    for regular, bold in choices:
        if regular.exists() and bold.exists():
            return regular, bold
    raise FileNotFoundError("한글 글꼴이 없습니다. Windows 맑은 고딕 또는 Linux fonts-nanum을 설치하세요")
BLUE = colors.HexColor("#17365D")
PALE = colors.HexColor("#EAF0F7")
GRAY = colors.HexColor("#526170")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def checked_snapshot(data):
    trading_date = date.fromisoformat(data["date"])
    require(date(2026, 11, 5) <= trading_date <= date(2026, 12, 3), "4주 파일럿 기간 밖입니다")
    require(trading_date.weekday() < 5, "주말입니다")
    asof = datetime.fromisoformat(data["asof_kst"])
    require(asof.replace(tzinfo=None) >= datetime.combine(trading_date, time(15, 45)),
            "파생상품 주간장 종료 전 자료입니다")
    require(len(data.get("sources", [])) >= 1, "출처가 없습니다")
    for source in data["sources"]:
        stamp = datetime.fromisoformat(source["asof_kst"])
        require(stamp.replace(tzinfo=None) >= datetime.combine(trading_date, time(15, 45)),
                f"출처 시각 오류: {source['name']}")
        require(source.get("url") or source.get("file"), f"출처 위치 누락: {source['name']}")
    require(set(data["markets"]) == {"KOSPI", "KOSDAQ"}, "KOSPI/KOSDAQ 현물 자료가 모두 필요합니다")
    for name, market in data["markets"].items():
        for key in ("close", "prev_close", "foreign_net_bn", "institution_net_bn", "program_arb_net_bn", "program_nonarb_net_bn"):
            require(isinstance(market.get(key), (float, int)), f"{name}.{key} 누락")
        require(market["close"] > 0 and market["prev_close"] > 0, f"{name} 종가 오류")
    require(set(data["derivatives"]) == {"KOSPI200", "KOSDAQ150"}, "두 파생 지수 자료가 모두 필요합니다")
    for name, deriv in data["derivatives"].items():
        expected_multiplier = 250000 if name == "KOSPI200" else 10000
        for key in ("underlying_close", "future_close", "prev_future_close", "future_multiplier_krw"):
            require(isinstance(deriv.get(key), (float, int)), f"{name}.{key} 누락")
        flow = deriv.get("foreign_future_net_contracts")
        require(flow is None or isinstance(flow, (float, int)), f"{name}.foreign_future_net_contracts 오류")
        require(deriv["underlying_close"] > 0 and deriv["future_close"] > 0
                and deriv["prev_future_close"] > 0, f"{name} 지수/선물 종가 오류")
        require(deriv["future_multiplier_krw"] == expected_multiplier,
                f"{name} 정규 선물 승수 오류")
        require(len(deriv.get("options", [])) > 0, f"{name} 옵션 체인 누락")
        require({option.get("series") for option in deriv["options"]} == {"monthly", "weekly"},
                f"{name} 월물/위클리 옵션이 모두 필요합니다")
        for option in deriv["options"]:
            for key in ("strike", "oi", "delta", "gamma", "option_multiplier_krw"):
                require(isinstance(option.get(key), (int, float)), f"{name} 옵션 {key} 누락")
            require(option["kind"] in ("C", "P") and option["series"] in ("monthly", "weekly"), "옵션 종류 오류")
            require(option["strike"] > 0 and option["oi"] >= 0 and option["gamma"] >= 0,
                    "옵션 행사가/미결제약정/감마 오류")
            require(-1 <= option["delta"] <= 1, "옵션 델타 범위 오류")
            require(option["option_multiplier_krw"] == expected_multiplier,
                    f"{name} 정규 옵션 승수 오류")
            require(date.fromisoformat(option["expiry"]) >= trading_date, "만기 지난 옵션이 포함됨")
    return trading_date


def sign(value):
    return "+" if value > 0 else ("−" if value < 0 else "0")


def bn(value):
    return f"{value:+,.1f}" if value else "0.0"


def market_comment(name, m, d):
    move = (m["close"] / m["prev_close"] - 1) * 100
    program = m["program_arb_net_bn"] + m["program_nonarb_net_bn"]
    f = d["foreign_future_net_contracts"]
    if f is None:
        return ("현물·프로그램 흐름 관측, 외국인 선물 수급 미확인",
                "변곡점 판단 보류: 선물 투자자별 수급을 확보한 뒤 현물·프로그램 흐름과 대조",
                "가설: 현물과 프로그램 수급의 동행 여부는 확인할 수 있다. 외국인 선물 순매수와 거래 동기가 확인되지 않아 방향성·헤지 거래의 인과는 판단할 수 없다.")
    if move > 0 and m["foreign_net_bn"] < 0 and f < 0:
        direction = "가격 상승과 외국인 현물·선물 순매도가 엇갈림"
        watch = "고점 경계: 다음 거래일 현물 유입 회복과 선물 순매수 전환 여부 확인"
    elif move < 0 and m["foreign_net_bn"] > 0 and f > 0:
        direction = "가격 하락 중 외국인 현물·선물 순매수 유입"
        watch = "저점 경계: 다음 거래일 가격 반등과 프로그램 수급 지속 여부 확인"
    elif m["foreign_net_bn"] > 0 and f > 0 and program > 0:
        direction = "현물·선물·프로그램 매수 흐름 동행"
        watch = "상승 지속 관찰: 유입 약화 또는 선물 반전 시 가설 재검토"
    elif m["foreign_net_bn"] < 0 and f < 0 and program < 0:
        direction = "현물·선물·프로그램 매도 흐름 동행"
        watch = "하락 지속 관찰: 매도 둔화와 가격 회복 시 가설 재검토"
    else:
        direction = "현물·선물·프로그램 방향 혼재"
        watch = "방향 확인 대기: 다음 거래일 수급 정렬 여부 확인"
    hypothesis = ("가설: 현물과 선물의 동행 여부는 헤지 또는 방향성 거래의 가능성을 시사한다. "
                  "차익/비차익 프로그램 변화가 이를 보강하는지 확인해야 하며, 거래 동기는 공개 수급만으로 확정할 수 없다.")
    return direction, watch, hypothesis


def gamma_levels(deriv):
    spot = deriv["underlying_close"]
    by_strike = {}
    gross_delta = 0.0
    for o in deriv["options"]:
        # One-percent move gamma sensitivity in KRW; gross magnitude, not signed dealer exposure.
        gamma_krw = o["gamma"] * o["oi"] * o["option_multiplier_krw"] * spot * spot * 0.01
        by_strike[o["strike"]] = by_strike.get(o["strike"], 0.0) + gamma_krw
        gross_delta += abs(o["delta"]) * o["oi"] * o["option_multiplier_krw"] * spot
    levels = sorted(by_strike.items(), key=lambda item: item[1], reverse=True)[:3]
    return levels, gross_delta / 1e8


def make_pdf(data, output):
    font, font_bold = font_files()
    pdfmetrics.registerFont(TTFont("Malgun", str(font)))
    pdfmetrics.registerFont(TTFont("MalgunBold", str(font_bold)))
    styles = {
        "title": ParagraphStyle("title", fontName="MalgunBold", fontSize=17, leading=25, textColor=BLUE, spaceAfter=7),
        "sub": ParagraphStyle("sub", fontName="MalgunBold", fontSize=10, leading=15, textColor=BLUE, spaceBefore=9, spaceAfter=4),
        "body": ParagraphStyle("body", fontName="Malgun", fontSize=8.7, leading=14, textColor=colors.HexColor("#22313F"), spaceAfter=4),
        "tiny": ParagraphStyle("tiny", fontName="Malgun", fontSize=7.2, leading=11, textColor=GRAY),
        "cell": ParagraphStyle("cell", fontName="Malgun", fontSize=8, leading=12),
        "head": ParagraphStyle("head", fontName="MalgunBold", fontSize=8, leading=12, textColor=colors.white),
    }
    P = lambda value, style="body": Paragraph(escape(str(value)), styles[style])
    incomplete = any(d["foreign_future_net_contracts"] is None for d in data["derivatives"].values())
    story = [P("한국 증시 수급·옵션 데일리 브리프" + (" | 검토본" if incomplete else ""), "title"),
             P(f"{data['date']}  |  현물 15:30 · 파생 주간장 종가  |  자료 확인 {data['asof_kst'][:16]} KST", "tiny"),
             *([P("외국인 선물 순매수 자료 미확보 · 방향 해석 제한 · 텔레그램 발송 금지", "body")] if incomplete else []),
             P("오늘의 수급", "sub")]
    rows = [[P(x, "head") for x in ("시장", "종가 / 등락", "외국인 현물", "기관 현물", "프로그램 차익/비차익")]]
    for name in ("KOSPI", "KOSDAQ"):
        m = data["markets"][name]
        move = (m["close"] / m["prev_close"] - 1) * 100
        rows.append([P(name, "cell"), P(f"{m['close']:,.2f} / {move:+.2f}%", "cell"),
                     P(f"{bn(m['foreign_net_bn'])} 십억원", "cell"),
                     P(f"{bn(m['institution_net_bn'])} 십억원", "cell"),
                     P(f"{bn(m['program_arb_net_bn'])} / {bn(m['program_nonarb_net_bn'])}", "cell")])
    table = Table(rows, colWidths=[65, 106, 105, 101, 135], hAlign="LEFT")
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), BLUE), ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#D9E1EA")),
                               ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 7),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    story += [table, P("선물 흐름 및 방향", "sub")]
    for market, index in (("KOSPI", "KOSPI200"), ("KOSDAQ", "KOSDAQ150")):
        d, w, h = market_comment(market, data["markets"][market], data["derivatives"][index])
        f = data["derivatives"][index]
        future_move = (f["future_close"] / f["prev_future_close"] - 1) * 100
        flow_text = (f"{f['foreign_future_net_contracts']:+,}계약" if f["foreign_future_net_contracts"] is not None
                     else "미확인")
        story += [P(f"{index}: 선물 {f['future_close']:,.2f} ({future_move:+.2f}%), 외국인 선물 당일 순매수 {flow_text}"),
                  P(f"관측 - {d}"), P(w)]
    story += [P("해석과 반증", "sub"),
              P("현물 가격과 관측 가능한 수급 흐름의 동행/괴리를 검토한다. 외국인 선물 수급이 없으면 변곡점 경계 신호의 판단을 보류한다. 단일 거래일만으로 고점·저점을 확정하지 않는다."),
              P("반증 조건: 다음 거래일 가격과 수급이 반대로 재정렬되거나, 만기·롤오버·일회성 리밸런싱의 영향으로 확인될 경우 방향 해석을 수정한다."),
              P("당일 순매수는 거래 흐름이며 누적 보유 포지션을 의미하지 않는다.", "tiny"),
              PageBreak(),
              P("옵션 델타·감마 지도", "title"),
              P("KRX 종가·내재변동성의 무이자·무배당 Black-Scholes 근사와 공개 미결제약정 기반 총 민감도. 순포지션의 부호는 확인되지 않음.", "tiny")]
    for name in ("KOSPI200", "KOSDAQ150"):
        deriv = data["derivatives"][name]
        levels, gross_delta_bn = gamma_levels(deriv)
        story += [P(f"{name} | 기초지수 {deriv['underlying_close']:,.2f}", "sub"),
                  P("감마 집중 행사가: " + ", ".join(f"{k:,.2f} ({v/1e8:,.1f}억원/1%)" for k, v in levels)),
                  P(f"옵션 총 델타 명목 규모(절댓값 합): {gross_delta_bn:,.1f}억원. 매수·매도 방향 미상으로 순델타와 딜러 감마 부호는 산출 불가."),
                  P("해석 가설: 집중 행사가 인근에서는 헤지 수요가 커질 수 있다. 실제 매수·매도 주체와 신규/청산 거래를 확인해야 헤지 방향을 판단할 수 있다.")]
    story += [P("인과 가설 검증", "sub")]
    for market, index in (("KOSPI", "KOSPI200"), ("KOSDAQ", "KOSDAQ150")):
        _, _, h = market_comment(market, data["markets"][market], data["derivatives"][index])
        story.append(P(f"{market} - {h}"))
    story += [P("자료·기준", "sub")]
    for source in data["sources"]:
        story.append(P(f"{source['name']} | {source['asof_kst']} KST | {source.get('url') or source.get('file')}", "tiny"))
    story += [Spacer(1, 8), P("본 브리프는 수급 해석용이며, 변곡점과 매매 동기를 확정하는 자료가 아닙니다.", "tiny")]

    def footer(canvas, doc):
        if data.get("demo"):
            canvas.setFont("MalgunBold", 9)
            canvas.setFillColor(colors.HexColor("#A32929"))
            canvas.drawRightString(A4[0] - 42, A4[1] - 25, "가상 데이터 샘플 · 발송 금지")
        elif incomplete:
            canvas.setFont("MalgunBold", 9)
            canvas.setFillColor(colors.HexColor("#A32929"))
            canvas.drawRightString(A4[0] - 42, A4[1] - 25, "선물 수급 미확인 · 발송 금지")
        canvas.setFont("Malgun", 7)
        canvas.setFillColor(GRAY)
        canvas.drawString(42, 28, f"{data['date']}  ·  주간장 기준")
        canvas.drawRightString(A4[0] - 42, 28, f"{doc.page} / 2")

    doc = BaseDocTemplate(str(output), pagesize=A4, leftMargin=42, rightMargin=42, topMargin=42, bottomMargin=42)
    frame = Frame(42, 42, A4[0] - 84, A4[1] - 84, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates(PageTemplate(id="brief", frames=frame, onPage=footer))
    doc.build(story)


def send_telegram(pdf_path, trading_date, output_dir):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    require(token and chat_id, "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 환경변수가 필요합니다")
    require(os.environ.get("MARKET_FLOW_PRIVATE_RECIPIENT") == "1",
            "본인만 접근하는 비공개 수신처 확인이 필요합니다")
    require(not chat_id.startswith("@"), "공개 채널 주소로 발송할 수 없습니다")
    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    receipt = output_dir / f"{trading_date}.telegram.json"
    if receipt.exists() and json.loads(receipt.read_text(encoding="utf-8")).get("sha256") == digest:
        print("이미 동일한 PDF를 발송했습니다")
        return
    boundary = "CodexBriefBoundary"
    pdf_bytes = pdf_path.read_bytes()
    fields = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat_id}\r\n"
              f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n"
              f"한국 증시 수급·옵션 브리프 | {trading_date} 주간장 종가 기준\r\n"
              f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; filename=\"{pdf_path.name}\"\r\n"
              f"Content-Type: application/pdf\r\n\r\n").encode("utf-8")
    body = fields + pdf_bytes + f"\r\n--{boundary}--\r\n".encode()
    req = request.Request(f"https://api.telegram.org/bot{token}/sendDocument", data=body,
                          headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
    try:
        with request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read())
    except error.HTTPError as exc:
        raise RuntimeError(f"텔레그램 HTTP 오류 {exc.code}; 봇 권한과 채널 ID를 확인하세요") from None
    except error.URLError:
        raise RuntimeError("텔레그램 연결 실패; 네트워크 상태를 확인하세요") from None
    require(result.get("ok"), "텔레그램 발송 실패")
    receipt.write_text(json.dumps({"date": str(trading_date), "sha256": digest,
                                   "message_id": result["result"]["message_id"]}, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--send", action="store_true")
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    trading_date = checked_snapshot(data)
    require(not (args.send and data.get("demo")), "가상 데이터는 발송할 수 없습니다")
    require(not (args.send and any(d["foreign_future_net_contracts"] is None
                                   for d in data["derivatives"].values())),
            "외국인 선물 순매수 누락: 검토본은 발송할 수 없습니다")
    args.output.mkdir(parents=True, exist_ok=True)
    pdf_path = args.output / f"KRX_flow_brief_{trading_date}.pdf"
    make_pdf(data, pdf_path)
    from pypdf import PdfReader
    require(len(PdfReader(str(pdf_path)).pages) <= 2, "보고서가 2쪽을 초과했습니다")
    print(pdf_path)
    if args.send:
        send_telegram(pdf_path, trading_date, args.output)


if __name__ == "__main__":
    main()

