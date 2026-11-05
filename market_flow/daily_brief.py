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


def market_analysis(m, d):
    """Describe the observed disagreement and a falsifiable next-session test."""
    move = (m["close"] / m["prev_close"] - 1) * 100
    foreign = m["foreign_net_bn"]
    institution = m["institution_net_bn"]
    arb = m["program_arb_net_bn"]
    nonarb = m["program_nonarb_net_bn"]
    program = arb + nonarb
    close = m["close"]
    facts = (f"지수 {move:+.2f}%, 외국인 {bn(foreign)}·기관 {bn(institution)} 십억원, "
             f"프로그램 순매수 {bn(program)} 십억원(차익 {bn(arb)}, 비차익 {bn(nonarb)})")
    if move > 0 and foreign < 0:
        headline = "상승했지만 외국인 현물은 순매도: 상승의 수급 확인이 약함"
        counterparty = ("기관 순매수가 외국인 매도와 반대편에 있었지만"
                        if institution > 0 else "기관도 순매수하지 않아")
        program_context = ("프로그램도 순매도여서 관측한 두 수급은 상승을 뒷받침하지 않음."
                           if program < 0 else "프로그램은 순매수였으나 투자자별 수급과 중복될 수 있음.")
        hypothesis = (f"{counterparty}, 종목별 기여도 없이 지수 상승의 매수 주체를 특정할 수 없음. "
                      + program_context)
        confirm = f"다음 장 {close:,.2f} 아래 마감과 외국인 순매도 지속 시 상승 취약 가설 강화"
        reject = f"{close:,.2f} 위 유지와 외국인 순매수 전환 시 경계 완화"
    elif move < 0 and foreign > 0:
        headline = "하락했지만 외국인 현물은 순매수: 매수 유입이 가격을 방어하지 못함"
        counterparty = ("기관 순매도가 외국인 매수와 반대였고" if institution < 0
                        else "기관도 순매수했으나")
        program_context = ("프로그램도 순매수였으므로 관측된 매수 흐름만으로 하락을 설명할 수 없음."
                           if program > 0 else "프로그램 순매도도 하방 압력의 후보임.")
        hypothesis = f"{counterparty}, {program_context} 종목별 기여도와 다른 주체의 거래가 필요함."
        confirm = f"다음 장 {close:,.2f} 위 회복과 외국인 순매수 지속 시 매도 흡수 가설 강화"
        reject = f"{close:,.2f} 아래 마감과 외국인 순매도 전환 시 저점 경계 해제"
    elif move > 0 and foreign > 0 and program > 0:
        headline = "가격·외국인 현물·프로그램 매수가 동행"
        hypothesis = ("동일 방향의 거래 흐름이 상승을 뒷받침한 것으로 해석 가능. "
                      "신규 포지션인지 기존 포지션 청산인지는 거래 흐름만으로 구분할 수 없음.")
        confirm = f"다음 장 {close:,.2f} 위 마감과 외국인·프로그램 순매수 지속 시 동행 강화"
        reject = f"{close:,.2f} 아래 마감 또는 두 수급의 동반 반전 시 해석 약화"
    elif move < 0 and foreign < 0 and program < 0:
        headline = "가격·외국인 현물·프로그램 매도가 동행"
        hypothesis = ("같은 방향의 매도 흐름이 하락 압력을 높인 것으로 해석 가능. "
                      "헤지와 방향성 매도를 분리하려면 선물 투자자별 자료가 필요함.")
        confirm = f"다음 장 {close:,.2f} 아래 마감과 외국인·프로그램 순매도 지속 시 압력 강화"
        reject = f"{close:,.2f} 위 회복과 두 수급의 순매수 전환 시 해석 약화"
    else:
        headline = "가격과 주요 수급의 방향이 섞여 단일 방향 신호가 약함"
        hypothesis = ("주체 간 매매가 상쇄됐거나 일부 종목의 영향이 지수 움직임을 좌우했을 가능성. "
                      "전체 거래대금과 종목별 기여도가 없어 원인을 특정할 수 없음.")
        confirm = f"다음 장 {close:,.2f}을 넘는 종가와 외국인·프로그램 동반 순매수 시 상방 확인"
        reject = f"{close:,.2f} 아래 종가와 두 수급의 동반 순매도 시 하방 확인"
    future_move = (d["future_close"] / d["prev_future_close"] - 1) * 100
    flow = d["foreign_future_net_contracts"]
    futures = (f"선물 종가 {future_move:+.2f}%; 외국인 당일 순매수 "
               + (f"{flow:+,}계약" if flow is not None else "자료 없음"))
    if flow is not None and foreign and flow:
        futures += (" - 외국인 현물·선물 같은 방향" if (foreign > 0) == (flow > 0)
                    else " - 외국인 현물·선물 반대 방향")
    limitation = ("선물 투자자별 흐름이 없어 현물·파생 동행과 헤지 여부는 판단 보류"
                  if flow is None else
                  "선물 순매수는 당일 거래 흐름이며 보유 잔고·헤지 동기를 뜻하지 않음")
    return {"headline": headline, "facts": facts, "futures": futures,
            "hypothesis": hypothesis, "confirm": confirm, "reject": reject,
            "limitation": limitation}


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
    return levels, gross_delta / 1e8, sum(by_strike.values()) / 1e8


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
    analyses = {market: market_analysis(data["markets"][market], data["derivatives"][index])
                for market, index in (("KOSPI", "KOSPI200"), ("KOSDAQ", "KOSDAQ150"))}
    story = [P("한국 증시 수급·옵션 데일리 브리프" + (" | 검토본" if incomplete else ""), "title"),
             P(f"{data['date']}  |  현물 15:30 · 파생 주간장 종가  |  자료 확인 {data['asof_kst'][:16]} KST", "tiny"),
             *([P("외국인 선물 순매수 자료 미확보 · 방향 해석 제한 · 텔레그램 발송 금지", "body")] if incomplete else []),
             P("오늘의 판단", "sub")]
    for name in ("KOSPI", "KOSDAQ"):
        story.append(P(f"{name} | {analyses[name]['headline']}"))
    story.append(P("판단 근거 | 당일 수급", "sub"))
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
    story += [table, P("가능한 설명과 다음 장 검증", "sub")]
    for market, index in (("KOSPI", "KOSPI200"), ("KOSDAQ", "KOSDAQ150")):
        a = analyses[market]
        story += [P(f"{market} / {index}", "sub"),
                  P("관측: " + a["facts"] + ". " + a["futures"]),
                  P("가능한 설명: " + a["hypothesis"]),
                  P("가설 강화: " + a["confirm"]),
                  P("가설 약화: " + a["reject"]),
                  P(a["limitation"], "tiny")]
    story += [P("고점·저점은 당일 수급의 괴리만으로 확정하지 않는다. 프로그램 수급과 투자자별 수급은 분류 축이 달라 합산하지 않는다. 위 조건은 다음 거래일에 확인할 관찰 기준이다.", "tiny"),
              PageBreak(),
              P("옵션 민감도와 관찰 구간", "title"),
              P("KRX 종가·내재변동성·미결제약정으로 계산한 총량 근사치. 매수·매도 포지션의 부호는 알 수 없음.", "tiny")]
    for name in ("KOSPI200", "KOSDAQ150"):
        deriv = data["derivatives"][name]
        levels, gross_delta_bn, total_gamma_bn = gamma_levels(deriv)
        top_strike, top_gamma = levels[0]
        spot = deriv["underlying_close"]
        distance = (top_strike / spot - 1) * 100
        position = "위" if distance > 0 else "아래" if distance < 0 else "동일"
        share = top_gamma / 1e8 / total_gamma_bn * 100 if total_gamma_bn else 0
        other_levels = ", ".join(f"{k:,.2f} ({v/1e8:,.1f}억원/1%)" for k, v in levels[1:]) or "추가 없음"
        story += [P(f"{name} | 기초지수 {spot:,.2f}", "sub"),
                  P(f"최대 총감마 행사가 {top_strike:,.2f}: 현 지수와 {abs(distance):.2f}% {position}. "
                    f"총감마 {top_gamma/1e8:,.1f}억원/지수 1% 변동, 전체 관측치의 {share:.1f}%."),
                  P("그다음 구간: " + other_levels),
                  P(f"총 델타 명목 규모의 절댓값 합 {gross_delta_bn:,.1f}억원. "
                    "이 값으로 순델타, 딜러 순감마, 지지·저항 방향을 정할 수 없음."),
                  P(f"관찰: 다음 장 {top_strike:,.2f} 부근을 통과하거나 재진입할 때 "
                    "옵션 미결제약정·내재변동성 변화와 현물/선물 수급을 함께 확인. "
                    "행사가 자체가 고점·저점이라는 뜻은 아님.")]
    story += [P("해석을 확정하려면", "sub"),
              P("1) 외국인 선물 투자자별 순매수와 2) 전일 대비 옵션 미결제약정 변화, 3) 지수 구성종목별 기여도를 대조한다. "
                "현재 자료는 당일 거래 흐름과 총 민감도만 보여주며 신규 포지션·청산·헤지의 동기를 식별하지 못한다."),
              P("감마·델타는 무이자·무배당 Black-Scholes 근사치이며 동일한 옵션 매수·매도 양쪽의 포지션 부호가 상쇄될 수 있다.", "tiny")]
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

