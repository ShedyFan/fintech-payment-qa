# -*- coding: utf-8 -*-
"""
Сборка печатных PDF из Markdown-исходников репозитория.

Конвейер, без внешних установок:
  Markdown  --(этот скрипт)-->  самодостаточный HTML + print-CSS
            --(docs/paged.polyfill.js, Paged.js v0.4.3)-->  постраничная вёрстка
            --(headless Google Chrome, --print-to-pdf)-->     docs/<name>.pdf

Выход:
  docs/test-plan.html / docs/test-plan.pdf   — из test-plan.md
  docs/report.html    / docs/report.pdf      — из REPORT.md
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(REPO, "docs")
STAGE = os.path.join(tempfile.gettempdir(), "qabuild")


def _find_chrome():
    """Первый существующий Chromium-бинарь: Chrome, затем Edge (оба умеют
    --headless --print-to-pdf). Можно переопределить переменной CHROME_BIN."""
    env = os.environ.get("CHROME_BIN")
    if env and os.path.isfile(env):
        return env
    local = os.environ.get("LOCALAPPDATA", "")
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.join(local, r"Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for p in candidates:
        if p and os.path.isfile(p):
            return p
    return candidates[0]  # для сообщения об ошибке в main()


CHROME = _find_chrome()

DATE_HUMAN = "29 августа 2026"
AUTHOR = os.environ.get("PDF_AUTHOR") or "Кирилл Никифоров"

# ----------------------------------------------------------------------------
# Markdown -> HTML (ровно те конструкции, что встречаются в двух исходниках:
# заголовки, GFM-таблицы с <br> в ячейках, огороженный код, цитаты, списки,
# чекбоксы, `код`, **жирный**, *курсив*, --- как разделитель)
# ----------------------------------------------------------------------------

EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000026FF\U00002700-\U000027BF"
    "\U00002B00-\U00002BFF\U0000FE00-\U0000FE0F\U0001F1E6-\U0001F1FF"
    "\u203C\u2049\u24C2]"
)

LIST_RE = re.compile(r"^(?P<indent> *)(?P<marker>[-*+]|\d+[.)])\s+(?P<rest>.*)$")


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline(text):
    t = esc(text)
    t = re.sub(r"&lt;br\s*/?&gt;", "<br>", t)          # <br> в ячейках таблиц
    stash = []
    def _stash(m):
        stash.append(m.group(1))
        return "\x00%d\x00" % (len(stash) - 1)
    t = re.sub(r"`([^`]+)`", _stash, t)                # защитить код-спаны
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", t)
    t = re.sub(r"\x00(\d+)\x00", lambda m: "<code>%s</code>" % stash[int(m.group(1))], t)
    return t


def is_table_sep(line):
    s = line.strip()
    return "|" in s and "-" in s and set(s) <= set("|:- ")


def split_row(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def render_list(lines, i):
    m0 = LIST_RE.match(lines[i])
    base = len(m0.group("indent"))
    top_ordered = m0.group("marker")[0].isdigit()
    root = []
    stack = [(base, top_ordered, root)]

    while i < len(lines):
        ln = lines[i]
        if ln.strip() == "":
            j = i + 1
            nxt = LIST_RE.match(lines[j]) if j < len(lines) else None
            if nxt and len(nxt.group("indent")) >= base:
                i = j
                ln = lines[i]
            else:
                break
        m = LIST_RE.match(ln)
        if not m:
            if ln.startswith(" " * (base + 2)) and stack[-1][2]:
                stack[-1][2][-1]["lines"].append(ln.strip())
                i += 1
                continue
            break
        ind = len(m.group("indent"))
        ordered = m.group("marker")[0].isdigit()
        while len(stack) > 1 and ind < stack[-1][0]:
            stack.pop()
        if ind > stack[-1][0]:
            kids = []
            stack[-1][2][-1]["children"].append((ordered, kids))
            stack.append((ind, ordered, kids))
        stack[-1][2].append({"lines": [m.group("rest")], "children": []})
        i += 1

    def emit(ordered, items):
        tag = "ol" if ordered else "ul"
        out = ["<%s>" % tag]
        for it in items:
            txt = " ".join(it["lines"]).strip()
            tm = re.match(r"^\[([ xX])\]\s+(.*)$", txt)
            if tm:
                on = " on" if tm.group(1) != " " else ""
                body = '<span class="box%s"></span> %s' % (on, inline(tm.group(2)))
                li_open = '<li class="task">'
            else:
                body = inline(txt)
                li_open = "<li>"
            kids = "".join(emit(o, its) for (o, its) in it["children"])
            out.append("%s%s%s</li>" % (li_open, body, kids))
        out.append("</%s>" % tag)
        return "".join(out)

    return emit(top_ordered, root), i


def md_to_html(src, hid):
    """hid: изменяемый [next_int]; возвращает (html, headings[(level,text,id)])."""
    lines = src.replace("\r\n", "\n").split("\n")
    html = []
    heads = []
    i, n = 0, len(lines)

    while i < n:
        ln = lines[i]

        if ln.strip() == "":
            i += 1
            continue

        m = re.match(r"^\s*```+(.*)$", ln)
        if m:
            buf = []
            i += 1
            while i < n and not re.match(r"^\s*```+\s*$", lines[i]):
                buf.append(lines[i])
                i += 1
            i += 1
            html.append("<pre><code>%s</code></pre>" % esc("\n".join(buf)))
            continue

        m = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", ln)
        if m:
            lvl = len(m.group(1))
            txt = m.group(2).strip()
            hid[0] += 1
            hid_s = "sec%d" % hid[0]
            heads.append((lvl, txt, hid_s))
            html.append('\n<h%d id="%s">%s</h%d>' % (lvl, hid_s, inline(txt), lvl))
            i += 1
            continue

        if re.match(r"^-{3,}\s*$", ln) or re.match(r"^\*{3,}\s*$", ln) or re.match(r"^_{3,}\s*$", ln):
            html.append("<hr>")
            i += 1
            continue

        if "|" in ln and i + 1 < n and is_table_sep(lines[i + 1]):
            header = split_row(ln)
            i += 2
            body = []
            while i < n and lines[i].strip() != "" and "|" in lines[i]:
                body.append(split_row(lines[i]))
                i += 1
            ncol = len(header)
            # широкие таблицы сценариев (ID/Описание/Шаги/Ожидаемый результат/Приоритет)
            # печатаются с фиксированной раскладкой — иначе Paged.js не режет их по страницам
            grid = ""
            colgroup = ""
            if ncol == 5:
                grid = ' class="grid"'
                colgroup = ("<colgroup><col style='width:8%'><col style='width:16%'>"
                            "<col style='width:40%'><col style='width:29%'>"
                            "<col style='width:7%'></colgroup>")
            out = ["\n<table%s>%s<thead><tr>" % (grid, colgroup)]
            out += ["<th>%s</th>" % inline(c) for c in header]
            out.append("</tr></thead><tbody>")
            for row in body:
                if len(row) < len(header):
                    row = row + [""] * (len(header) - len(row))
                out.append("<tr>" + "".join("<td>%s</td>" % inline(c) for c in row) + "</tr>")
            out.append("</tbody></table>")
            html.append("".join(out))
            continue

        if ln.lstrip().startswith(">"):
            buf = []
            while i < n and (lines[i].lstrip().startswith(">") or
                             (lines[i].strip() == "" and i + 1 < n and lines[i + 1].lstrip().startswith(">"))):
                s = re.sub(r"^>\s?", "", lines[i].lstrip())
                buf.append(s)
                i += 1
            inner, _ = md_to_html("\n".join(buf), hid)
            # заголовки внутри цитаты (это цитата чужого ответа, не раздел документа)
            # понижаем до жирного абзаца, чтобы они не попадали в колонтитул и оглавление
            inner = re.sub(r'<h[1-6][^>]*>(.*?)</h[1-6]>', r'<p class="qhead"><strong>\1</strong></p>', inner)
            html.append("\n<blockquote>%s</blockquote>" % inner)
            continue

        if LIST_RE.match(ln):
            frag, i = render_list(lines, i)
            html.append("\n" + frag)
            continue

        buf = [ln]
        i += 1
        while i < n:
            s = lines[i]
            if (s.strip() == "" or re.match(r"^#{1,6}\s", s) or re.match(r"^\s*```+", s)
                    or LIST_RE.match(s) or s.lstrip().startswith(">")
                    or re.match(r"^-{3,}\s*$", s)
                    or ("|" in s and i + 1 < n and is_table_sep(lines[i + 1]))):
                break
            buf.append(s)
            i += 1
        html.append("\n<p>%s</p>" % inline(" ".join(x.strip() for x in buf)))

    return "".join(html), heads


# ----------------------------------------------------------------------------
# Шаблон: обложка + оглавление + резюме + тело; постранично режет Paged.js
# ----------------------------------------------------------------------------

CSS = r"""
:root{
  --accent:#1b4965; --accent-2:#2b6a86;
  --ink:#1c1c1c; --muted:#5b6570; --rule:#c9d2da; --tint:#eef3f7;
}
*{box-sizing:border-box;}
html{-webkit-print-color-adjust:exact;print-color-adjust:exact;}
body{margin:0;color:var(--ink);font-family:Georgia,"DejaVu Serif","Times New Roman",serif;
     font-size:10.5pt;line-height:1.46;}

@page{
  size:A4; margin:20mm 18mm 18mm 18mm;
  @top-left{content:"__RUNTITLE__";font:8pt Georgia,serif;color:#8a949e;}
  @top-right{content:string(docsect);font:8pt Georgia,serif;color:#8a949e;}
  @bottom-center{content:counter(page) " / " counter(pages);font:8.5pt Georgia,serif;color:var(--accent);}
}
@page :first{
  @top-left{content:none} @top-right{content:none} @bottom-center{content:none}
}

h1,h2,h3,h4{font-family:"Segoe UI",system-ui,"DejaVu Sans",Arial,sans-serif;color:var(--accent);
            line-height:1.24;font-weight:600;}
h2{font-size:15pt;margin:0 0 11pt;padding-bottom:3pt;border-bottom:1.5pt solid var(--accent);
   string-set:docsect content(text);break-after:avoid;}
h3{font-size:11.5pt;margin:15pt 0 5pt;color:var(--accent-2);break-after:avoid;}
h4{font-size:10.5pt;margin:12pt 0 4pt;color:var(--accent-2);break-after:avoid;}
__SECTIONBREAK__
p{margin:0 0 7pt;orphans:2;widows:2;}
strong{font-weight:700;}
a{color:inherit;text-decoration:none;}

code{font-family:Consolas,"DejaVu Sans Mono",monospace;font-size:.86em;background:var(--tint);
     padding:.03em .3em;border-radius:2px;}
pre{background:var(--tint);border:.75pt solid var(--rule);border-left:3pt solid var(--accent);
    padding:7pt 9pt;margin:8pt 0;font-family:Consolas,"DejaVu Sans Mono",monospace;
    font-size:8.4pt;line-height:1.4;white-space:pre-wrap;word-wrap:break-word;break-inside:avoid;}
pre code{background:none;padding:0;font-size:inherit;}

blockquote{margin:8pt 0;padding:2pt 0 2pt 12pt;border-left:3pt solid var(--rule);color:#43474c;}
blockquote p{margin:4pt 0;}
p.qhead{margin:6pt 0 2pt;color:var(--accent-2);}

ul,ol{margin:6pt 0;padding-left:18pt;}
li{margin:3pt 0;}
li.task{list-style:none;margin-left:-18pt;padding-left:18pt;}
li.task .box{display:inline-block;width:9pt;height:9pt;border:1pt solid var(--accent);
             vertical-align:-1pt;margin-right:6pt;}
li.task .box.on{background:var(--accent);}

hr{border:0;border-top:.75pt solid var(--rule);margin:14pt 0;}

table{width:100%;border-collapse:collapse;margin:8pt 0 12pt;font-size:8.7pt;line-height:1.32;}
table.grid{table-layout:fixed;}
table.grid td{overflow-wrap:anywhere;word-break:break-word;}
thead{display:table-header-group;break-after:avoid;}
th,td{border:.75pt solid var(--rule);padding:4pt 6pt;text-align:left;vertical-align:top;}
th{background:var(--accent);color:#fff;font-family:"Segoe UI",system-ui,sans-serif;font-weight:600;font-size:8.4pt;}
tbody tr:nth-child(even){background:var(--tint);}
tr{break-inside:avoid;}
tbody tr:first-child{break-before:avoid;}

/* Обложка */
section.cover{height:245mm;display:flex;flex-direction:column;justify-content:center;break-after:page;}
.cover .kicker{font-family:"Segoe UI",system-ui,sans-serif;font-size:9pt;letter-spacing:.14em;
               text-transform:uppercase;color:var(--muted);margin-bottom:9mm;}
.cover h1{font-size:29pt;line-height:1.14;margin:0;color:var(--accent);}
.cover .sub{font-family:"Segoe UI",system-ui,sans-serif;font-size:12pt;color:var(--ink);
            margin-top:6mm;line-height:1.4;}
.cover hr{border:0;border-top:2pt solid var(--accent);margin:12mm 0;width:55mm;}
.cover dl{display:grid;grid-template-columns:26mm 1fr;row-gap:3mm;margin:0;
          font-family:"Segoe UI",system-ui,sans-serif;font-size:10.5pt;}
.cover dt{color:var(--muted);}
.cover dd{margin:0;}

/* Оглавление */
section.toc-page{break-after:page;}
h2.plain{string-set:docsect content(text);}
ol.toc{list-style:none;padding:0;margin:10pt 0 0;font-family:"Segoe UI",system-ui,sans-serif;}
ol.toc li{display:flex;align-items:baseline;margin:5pt 0;}
ol.toc li.sub{margin-left:9mm;font-size:9.4pt;color:#33404a;}
ol.toc .t{white-space:nowrap;}
ol.toc .fill{flex:1 1 auto;border-bottom:1px dotted #a7b4bd;margin:0 5px;position:relative;top:-3px;}
ol.toc .p::after{content:target-counter(attr(data-ref url), page);color:var(--muted);
                 font-variant-numeric:tabular-nums;}

section.summary{break-after:page;}
"""

PAGE = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>{css}</style>
</head>
<body>

<section class="cover">
  <div class="kicker">{kicker}</div>
  <h1>{title}</h1>
  <div class="sub">{subtitle}</div>
  <hr>
  <dl>
    <dt>Дата</dt><dd>{date}</dd>
    <dt>Автор</dt><dd>{author}</dd>
    <dt>Источник</dt><dd>{source}</dd>
  </dl>
</section>

<section class="toc-page">
  <h2 class="plain">Оглавление</h2>
  <ol class="toc">{toc}</ol>
</section>

<section class="summary">
  <h2 class="plain" id="sec-summary">Краткое резюме</h2>
  {summary}
</section>

<main class="content">
{body}
</main>

<script>
  /* Paged.js уступает управление между страницами через requestAnimationFrame.
     В headless Chrome с --virtual-time-budget rAF-цикл не удерживает виртуальные
     часы, и вёрстка обрывается на 2-3-й странице. Переводим rAF на setTimeout —
     такие задачи headless дожидается до конца. */
  window.requestAnimationFrame = function (cb) {{ return setTimeout(function () {{ cb(Date.now()); }}, 0); }};
  window.cancelAnimationFrame = function (id) {{ clearTimeout(id); }};
</script>
<script src="paged.polyfill.js"></script>
</body>
</html>
"""


def build_toc(heads, depth):
    rows = ['<li><span class="t">Краткое резюме</span><span class="fill"></span>'
            '<span class="p" data-ref="#sec-summary"></span></li>']
    for lvl, txt, hid_s in heads:
        if lvl < 2 or lvl > depth:
            continue
        cls = ' class="sub"' if lvl >= 3 else ""
        rows.append('<li%s><span class="t">%s</span><span class="fill"></span>'
                    '<span class="p" data-ref="#%s"></span></li>' % (cls, inline(txt), hid_s))
    return "".join(rows)


def make_html(spec):
    raw = open(os.path.join(REPO, spec["src"]), encoding="utf-8").read()
    raw = EMOJI.sub("", raw)

    mm = re.search(r"(?m)^## ", raw)
    body_md = raw[mm.start():] if mm else raw

    hid = [0]
    body_html, heads = md_to_html(body_md, hid)
    summary_html, _ = md_to_html(spec["summary"], [10000])
    toc = build_toc(heads, spec.get("toc_depth", 2))

    css = CSS.replace("__RUNTITLE__", spec["title"])
    css = css.replace("__SECTIONBREAK__",
                      ".content > h2{break-before:page;}" if spec.get("section_page_break") else "")
    return PAGE.format(
        css=css, title=spec["title"], kicker=spec["kicker"], subtitle=spec["subtitle"],
        date=DATE_HUMAN, author=AUTHOR, source=spec["src"],
        toc=toc, summary=summary_html, body=body_html,
    )


def render_pdf(name, html):
    if os.path.isdir(STAGE):
        shutil.rmtree(STAGE, ignore_errors=True)
    os.makedirs(STAGE, exist_ok=True)

    open(os.path.join(DOCS, name + ".html"), "w", encoding="utf-8", newline="\n").write(html)
    open(os.path.join(STAGE, name + ".html"), "w", encoding="utf-8", newline="\n").write(html)
    shutil.copyfile(os.path.join(DOCS, "paged.polyfill.js"), os.path.join(STAGE, "paged.polyfill.js"))

    out_pdf = os.path.join(STAGE, name + ".pdf")
    cmd = [
        CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
        "--run-all-compositor-stages-before-draw", "--virtual-time-budget=180000",
        "--user-data-dir=" + os.path.join(STAGE, "cp-" + name),
        "--print-to-pdf=" + out_pdf,
        os.path.join(STAGE, name + ".html"),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if not os.path.isfile(out_pdf) or open(out_pdf, "rb").read(5) != b"%PDF-":
        sys.stderr.write((r.stdout or "") + "\n" + (r.stderr or "") + "\n")
        raise SystemExit("Chrome не создал корректный PDF для %s" % name)

    shutil.copyfile(out_pdf, os.path.join(DOCS, name + ".pdf"))
    size = os.path.getsize(os.path.join(DOCS, name + ".pdf"))
    print("OK  %-11s ->  docs/%s.pdf  (%d bytes)" % (name, name, size))


DOCS_SPEC = [
    {
        "src": "test-plan.md",
        "name": "test-plan",
        "title": "Тест-план платёжных сценариев",
        "kicker": "QA · Платёжные сценарии финтех-продукта",
        "subtitle": "Переводы и лимиты · Карты и отмена операции · Комиссии и округление",
        "toc_depth": 2,
        "section_page_break": True,
        "summary": (
            "**Предмет.** Тест-план платёжных сценариев финтех-продукта по трём областям: "
            "переводы и лимиты, карты и отмена операции, комиссии и округление. Области 1–3 — "
            "параметрический стенд (проверка готовности сценариев к исполнению); Область 4 "
            "(APP-001…014) — исполняемые проверки против продукта `app/`.\n\n"
            "**Объём.** 136 формальных сценариев в трёх областях, 55 находок независимой "
            "проверки и сквозной чек-лист денежных границ.\n\n"
            "| Блок | Диапазон ID | Позиций |\n"
            "| --- | --- | --- |\n"
            "| Область 1. Переводы и лимиты | TR-001 … TR-044 | 44 |\n"
            "| Область 2. Карты и отмена операции | CRD-001 … CRD-044 | 44 |\n"
            "| Область 3. Комиссии, округление, граничные значения | FEE-001 … FEE-048 | 48 |\n"
            "| Находки агента-скептика | SK-01 … SK-55 | 55 |\n"
            "| Граничные значения в деньгах | чек-лист | 6 |\n\n"
            "**Формат сценария.** Каждая строка области — идентификатор, описание, шаги, "
            "ожидаемый результат как проверяемый оракул и приоритет. В конце каждой области — "
            "список открытых вопросов: где не хватает значения параметра или бизнес-правила.\n\n"
            "**Находки агента-скептика.** Отдельная роль, не участвовавшая в составлении "
            "чек-листов: перечисляет не покрытое, а не подтверждает полноту. Находки "
            "отсортированы по критичности — блокирующие, критические, высокие, средние — и "
            "завершаются сквозными замечаниями по методологии: гонки на общих счётчиках, "
            "компенсация отката, границы времени, семантика идемпотентного ключа."
        ),
    },
    {
        "src": "REPORT.md",
        "name": "report",
        "title": "Отчёт по ДЗ №2",
        "kicker": "QA · Домашнее задание №2 · вариант A4",
        "subtitle": "Платёжные сценарии: сборка, независимая проверка, устойчивость к инъекциям",
        "toc_depth": 3,
        "summary": (
            "**Что это.** Отчёт по домашнему заданию №2 (вариант A4): платёжный кабинет `app/` "
            "как система под тестом, тест-план против него и по домену, независимая проверка "
            "полноты и попытка скомпрометировать собственную работу.\n\n"
            "**Структура.** Десять разделов по пунктам задания плюс «Честные тупики» и "
            "«Инструменты».\n\n"
            "| Раздел | Тема | Кратко |\n"
            "| --- | --- | --- |\n"
            "| 1 | Работающий результат | `test-plan.md`: Области 1–3 (136 параметрических) + Область 4 (APP-001…014 против `app/`), находки скептика, чек-лист денег |\n"
            "| 2 | Агенты параллельно | реальный параллельный батч из трёх субагентов (диагностика BUG-02/03/04); ранняя формулировка про параллельное авторство областей снята |\n"
            "| 3 | Workflow | `qa-regression-workflow.md` прогонялся дважды, с отклонениями |\n"
            "| 4 | Worktrees | три ветки по областям, три merge в `main`; рабочие копии не удалены |\n"
            "| 5 | Изоляция | песочница отклоняет запись за пределы каталога — зафиксированы команды и коды возврата |\n"
            "| 6 | Инъекция | три способа внедрения скрытой инструкции на двух моделях; ни одна инструкцию не выполнила |\n"
            "| 7 | Оптимизатор / индекс | `rtk` и `claude-mem` проверены вживую; честный открытый вопрос по хуку `rtk` |\n"
            "| 8 | Замеры параллельно/последовательно | проведены; чистого числа нет, есть содержательные находки |\n"
            "| 9 | Сравнение наивного и спекового прогонов | наивный шире и быстрее, но молча выбрал масштаб и допущения; дефектов не нашёл |\n"
            "| 10 | Расхождения | отдельный список «сказал готово — проверка опровергла» |\n\n"
            "**Тон.** Фиксируются и удачи, и осечки: отклонения от workflow, неубранные "
            "worktrees, непочиненные BUG-02/03/04, аудит только одной моделью. Раздел «Честные "
            "тупики» собирает все промахи, включая мелкие."
        ),
    },
]


def main():
    if not os.path.isfile(CHROME):
        raise SystemExit("Не найден Chrome: %s" % CHROME)
    for spec in DOCS_SPEC:
        render_pdf(spec["name"], make_html(spec))


if __name__ == "__main__":
    main()
