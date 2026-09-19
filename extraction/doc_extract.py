#!/usr/bin/env python3
"""
doc-extract v2 — đọc JSON cấu trúc của Docling thay vì text layer.

Bản v1 (giữ lại ở doc_extract_pdftotext.py.bak) dựng lại bảng từ `pdftotext
-layout` bằng cách cắt theo VỊ TRÍ KÝ TỰ. Toàn bộ lớp logic đó đã sinh ra
những lỗi sau, tất cả đều im lặng:

  - hai bảng chung một dòng đơn vị -> lấy nhầm header -> lệch nguyên một cột
  - nhãn nhóm căn giữa ("Equity") dùng làm biên cột -> đọc nhầm khối
  - "2024" và "target" cách nhau nhiều khoảng trắng bị ghép thành một cột
  - chú thích dính header ("2024¹" -> "20241") -> mất cả báo cáo, không báo lỗi
  - cột "Anhangangabe" chứa số tham chiếu trông y hệt giá trị

Docling trả về lưới ô có chỉ số hàng/cột, nên cả lớp đó biến mất:
  - mỗi bảng là một đối tượng riêng, không cần đoán ranh giới
  - "Anhangangabe" là MỘT CỘT, không còn lẫn vào dữ liệu
  - "2024 1" giữ nguyên marker chú thích trong ô -> vẫn suy được period_basis
  - header hai tầng (Operational control | Equity) ra đúng hai nhóm cột

Những gì KHÔNG đổi: hợp đồng đầu ra, quy tắc số theo locale, quy ước dấu,
và ánh xạ nhãn -> concept. Docling cho cấu trúc, không cho ngữ nghĩa.
"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import argparse, hashlib, json, pathlib, re, sys
from decimal import Decimal

from parsing import docling_io
from shared.numbers import is_number_token, parse_number as _parse_number
from shared.tables import YEAR_BARE as YEAR_CELL, header_columns

# Ký hiệu tiền tệ -> mã ISO. Shell in "$ million" chứ không in "USD million",
# và schema yêu cầu mã ISO. Fail closed: ký hiệu lạ giữ nguyên để lộ ra ở
# kiểm tra hợp đồng dữ liệu, thay vì đoán bừa.
CURRENCY_SYMBOL = {"$": "USD", "€": "EUR", "£": "GBP",
                   "euros": "EUR", "euro": "EUR", "Euros": "EUR"}

PROFILES = {
 "omv-de": dict(
    decimal_separator=",",   # ô trống và quy ước dấu: xem shared/numbers.py
    scale_re=r"In\s+([A-Z]{3})\s+(Mio|Mrd|Tsd)",
    scale_map={"Tsd": 1_000, "Mio": 1_000_000, "Mrd": 1_000_000_000},
    # Concept mà DẤU TRÌNH BÀY ngược với dấu taxonomy quy định.
    # IFRS định nghĩa IncomeTaxExpenseContinuingOperations là CHI PHÍ DƯƠNG;
    # báo cáo Đức in nó như một khoản trừ (–1.834). Bê nguyên dấu in là sai
    # dấu, và đây chính là trường `sign_rule_applied` trong schema.
    sign_flip={"ifrs-full:IncomeTaxExpenseContinuingOperations"},
    sections=[("Konzern-Gewinn- und Verlustrechnung", "income_statement"),
              ("Konzernbilanz", "balance_sheet"),
              ("Vermögen", "balance_sheet"),
              ("Eigenkapital und Verbindlichkeiten", "balance_sheet"),
              ("Konzern-Cashflow-Rechnung", "cash_flow")],
    labels={
      "Umsatzerlöse": ("ifrs-full:Revenue", "income_statement"),
      "Operatives Ergebnis": ("ifrs-full:ProfitLossFromOperatingActivities", "income_statement"),
      "Ergebnis vor Steuern": ("ifrs-full:ProfitLossBeforeTax", "income_statement"),
      "Steuern vom Einkommen und vom Ertrag": ("ifrs-full:IncomeTaxExpenseContinuingOperations", "income_statement"),
      "Jahresüberschuss": ("ifrs-full:ProfitLoss", "income_statement"),
      "davon den Aktionären des Mutterunternehmens zuzurechnen":
          ("ifrs-full:ProfitLossAttributableToOwnersOfParent", "income_statement"),
      "davon nicht beherrschenden Anteilen zuzurechnen":
          ("ifrs-full:ProfitLossAttributableToNoncontrollingInterests", "income_statement"),
      "Summe Aktiva": ("ifrs-full:Assets", "balance_sheet"),
      "Summe Eigenkapital": ("ifrs-full:Equity", "balance_sheet"),
      "Eigenkapital der Anteilseigner des Mutterunternehmens":
          ("ifrs-full:EquityAttributableToOwnersOfParent", "balance_sheet"),
      "Nicht beherrschende Anteile": ("ifrs-full:NoncontrollingInterests", "balance_sheet"),
      "Summe Passiva": ("ifrs-full:EquityAndLiabilities", "balance_sheet"),
      "Zahlungsmittel und Zahlungsmitteläquivalente": ("ifrs-full:CashAndCashEquivalents", "balance_sheet"),
      "Cashflow aus der Betriebstätigkeit": ("ifrs-full:CashFlowsFromUsedInOperatingActivities", "cash_flow"),
      "Cashflow aus der Investitionstätigkeit": ("ifrs-full:CashFlowsFromUsedInInvestingActivities", "cash_flow"),
      "Cashflow aus der Finanzierungstätigkeit": ("ifrs-full:CashFlowsFromUsedInFinancingActivities", "cash_flow"),
      "Währungsdifferenz auf liquide Mittel":
          ("ifrs-full:EffectOfExchangeRateChangesOnCashAndCashEquivalents", "cash_flow"),
    }),

 "akerbp-en": dict(
    decimal_separator=".",   # ô trống và quy ước dấu: xem shared/numbers.py
    scale_re=r"\(([A-Z]{3})\s+(million|thousand|billion)\)",
    scale_map={"thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000},
    sign_flip=set(),
    sections=[("Income statement", "income_statement"),
              ("Statement of financial position", "balance_sheet"),
              ("Statement of cash flows", "cash_flow")],
    labels={
      "Total income": ("ifrs-full:RevenueAndOperatingIncome", "income_statement"),
      "Total operating expenses": ("ifrs-full:OperatingExpense", "income_statement"),
      "Profit/loss before taxes": ("ifrs-full:ProfitLossBeforeTax", "income_statement"),
      "Net profit/loss": ("ifrs-full:ProfitLoss", "income_statement"),
      "Total assets": ("ifrs-full:Assets", "balance_sheet"),
      "Total non-current assets": ("ifrs-full:NoncurrentAssets", "balance_sheet"),
      "Total current assets": ("ifrs-full:CurrentAssets", "balance_sheet"),
      "Total equity": ("ifrs-full:Equity", "balance_sheet"),
      "Total liabilities": ("ifrs-full:Liabilities", "balance_sheet"),
      "Total non-current liabilities": ("ifrs-full:NoncurrentLiabilities", "balance_sheet"),
      "Total current liabilities": ("ifrs-full:CurrentLiabilities", "balance_sheet"),
      "Total equity and liabilities": ("ifrs-full:EquityAndLiabilities", "balance_sheet"),
      "Net cash flow from operating activities": ("ifrs-full:CashFlowsFromUsedInOperatingActivities", "cash_flow"),
      "Net cash flow from investment activities": ("ifrs-full:CashFlowsFromUsedInInvestingActivities", "cash_flow"),
      "Net cash flow from financing activities": ("ifrs-full:CashFlowsFromUsedInFinancingActivities", "cash_flow"),
      "Net change in cash and cash equivalents":
          ("ifrs-full:IncreaseDecreaseInCashAndCashEquivalentsBeforeEffectOfExchangeRateChanges", "cash_flow"),
      "Cash and cash equivalents": ("ifrs-full:CashAndCashEquivalents", "balance_sheet"),
    }),

 # Shell: ba cột năm (2025/2024/2023) ở KQKD, hai cột ở CĐKT. Đơn vị "$ million"
 # nằm lẫn trong ô tiêu đề cột cuối ("$ million 2023") chứ không đứng riêng.
 "shell-en": dict(
    decimal_separator=".",
    # group(1)=tiền tệ, group(2)=bậc — đúng thứ tự scale_for() mong đợi.
    # Shell in "$ million"; ký hiệu $ được chuẩn hoá về USD ở dưới.
    scale_re=r"(\$)\s*(million|billion)",
    scale_map={"million": 1_000_000, "billion": 1_000_000_000},
    sign_flip=set(),
    sections=[("Consolidated Statement of Income", "income_statement"),
              ("Consolidated Balance Sheet", "balance_sheet"),
              ("Consolidated Statement of Cash Flows", "cash_flow")],
    labels={
      "Revenue": ("ifrs-full:Revenue", "income_statement"),
      "Total expenditure": ("ifrs-full:OperatingExpense", "income_statement"),
      "Income before taxation": ("ifrs-full:ProfitLossBeforeTax", "income_statement"),
      "Taxation charge": ("ifrs-full:IncomeTaxExpenseContinuingOperations", "income_statement"),
      "Income for the period": ("ifrs-full:ProfitLoss", "income_statement"),
      "Income attributable to non-controlling interest":
          ("ifrs-full:ProfitLossAttributableToNoncontrollingInterests", "income_statement"),
      "Income attributable to Shell plc shareholders":
          ("ifrs-full:ProfitLossAttributableToOwnersOfParent", "income_statement"),
      # KHÔNG ánh xạ "Total assets" và "Cash flow from investing activities".
      # Docling gán nhãn lệch dòng ở hai chỗ này trên bản Chrome render:
      #   r20 "Total assets"        -> 107.173  (thật ra là tổng tài sản NGẮN HẠN;
      #                                tổng thật 370.350 không nằm trong bảng)
      #   r27 "Other investing …"   -> (16.811)/(15.155)/(17.734)  (đây mới là
      #                                giá trị của dòng investing activities;
      #                                r28 chỉ còn sót (310) ở một cột)
      # Số đọc đúng, nhưng cặp nhãn↔giá trị sai. compare_to_truth bắt được cả
      # hai. Thà mất fact còn hơn phát ra con số trông hợp lý mà sai gấp 3,5 lần.
      "Total liabilities": ("ifrs-full:Liabilities", "balance_sheet"),
      "Equity attributable to Shell plc shareholders":
          ("ifrs-full:EquityAttributableToOwnersOfParent", "balance_sheet"),
      "Cash and cash equivalents": ("ifrs-full:CashAndCashEquivalents", "balance_sheet"),
      "Cash flow from operating activities":
          ("ifrs-full:CashFlowsFromUsedInOperatingActivities", "cash_flow"),
      "Cash flow from financing activities":
          ("ifrs-full:CashFlowsFromUsedInFinancingActivities", "cash_flow"),
      "Effects of exchange rate changes on cash and cash equivalents":
          ("ifrs-full:EffectOfExchangeRateChangesOnCashAndCashEquivalents", "cash_flow"),
    }),

 # Equinor: tiếng Na Uy, số kiểu Âu (102.502 = 102502) nhưng tiền tệ USD —
 # đúng ca mà locale và currency không đi cùng nhau. Đơn vị khai "i millioner
 # USD", tức BẬC đứng trước TIỀN TỆ, ngược với "In EUR Mio"; resolve_scale()
 # xử lý bằng cách tra scale_map chứ không dựa vào thứ tự nhóm.
 "equinor-nb": dict(
    decimal_separator=",",
    scale_re=r"i\s+(millioner|tusen)\s+([A-Z]{3})",
    scale_map={"tusen": 1_000, "millioner": 1_000_000},
    sign_flip=set(),
    sections=[("Konsolidert oppstilling  over totalresultat", "income_statement"),
              ("Konsernbalanse", "balance_sheet"),
              ("Konsolidert kontantstrømoppstilling", "cash_flow")],
    labels={
      "Sum eiendeler": ("ifrs-full:Assets", "balance_sheet"),
      "Sum anleggsmidler": ("ifrs-full:NoncurrentAssets", "balance_sheet"),
      "Sum omløpsmidler": ("ifrs-full:CurrentAssets", "balance_sheet"),
      "Betalingsmidler": ("ifrs-full:CashAndCashEquivalents", "balance_sheet"),
      "Resultat før skattekostnad": ("ifrs-full:ProfitLossBeforeTax", "cash_flow"),
      "Kontantstrøm fra operasjonelle aktiviteter":
          ("ifrs-full:CashFlowsFromUsedInOperatingActivities", "cash_flow"),
      "Kontantstrøm fra/(benyttet til) investeringsaktiviteter":
          ("ifrs-full:CashFlowsFromUsedInInvestingActivities", "cash_flow"),
    }),

 # Eni: tiếng Ý, số kiểu Âu, EUR. Bảng cân đối xen cột phụ "di cui verso parti
 # correlate" (giao dịch bên liên quan) giữa các cột năm — cột phụ không mang
 # năm nên header_columns bỏ qua, đúng như mong muốn.
 "eni-it": dict(
    decimal_separator=",",
    scale_re=r"(€)\s*(milioni|migliaia)",
    scale_map={"migliaia": 1_000, "milioni": 1_000_000},
    # Ý in chi phí thuế là số âm (3.020); taxonomy quy định dương.
    sign_flip={"ifrs-full:IncomeTaxExpenseContinuingOperations"},
    # Ô năm merge ngang "Totale" + "di cui verso parti correlate"; chỉ cột
    # "Totale" mang giá trị tổng. Thiếu khai này thì mỗi năm ra hai fact.
    value_subheader="Totale",
    sections=[("STATO PATRIMONIALE", "balance_sheet"),
              ("CONTO ECONOMICO", "income_statement"),
              ("RENDICONTO FINANZIARIO", "cash_flow"),
              ("(segue) RENDICONTO FINANZIARIO", "cash_flow")],
    labels={
      "TOTALE ATTIVITÀ": ("ifrs-full:Assets", "balance_sheet"),
      "TOTALE PASSIVITÀ": ("ifrs-full:Liabilities", "balance_sheet"),
      "TOTALE PATRIMONIO NETTO": ("ifrs-full:Equity", "balance_sheet"),
      "TOTALE PASSIVITÀ E PATRIMONIO NETTO": ("ifrs-full:EquityAndLiabilities", "balance_sheet"),
      "Totale patrimonio netto di Eni":
          ("ifrs-full:EquityAttributableToOwnersOfParent", "balance_sheet"),
      "Disponibilità liquide ed equivalenti": ("ifrs-full:CashAndCashEquivalents", "balance_sheet"),
      "Ricavi della gestione caratteristica": ("ifrs-full:Revenue", "income_statement"),
      "UTILE ANTE IMPOSTE": ("ifrs-full:ProfitLossBeforeTax", "income_statement"),
      "Imposte sul reddito":
          ("ifrs-full:IncomeTaxExpenseContinuingOperations", "income_statement"),
      "UTILE DELL'ESERCIZIO": ("ifrs-full:ProfitLoss", "income_statement"),
      "Utile dell'esercizio di competenza Eni":
          ("ifrs-full:ProfitLossAttributableToOwnersOfParent", "income_statement"),
      "Flusso di cassa netto da attività operativa":
          ("ifrs-full:CashFlowsFromUsedInOperatingActivities", "cash_flow"),
      "Flusso di cassa netto da attività di investimento":
          ("ifrs-full:CashFlowsFromUsedInInvestingActivities", "cash_flow"),
      "Flusso di cassa netto da attività di finanziamento":
          ("ifrs-full:CashFlowsFromUsedInFinancingActivities", "cash_flow"),
    }),

 # Repsol: tiếng Tây Ban Nha, số kiểu Âu, EUR. Bản render mất hết tiêu đề báo
 # cáo nên phải khai section theo trang (xem ghi chú ở section_for).
 "repsol-es": dict(
    decimal_separator=",",
    scale_re=r"(Millones|Miles) de (euros)",
    scale_map={"Miles": 1_000, "Millones": 1_000_000},
    sign_flip={"ifrs-full:IncomeTaxExpenseContinuingOperations"},
    sections=[],
    section_by_page={14: "income_statement", 15: "balance_sheet",
                     16: "balance_sheet", 17: "cash_flow"},
    labels={
      # Nhãn giữ NGUYÊN như Docling đọc, kể cả chỗ dính chữ
      # ("RESULTADOANTES DE IMPUESTOS") — sửa cho đẹp là tự làm hụt khớp.
      "Ventas": ("ifrs-full:Revenue", "income_statement"),
      "RESULTADOANTES DE IMPUESTOS": ("ifrs-full:ProfitLossBeforeTax", "income_statement"),
      "Impuesto sobre beneficios":
          ("ifrs-full:IncomeTaxExpenseContinuingOperations", "income_statement"),
      "RESULTADO CONSOLIDADO DELEJERCICIO": ("ifrs-full:ProfitLoss", "income_statement"),
      "RESULTADO TOTALATRIBUIDOALASOCIEDAD DOMINANTE":
          ("ifrs-full:ProfitLossAttributableToOwnersOfParent", "income_statement"),
      "Efectivo y otros activos líquidos equivalentes":
          ("ifrs-full:CashAndCashEquivalents", "balance_sheet"),
      "PATRIMONIO NETO": ("ifrs-full:Equity", "balance_sheet"),
      "PASIVO NO CORRIENTE": ("ifrs-full:NoncurrentLiabilities", "balance_sheet"),
      "PASIVO CORRIENTE": ("ifrs-full:CurrentLiabilities", "balance_sheet"),
      "TOTALPATRIMONIO NETOYPASIVO": ("ifrs-full:EquityAndLiabilities", "balance_sheet"),
      "Resultado antes de impuestos": ("ifrs-full:ProfitLossBeforeTax", "cash_flow"),
      "FLUJOS DE EFECTIVO DE EXPLOTACIÓN":
          ("ifrs-full:CashFlowsFromUsedInOperatingActivities", "cash_flow"),
      "FLUJOS DE EFECTIVO DE INVERSIÓN":
          ("ifrs-full:CashFlowsFromUsedInInvestingActivities", "cash_flow"),
      "FLUJOS DE EFECTIVO DE FINANCIACIÓN":
          ("ifrs-full:CashFlowsFromUsedInFinancingActivities", "cash_flow"),
    }),

 # Galp: tiếng Anh, số kiểu Anh-Mỹ, EUR. Bản render mặc định MẤT HẾT cột số —
 # bảng rộng hơn khổ A4 nên Chrome cắt, chỉ còn cột nhãn và cột Note. Phải
 # render lại khổ 420×297mm (xem README). Nhãn ở đây kết thúc bằng dấu hai
 # chấm ("Total assets:"), giữ nguyên như tài liệu in.
 "galp-en": dict(
    decimal_separator=".",
    scale_re=r"(million|thousand) (Euros)",
    scale_map={"thousand": 1_000, "million": 1_000_000},
    sign_flip=set(),
    sections=[("Consolidated Statement of Financial Position", "balance_sheet"),
              ("Consolidated Income Statement", "income_statement"),
              ("Consolidated Statement of Cash Flows", "cash_flow")],
    labels={
      "Total assets:": ("ifrs-full:Assets", "balance_sheet"),
      "Total non-current assets:": ("ifrs-full:NoncurrentAssets", "balance_sheet"),
      "Total current assets:": ("ifrs-full:CurrentAssets", "balance_sheet"),
      "Total equity:": ("ifrs-full:Equity", "balance_sheet"),
      "Total equity attributable to shareholders:":
          ("ifrs-full:EquityAttributableToOwnersOfParent", "balance_sheet"),
      "Total liabilities:": ("ifrs-full:Liabilities", "balance_sheet"),
      "Total non-current liabilities:": ("ifrs-full:NoncurrentLiabilities", "balance_sheet"),
      "Total current liabilities:": ("ifrs-full:CurrentLiabilities", "balance_sheet"),
      "Total equity and liabilities:": ("ifrs-full:EquityAndLiabilities", "balance_sheet"),
      "Cash and cash equivalents": ("ifrs-full:CashAndCashEquivalents", "balance_sheet"),
      "Sales": ("ifrs-full:Revenue", "income_statement"),
      "Profit/(Loss) before taxes and other contributions:":
          ("ifrs-full:ProfitLossBeforeTax", "income_statement"),
      "Consolidated net income/(loss) for the year": ("ifrs-full:ProfitLoss", "income_statement"),
      "Cash flow from operating activities":
          ("ifrs-full:CashFlowsFromUsedInOperatingActivities", "cash_flow"),
      "Cash flow from investing activities":
          ("ifrs-full:CashFlowsFromUsedInInvestingActivities", "cash_flow"),
      "Cash flow from financing activities":
          ("ifrs-full:CashFlowsFromUsedInFinancingActivities", "cash_flow"),
    }),

 # TotalEnergies: tiếng Anh, USD, ba cột năm. Tiêu đề mục có ĐÁNH SỐ
 # ("8.4 Consolidated balance sheet") nên phải khớp cả phần số.
 #
 # Chrome dồn cả ba báo cáo lên một trang PDF, nên phần đuôi báo cáo kết quả
 # kinh doanh (Income taxes, Consolidated net income) nằm DƯỚI tiêu đề 8.3.
 # Vì thế 8.3 cũng trỏ về income_statement — nhưng KHÔNG khai "TotalEnergies
 # share": trong bảng 8.3 nhãn đó là phần thu nhập TOÀN DIỆN thuộc về công ty
 # mẹ, một con số khác hẳn lợi nhuận thuần. Khai nó vào đây là mời một fact sai
 # trông rất hợp lý.
 "tte-en": dict(
    decimal_separator=".",
    scale_re=r"\((M)(\$)\)",
    scale_map={"M": 1_000_000, "B": 1_000_000_000},
    sign_flip={"ifrs-full:IncomeTaxExpenseContinuingOperations"},
    sections=[("8.2 Consolidated statement of income", "income_statement"),
              ("8.3 Consolidated statement of comprehensive income", "income_statement"),
              ("8.4 Consolidated balance sheet", "balance_sheet"),
              ("8.5 Consolidated statement of cash flow", "cash_flow")],
    labels={
      "Sales": ("ifrs-full:Revenue", "income_statement"),
      "Income taxes": ("ifrs-full:IncomeTaxExpenseContinuingOperations", "income_statement"),
      "Consolidated net income": ("ifrs-full:ProfitLoss", "income_statement"),
      "Total assets": ("ifrs-full:Assets", "balance_sheet"),
      "Total non-current assets": ("ifrs-full:NoncurrentAssets", "balance_sheet"),
      "Total current assets": ("ifrs-full:CurrentAssets", "balance_sheet"),
      "Cash flow from operating activities":
          ("ifrs-full:CashFlowsFromUsedInOperatingActivities", "cash_flow"),
      "Cash flow used in investing activities":
          ("ifrs-full:CashFlowsFromUsedInInvestingActivities", "cash_flow"),
      "Cash flow from/(used in) financing activities":
          ("ifrs-full:CashFlowsFromUsedInFinancingActivities", "cash_flow"),
    }),
}

# Chỉ cắt những gì CHẮC CHẮN là ký hiệu chú thích:
#   - chữ số mũ:        Umsatzerlöse¹
#   - ký hiệu:          Revenue*  ·  Total†
#   - số kèm ngoặc:     Total assets 1)  ·  Emission source/category 1) 2) 3)
#
# KHÔNG cắt chữ số trần ở cuối nhãn. Bản đầu dùng r"\s*[\d¹²³\*†]{1,2}\)?$",
# tức coi mọi chữ số cuối là chú thích, nên:
#     "Revenue 2024"            -> "Revenue 20"
#     "Equity as of 31.12.2022" -> "Equity as of 31.12.20"
# và ba năm 2022 / 2023 / 2024 gộp thành CÙNG một nhãn. Nó không làm chương
# trình dừng — nó lặng lẽ biến nhãn này thành nhãn khác, đúng kiểu hỏng nguy
# hiểm nhất với một bộ benchmark. Đo trên corpus hiện tại: 14 nhãn bị biến dạng,
# và KHÔNG nhãn nào trong LABEL_MAP thực sự cần cắt chú thích — tức quy tắc cũ
# mang toàn bộ rủi ro mà chưa từng mang lại lợi ích nào.
#
# Nguyên tắc: thà bỏ sót một chú thích còn hơn cắt nhầm phần mang nghĩa của nhãn.
# Bỏ sót chỉ làm mất một dòng, và mất dòng thì đếm được; cắt nhầm thì không.
FOOTNOTE_TAIL = re.compile(r"(?:\s*(?:[¹²³⁴⁵⁶⁷⁸⁹⁰]+|[*†‡§]+|\d{1,2}\)))+$")

def norm_label(s):
    """Chuẩn hoá nhãn để so khớp CHÍNH XÁC.

    Khớp bằng startswith là sai: bảng lưu chuyển tiền tệ có
    "Cashflow aus der Betriebstätigkeit exklusive Net-Working-Capital-Positionen"
    đứng TRƯỚC "Cashflow aus der Betriebstätigkeit", nên dòng dài chiếm mất
    concept và trả về 4.494 thay vì 5.215 — sai 14%, mọi con số vẫn hợp lý.
    """
    s = re.sub(r"\s+", " ", (s or "").strip())
    return FOOTNOTE_TAIL.sub("", s)


def squash(s):
    """Bỏ hết dấu cách để so khớp.

    Docling thỉnh thoảng nuốt khoảng trắng: "Summe Aktiva" -> "SummeAktiva",
    "von OMV" -> "vonOMV". Đây là đánh đổi của việc đọc theo ô thay vì theo
    dòng ký tự — bù lại nó cho đúng cấu trúc cột. So khớp bỏ dấu cách là cách
    rẻ nhất để không mất dòng vì một lỗi đánh máy của parser.
    """
    return re.sub(r"\s+", "", norm_label(s)).lower()


# Năm có thể đứng cuối một chuỗi dài hơn: OMV ghi "2024 1" (kèm marker chú
# thích), Aker BP ghi "31.12.2024". Neo vào ĐẦU ô sẽ trượt dạng thứ hai và làm
# mất toàn bộ bảng cân đối — 16 fact thay vì 29, lại là một mất mát im lặng.


def parse_number(tok, prof):
    """Bọc mỏng quanh shared.numbers — văn phạm và danh sách ô trống nằm ở đó.

    Trước đây hàm này tự strip("()") và lstrip dấu, nên "(123", "--123", "1,23,4"
    đều lọt. Giờ dùng chung một bộ đọc fail-closed với esg_extract, và cổng lọc
    `is_number_token` gọi vào đúng hàm này nên hai bên không thể lệch nhau.
    """
    return _parse_number(tok, prof["decimal_separator"])

def _num(d):
    return int(d) if d == d.to_integral_value() else float(d)

def year_columns(grid, value_subheader=None):
    """Bọc mỏng quanh shared.tables.header_columns.

    Ô tiêu đề bên tài chính là NĂM TRẦN (tuỳ chọn kèm ký hiệu chú thích), nên
    bare_year_only=True: "2024)" hay "2024€" bị từ chối làm cột năm.
    Bên ESG dùng cùng hàm này với bare_year_only=False vì ô tiêu đề ở đó là cụm
    từ chứa năm ("Base year (2017)", "2030 target").
    """
    ri, cols = header_columns(grid, bare_year_only=True)
    return ri, dedupe_year_columns(grid, ri, cols, value_subheader)


def dedupe_year_columns(grid, hdr_i, cols, value_subheader=None):
    """Một năm ứng với NHIỀU cột -> phải chọn, hoặc bỏ. Không được lấy cả hai.

    Bảng kết quả kinh doanh của Eni có ô tiêu đề "2024" MERGE ngang hai cột con
    "Totale" và "di cui verso parti correlate" (phần giao dịch với bên liên
    quan). docling_io trải span ra nên grid có "2024" ở cả hai cột, và bản cũ
    phát ra HAI fact Revenue cho cùng năm 2024: 88.797 (đúng) và 2.997 (phần
    bên liên quan). Cả hai đều là số đọc đúng, nên không cổng số học nào bắt
    được — chỉ kiểm tra trùng khoá trong compare_to_truth mới lộ.

    Cách chọn: profile khai `value_subheader` (vd "Totale") để chỉ ra cột con
    nào mang giá trị tổng; hàng ngay dưới hàng tiêu đề chứa các nhãn cột con.
    Không khai, hoặc khai mà không khớp đúng MỘT cột -> bỏ hẳn năm đó.
    Fail closed: thà mất một năm còn hơn phát ra hai con số mâu thuẫn.
    """
    out = [(c.index, c.year, c.marker) for c in cols]
    by_year = {}
    for c in cols:
        by_year.setdefault(c.year, []).append(c)
    if all(len(v) == 1 for v in by_year.values()):
        return out

    sub = grid[hdr_i + 1] if hdr_i is not None and hdr_i + 1 < len(grid) else []
    keep = []
    for year, group in by_year.items():
        if len(group) == 1:
            keep.append(group[0])
            continue
        if not value_subheader:
            continue
        hit = [c for c in group
               if c.index < len(sub) and (sub[c.index] or "").strip() == value_subheader]
        if len(hit) == 1:
            keep.append(hit[0])
    keep.sort(key=lambda c: c.index)
    return [(c.index, c.year, c.marker) for c in keep]


# Khai section theo TRANG, dùng khi bản render mất hẳn tiêu đề báo cáo.
#
# Repsol là ca thật: xhtml qua Chrome ra PDF không còn "Cuenta de pérdidas y
# ganancias" / "Balance de situación" dưới dạng tiêu đề — chúng chỉ còn trong
# mục lục ở trang khác. section_for() trả None, mọi bảng bị bỏ, tài liệu ra 0
# fact. Khai tay là một PHÁT BIỂU về tài liệu, và phát biểu đó được kiểm: mọi
# giá trị vẫn phải khớp xBRL-JSON qua compare_to_truth. Sai trang thì nhãn
# không khớp, hoặc khớp ra số sai và bị bắt ngay.
#
# Chỉ dùng khi section_for() không kết luận được; heading thật luôn thắng.
def section_for(texts, page_no, table_bbox, prof):
    """Tiêu đề mục gần nhất PHÍA TRÊN bảng.

    Docling dùng gốc toạ độ BOTTOMLEFT, nên "phía trên" nghĩa là `t` LỚN HƠN.
    Bản đầu chỉ lọc theo trang rồi lấy tiêu đề khớp CUỐI CÙNG: trang 148 của OMV
    mang cả "Konzern-Gewinn- und Verlustrechnung" lẫn "Konzernbilanz", nên toàn
    bộ báo cáo kết quả kinh doanh bị gán nhầm là bảng cân đối và bị lọc bỏ —
    16 fact thay vì 32, mà không có lỗi nào được báo.
    """
    if not table_bbox:
        return None
    top = table_bbox[1]
    best, best_gap = None, None
    for t in texts:
        if t["page_no"] != page_no or "header" not in t["label"] or not t["bbox"]:
            continue
        stmt = next((s for pat, s in prof["sections"] if t["text"].startswith(pat)), None)
        if stmt is None:
            continue
        gap = t["bbox"][1] - top          # >0 nghĩa là tiêu đề nằm trên bảng
        if gap >= 0 and (best_gap is None or gap < best_gap):
            best, best_gap = stmt, gap
    return best

def resolve_scale(m, prof):
    """Nhóm nào là bậc, nhóm nào là tiền tệ — không phụ thuộc thứ tự trong câu.

    Tiếng Đức/Anh viết tiền tệ trước ("In EUR Mio", "(USD million)"), tiếng Na Uy
    viết bậc trước ("i millioner USD"). Tra scale_map để biết nhóm nào là bậc,
    thay vì bắt mọi profile xoay regex cho khớp thứ tự nhóm cố định.

    Fail closed: không nhóm nào nằm trong scale_map thì trả (None, None) để
    bảng bị bỏ, chứ không đoán.
    """
    a, b = m.group(1), m.group(2)
    if b in prof["scale_map"]:
        return prof["scale_map"][b], a
    if a in prof["scale_map"]:
        return prof["scale_map"][a], b
    return None, None

def scale_for(texts, page_no, prof, grid=None):
    """Hệ số đơn vị. Tìm trong CHÍNH BẢNG trước, rồi mới tới text của trang.

    OMV khai "In EUR Mio" thành một dòng text riêng; Aker BP khai "(USD million)"
    ngay trong ô header của bảng. Chỉ tìm ở texts sẽ trượt Aker BP, rồi code lùi
    về scale=1 và phát ra 16 fact sai đúng 10⁶ — không cổng nào bắt được, vì
    raw × 1 == value vẫn tự nhất quán.
    """
    if grid:
        for row in grid[:4]:
            for cell in row:
                m = re.search(prof["scale_re"], cell or "")
                if m:
                    sc, cu = resolve_scale(m, prof)
                    if sc:
                        return sc, cu, "column_header"
    for t in texts:
        if t["page_no"] != page_no:
            continue
        m = re.search(prof["scale_re"], t["text"])
        if m:
            sc, cu = resolve_scale(m, prof)
            if sc:
                return sc, cu, "statement_header"
    return None, None, "inferred"

def document_scale(texts, tables, prof):
    """Bậc/tiền tệ dùng chung, CHỈ khi cả tài liệu khai đúng một cặp duy nhất.

    Render xhtml sang PDF bằng Chrome phân trang lại theo ý nó, nên caption đơn
    vị có thể rơi sang trang khác với bảng nó mô tả. Shell là ca thật: "$ million"
    nằm ở trang 231, bảng cân đối ở trang 230, và cả bảng bị bỏ — mất 8 fact dù
    số liệu đọc được hoàn hảo.

    Fail closed vẫn được giữ: nếu tài liệu khai từ HAI cặp trở lên (vd vừa "Mio"
    vừa "Tsd") thì trả None, vì lúc đó không suy ra được bảng nào theo bậc nào.
    Trường hợp dùng tới được ghi scale_source="document_uniform" để truy được.
    """
    found = set()
    for t in texts:
        m = re.search(prof["scale_re"], t["text"])
        if m and resolve_scale(m, prof)[0]:
            found.add(resolve_scale(m, prof))
    for tb in tables:
        for row in (tb.get("grid") or [])[:4]:
            for cell in row:
                m = re.search(prof["scale_re"], cell or "")
                if m and resolve_scale(m, prof)[0]:
                    found.add(resolve_scale(m, prof))
    return found.pop() if len(found) == 1 else None

def footnote_basis(texts, page_no, marker):
    if not marker:
        return "audited", None
    for t in texts:
        if t["page_no"] != page_no:
            continue
        s = t["text"].strip()
        # marker phải là token đứng riêng ở đầu dòng, theo sau là dấu cách hoặc
        # dấu câu. startswith("1") trần sẽ khớp cả "1. Jänner 2024" và
        # "100% Scope-1-..." — rồi lấy đoạn đầu tiên gặp làm chú thích.
        m = re.match(rf"{re.escape(marker)}[)\].:]?\s+(?=\S)", s)
        if m and len(s) > len(m.group(0)) + 3:
            note = s[m.end():].strip()
            if re.search(r"Angepass|Anpassung|restated|adjusted", note, re.I):
                return "restated", note[:160]
    return "audited", None

def load_label_map(path):
    """Nạp bảng tên gọi sinh từ iXBRL, thay cho bảng viết tay trong profile.

    Định dạng: {"nhãn in ra": ["ifrs-full:Concept", "statement"]} — cùng hình
    dạng với `labels` trong profile, nên phần còn lại của bộ trích xuất không
    phải biết bảng đến từ đâu.
    """
    d = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    bad = [k for k, v in d.items()
           if not isinstance(v, (list, tuple)) or len(v) not in (2, 3) or ":" not in v[0]]
    if bad:
        sys.exit(f"{path}: {len(bad)} mục sai định dạng, vd {bad[:2]}")
    labels = {k: (v[0], v[1]) for k, v in d.items()}
    # Phần tử thứ ba là quy ước dấu, cũng suy từ iXBRL (thuộc tính sign="-").
    flip = {v[0] for v in d.values() if len(v) == 3 and v[2]}
    return labels, flip


def extract(parsed_path, company_id, profile, label_map=None):
    prof = PROFILES[profile]
    d = docling_io.load(parsed_path)          # DoclingDocument chính tắc
    doc_hash = d["meta"]["source_sha256"]
    run_id = f"doc-extract-docling-{d['meta']['parser_version']}"
    texts = d["texts"]
    if label_map is not None:
        labels, flipset = label_map
    else:
        labels, flipset = prof["labels"], prof.get("sign_flip", set())
    rows, claimed, stats = [], set(), {"table": 0, "hit": 0, "dup": 0}
    doc_scale = document_scale(texts, d["tables"], prof)
    prev_sect, prev_cols = None, None

    for tb in d["tables"]:
        grid, page = tb["grid"], tb["page_no"]
        table_id = f"p{page}-{tb['num_rows']}x{tb['num_cols']}"
        hdr_i, cols = year_columns(grid, prof.get("value_subheader"))
        if not cols:
            continue
        stats["table"] += 1
        sect = section_for(texts, page, tb["bbox"], prof)
        sect_src = "heading"
        if sect is None and prof.get("section_by_page"):
            sect = prof["section_by_page"].get(page)
            sect_src = "profile_page_map"
        # Bảng TIẾP NỐI: Chrome ngắt trang giữa một báo cáo, nên nửa sau rơi
        # xuống trang mới và không còn tiêu đề nào phía trên. TotalEnergies mất
        # cả Income taxes lẫn dòng financing theo cách này; Shell mất Total
        # equity y hệt.
        #
        # Điều kiện kế thừa, cả ba phải đúng cùng lúc:
        #   - bảng ngay TRƯỚC nó (thứ tự tài liệu) đã xác định được báo cáo;
        #   - hai bảng có CÙNG BỘ CỘT NĂM — dấu hiệu là cùng một báo cáo bị
        #     cắt đôi, chứ không phải hai bảng khác nhau tình cờ nằm cạnh;
        #   - trang này không có tiêu đề nào khớp profile (section_for đã trả
        #     None nên điều kiện này tự thoả).
        # Ghi section_source="continuation" để truy được.
        if sect is None and prev_sect and cols and prev_cols == [c[1] for c in cols]:
            sect, sect_src = prev_sect, "continuation"
            stats["cont"] = stats.get("cont", 0) + 1
        if sect is None:
            # KHÔNG biết bảng này thuộc báo cáo nào thì không nhận nhãn của nó.
            # Bản trước để `if sect and stmt != sect` — sect None làm bộ lọc bị
            # bỏ qua HOÀN TOÀN, tức fail-open: một bảng phụ lục khớp nhãn
            # ProfitLoss có thể tranh mất concept của báo cáo kết quả kinh doanh,
            # và ai thắng chỉ phụ thuộc thứ tự bảng trong tài liệu.
            stats["no_section"] = stats.get("no_section", 0) + 1
            prev_sect, prev_cols = None, None
            continue
        prev_sect, prev_cols = sect, [c[1] for c in cols]
        scale, cur, scale_src = scale_for(texts, page, prof, grid)
        if scale is None and doc_scale:
            scale, cur, scale_src = doc_scale[0], doc_scale[1], "document_uniform"
            stats["doc_scale"] = stats.get("doc_scale", 0) + 1
        if scale is None:
            # KHÔNG phát ra fact khi chưa biết đơn vị. Mặc định về 1 là cách
            # sinh lỗi 1000×/10⁶ im lặng nhất — thà mất dòng còn hơn sai bậc.
            stats["no_scale"] = stats.get("no_scale", 0) + 1
            continue
        basis = {c[0]: footnote_basis(texts, page, c[2]) for c in cols}

        for ri in range(hdr_i + 1, len(grid)):
            label = (grid[ri][0] or "").strip()
            nl = norm_label(label)
            key = next((k for k in labels if norm_label(k) == nl), None)
            if key is None:
                sq = squash(label)
                key = next((k for k in labels if squash(k) == sq), None)
            if not key:
                continue
            concept, stmt = labels[key]
            if stmt != sect:
                continue                      # bảng thuộc báo cáo khác -> bỏ
            if (concept, stmt) in claimed:
                stats["dup"] += 1
                continue
            instant = stmt == "balance_sheet"
            emitted = 0
            for ci, yr, marker in cols:
                if ci >= len(grid[ri]):
                    continue
                raw = (grid[ri][ci] or "").strip()
                if not raw or not is_number_token(raw, prof["decimal_separator"]):
                    continue
                val, is_nil = parse_number(raw, prof)
                if val is None and not is_nil:
                    continue
                flipped = concept in flipset
                if flipped and val is not None:
                    val = -val
                pb, note = basis[ci]
                rows.append({
                    # (doc_hash, page_no, table_id, row_idx, col_idx) — đúng như
                    # silver-schema quy định. Thiếu table_id thì hai bảng trên
                    # CÙNG một trang có ô ở cùng (ri, ci) sẽ ra trùng fact_id;
                    # trang 148/149/150 của OMV đều có hai bảng, nên đây là va
                    # chạm chờ sẵn chứ không phải giả thuyết.
                    "fact_id": hashlib.sha256(
                        f"{doc_hash}|{page}|{table_id}|{ri}|{ci}".encode()).hexdigest()[:32],
                    "run_id": run_id, "doc_hash": doc_hash, "company_id": company_id,
                    "statement": stmt, "line_item_reported": label,
                    "line_item_canonical": concept, "canonical_taxonomy": "ifrs-full",
                    "mapping_confidence": 1.0,
                    "period_start": None if instant else f"{yr}-01-01",
                    "period_end": f"{yr}-12-31",
                    "period_duration_months": None if instant else 12,
                    "period_basis": pb, "is_comparative": ci != cols[0][0],
                    "value_raw_text": raw,
                    "value": None if is_nil else _num(val * Decimal(scale)),
                    "declared_precision": -6 if scale == 1_000_000 else None,
                    "scale_multiplier": scale, "scale_source": scale_src,
                    "currency": CURRENCY_SYMBOL.get(cur, cur) or "EUR",
                    "currency_source": scale_src,
                    "decimal_separator": prof["decimal_separator"],
                    "sign_rule_applied": "taxonomy_balance" if flipped else "as_printed",
                    "section_source": sect_src,
                    "is_nil": is_nil,
                    "source_ref": {
                        "page_no": page, "bbox": tb["bbox"],
                        "verbatim_span": raw,
                        "table_id": table_id,
                        "row_idx": ri, "col_idx": ci,
                        "col_header_path": [str(sect or ""), yr + (f" {marker}" if marker else "")],
                        "extraction_path": "native_text",
                    },
                    "groundedness_verified": True,
                    "extraction_confidence": 0.99,
                    "footnote_refs": [marker] if marker else [],
                    "footnote_texts": [note] if note else [],
                    "validation_flags": ["restated"] if pb == "restated" else [],
                    "extractor_version": f"doc-extract@2.0.0-docling",
                    "model_id": f"docling-{d['meta']['parser_version']}",
                    "prompt_hash": "-", "schema_version": "1.0",
                })
                stats["hit"] += 1
                emitted += 1

            # Chỉ chiếm chỗ khi dòng THỰC SỰ ra fact.
            #
            # Bảng cân đối Aker BP có hai dòng cùng nhãn "Cash and cash
            # equivalents": dòng 21 là tiêu đề phụ, mọi ô đều rỗng; dòng 22 mới
            # mang số. Claim trước khi đọc số khiến dòng rỗng giành mất concept
            # rồi dòng có số bị loại là "trùng" — mất trắng 2 fact, và bộ đếm
            # `dup` chỉ đọc như hành vi dedup bình thường nên không ai để ý.
            # compare_to_truth --profile bắt được vì thấy nhãn có khai mà
            # không ra fact nào.
            if emitted:
                claimed.add((concept, stmt))
            else:
                stats["empty"] = stats.get("empty", 0) + 1
    print(f"    [doc-extract v2] {stats['table']} bảng có cột năm, {stats['hit']} fact, "
          f"{stats['dup']} nhãn trùng bị loại, "
          f"{stats.get('empty', 0)} dòng khớp nhãn nhưng không có số, "
          f"{stats.get('doc_scale', 0)} bảng dùng đơn vị suy từ cả tài liệu, "
          f"{stats.get('cont', 0)} bảng tiếp nối kế thừa báo cáo, "
          f"{stats.get('no_section', 0)} bảng bỏ vì không rõ thuộc báo cáo nào, "
          f"{stats.get('no_scale', 0)} bảng bỏ vì không xác định được đơn vị", file=sys.stderr)
    return rows

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--parsed", required=True, help="JSON từ docling_convert.py")
    ap.add_argument("--company-id", required=True)
    ap.add_argument("--profile", required=True, choices=list(PROFILES))
    ap.add_argument("--out", required=True)
    ap.add_argument("--labels", help="bảng tên gọi sinh từ iXBRL (build_label_map.py). "
                                     "Không truyền thì dùng bảng viết tay trong profile.")
    a = ap.parse_args()
    lm = load_label_map(a.labels) if a.labels else None
    rows = extract(a.parsed, a.company_id, a.profile, label_map=lm)
    pathlib.Path(a.out).write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    print(f"{len(rows)} fact -> {a.out}")
