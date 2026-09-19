#!/usr/bin/env python3
"""Xuất bộ ôn AI_engineer ra PDF.

Dùng:  python3 export-pdf.py        (chạy từ thư mục này)
Yêu cầu: pip install --user markdown pygments  +  Google Chrome.
Sửa .md xong chạy lại là ra PDF mới.
"""
import re, sys, pathlib, markdown
from pygments.formatters import HtmlFormatter

CSS_TMPL = """
@page { size: A4; margin: 17mm 15mm 16mm 15mm; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body {
  font-family: -apple-system, "SF Pro Text", "Helvetica Neue", Helvetica, Arial, sans-serif;
  font-size: 10pt; line-height: 1.52; color: #16181d; margin: 0;
}
h1, h2, h3, h4 { line-height: 1.25; break-after: avoid; page-break-after: avoid; margin: 0 0 .45em; }
h1 { font-size: 19pt; font-weight: 800; letter-spacing: -.01em; margin-top: 0; padding-bottom: .22em;
     border-bottom: 2.2pt solid #16181d; }
%%H1BREAK%%
h2 { font-size: 13.5pt; font-weight: 750; margin-top: 1.5em; padding-bottom: .16em;
     border-bottom: .6pt solid #c9ced6; }
%%H2BREAK%%
h3 { font-size: 11pt; font-weight: 700; margin-top: 1.25em; color: #23262d; }
h4 { font-size: 10pt; font-weight: 700; margin-top: 1em; }
p { margin: .42em 0 .62em; orphans: 2; widows: 2; }
strong { font-weight: 700; }
ul, ol { margin: .35em 0 .7em; padding-left: 1.5em; }
li { margin: .16em 0; }
li > ul, li > ol { margin: .12em 0 .2em; }
a { color: #16181d; text-decoration: none; border-bottom: .4pt dotted #9aa1ac; }
hr { border: none; border-top: .6pt solid #d7dbe0; margin: 1.5em 0; }
blockquote {
  margin: .7em 0; padding: .45em .85em; border-left: 2.6pt solid #b3bac4;
  background: #f7f8fa; color: #3a3f48;
}
blockquote p { margin: .22em 0; }
code, kbd {
  font-family: "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace;
  font-size: 8.9pt; background: #eef0f3; padding: .8pt 3pt; border-radius: 2.5pt;
  border: .4pt solid #dfe3e8; white-space: pre-wrap;
}
pre {
  background: #f7f8fa; border: .6pt solid #dfe3e8; border-radius: 3.5pt;
  padding: 7pt 9pt; margin: .65em 0; overflow: visible;
  white-space: pre-wrap; word-break: normal; overflow-wrap: anywhere;
  break-inside: avoid-page; page-break-inside: avoid;
}
pre code { background: none; border: none; padding: 0; font-size: 8.3pt; line-height: 1.42; }
table {
  width: 100%; border-collapse: collapse; margin: .7em 0; font-size: 8.8pt;
  break-inside: auto; page-break-inside: auto;
}
thead { display: table-header-group; }
tr { break-inside: avoid; page-break-inside: avoid; }
th, td { border: .5pt solid #ccd2da; padding: 3.6pt 5pt; text-align: left; vertical-align: top; }
th { background: #eceff3; font-weight: 700; }
td code, th code { font-size: 8.1pt; }
img { max-width: 100%; }
.footer-note { margin-top: 2.2em; padding-top: .5em; border-top: .6pt solid #d7dbe0;
               font-size: 8pt; color: #6b7280; }
.cover { break-after: page; page-break-after: always; padding-top: 22mm; }
.cover h1 { border: none; font-size: 23pt; margin-bottom: .3em; }
.cover .sub { font-size: 12pt; color: #4b515a; margin-bottom: 2.2em; line-height: 1.5; }
.cover .meta { font-size: 9.5pt; color: #6b7280; }
.cover table { margin-top: 1.4em; font-size: 9pt; width: 99%; }
"""

H1_BREAK = "h1 { break-before: page; page-break-before: always; }\nh1:first-of-type { break-before: auto; page-break-before: auto; }"
H2_BREAK = "h2 { break-before: page; page-break-before: always; }"


def convert(md_text: str, break_h1=True, break_h2=False) -> str:
    html = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "codehilite", "sane_lists", "attr_list", "md_in_html"],
        extension_configs={"codehilite": {"guess_lang": False, "noclasses": False}},
    )
    css = CSS_TMPL.replace("%%H1BREAK%%", H1_BREAK if break_h1 else "")
    css = css.replace("%%H2BREAK%%", H2_BREAK if break_h2 else "")
    pyg = HtmlFormatter(style="friendly").get_style_defs(".codehilite")
    pyg += "\n.codehilite { background: #f7f8fa !important; }\n.codehilite pre { margin: 0; border: none; background: none; }\n"
    return (
        '<!doctype html><html lang="vi"><head><meta charset="utf-8">'
        f"<style>{css}\n{pyg}</style></head><body>{html}</body></html>"
    )


D = pathlib.Path(__file__).resolve().parent
SP = D

COVER = """<div class="cover">
<h1>Ph&#7887;ng v&#7845;n CDC Global<br>12 c&#226;u &amp; &#273;&#225;p &#225;n</h1>
<div class="sub">Nguyen Ngoc Minh Thy &middot; 25/08/2026<br>
V&#7883; tr&#237;: Senior AI / LLM Engineer</div>
<div class="meta">
<table>
<thead><tr><th>Nh&#243;m c&#226;u</th><th>N&#7897;i dung</th></tr></thead>
<tbody>
<tr><td><b>1&ndash;3</b></td><td>Ch&#7847;n &#273;o&#225;n RAG: recall@k cao m&#224; sai &middot; abstain khi context r&#7895;ng &middot; invalidate khi schema &#273;&#7893;i</td></tr>
<tr><td><b>4, 12</b></td><td>Guardrail cho agent: quy&#7873;n g&#7885;i API &middot; ch&#7885;n sai tool trong 10 tool</td></tr>
<tr><td><b>5&ndash;6</b></td><td>LLM-as-judge: gap 95% judge vs 60% user &middot; c&#417; ch&#7871; x&#7917; l&#253; b&#7845;t &#273;&#7891;ng</td></tr>
<tr><td><b>7&ndash;10</b></td><td>D&#7921; &#225;n Fabrion: model theo vai tr&#242; &middot; LangChain vs t&#7921; vi&#7871;t &middot; 0.14 &rarr; 0.93 &middot; 7 scorer</td></tr>
<tr><td><b>11</b></td><td>Case study: isolation cho 100 kh&#225;ch h&#224;ng</td></tr>
</tbody></table>
</div>
</div>

"""

def build(md_files, out_html, break_h2=False, cover=""):
    parts = [cover] if cover else []
    for f in md_files:
        parts.append((D / f).read_text().rstrip() + "\n")
    html = convert("\n\n".join(parts), break_h1=True, break_h2=break_h2)
    (SP / out_html).write_text(html, encoding="utf-8")
    return SP / out_html

build(["07-cdc-global-2026-08-25.md"], "out-07.html", break_h2=True, cover=COVER)

COVER_RAG = """<div class="cover">
<h1>Advanced RAG / Agent<br>Interview Q&amp;A</h1>
<div class="sub">Nguyen Ngoc Minh Thy &middot; 2026<br>
DataXight Prep &middot; b&#225;m theo NL-to-SQL Agent / LAAF (Fabrion)</div>
<div class="meta">
<table>
<thead><tr><th>Nh&#243;m c&#226;u</th><th>N&#7897;i dung</th></tr></thead>
<tbody>
<tr><td><b>1&ndash;3</b></td><td>Ch&#7847;n &#273;o&#225;n RAG: recall@k cao m&#224; sai &middot; abstain khi context r&#7895;ng &middot; invalidate khi schema &#273;&#7893;i</td></tr>
<tr><td><b>4, 12</b></td><td>Guardrail cho agent: quy&#7873;n g&#7885;i API &middot; ch&#7885;n sai tool trong 10 tools</td></tr>
<tr><td><b>5&ndash;6</b></td><td>LLM-as-judge: gap 95% judge vs 60% user &middot; c&#417; ch&#7871; x&#7917; l&#253; b&#7845;t &#273;&#7891;ng</td></tr>
<tr><td><b>7&ndash;10</b></td><td>D&#7921; &#225;n Fabrion: model routing &middot; LangChain vs t&#7921; vi&#7871;t &middot; 0.14 &rarr; 0.93 &middot; 7 deterministic score</td></tr>
<tr><td><b>11</b></td><td>Case study: isolation cho 100 kh&#225;ch h&#224;ng</td></tr>
</tbody></table>
<p style="margin-top:1.4em"><b>Ghi ch&#250;:</b> c&#225;c ch&#7895; &#273;&#225;nh d&#7845;u <code>[&#272;I&#7872;N]</code> l&#224; s&#7889; li&#7879;u th&#7853;t c&#7847;n b&#7893; sung t&#7915; project.</p>
</div>
</div>

"""

build(["RAG_Agent_Advanced_QnA.md"], "out-rag.html", break_h2=True, cover=COVER_RAG)


# ---------------------------------------------------------------- render PDF
import os, shutil, subprocess, tempfile

CHROME = next((p for p in [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    shutil.which("google-chrome") or "", shutil.which("chromium") or "",
] if p and os.path.exists(p)), None)

JOBS = [("out-07.html",  "07-cdc-global-2026-08-25.md.pdf"),
        ("out-rag.html", "RAG_Agent_Advanced_QnA.md.pdf")]

if CHROME is None:
    raise SystemExit("Kh\u00f4ng t\u00ecm th\u1ea5y Chrome \u2014 HTML \u0111\u00e3 t\u1ea1o, t\u1ef1 m\u1edf r\u1ed3i Print to PDF.")

tmp = pathlib.Path(tempfile.mkdtemp())
for html, pdf in JOBS:
    s = tmp / html
    shutil.move(str(D / html), s)
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
                    "--no-pdf-header-footer", "--virtual-time-budget=8000",
                    "--run-all-compositor-stages-before-draw",
                    f"--print-to-pdf={D / pdf}", s.as_uri()],
                   check=True, capture_output=True)
    print(f"  {pdf:<40} {(D / pdf).stat().st_size // 1024} KB")
shutil.rmtree(tmp, ignore_errors=True)
print("Xong.")
