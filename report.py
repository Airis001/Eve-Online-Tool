"""取得結果とスキル判定から、ブラウザで見る HTML レポートを生成する。"""

import datetime as dt
from html import escape

from paths import DATA_DIR
from skill_check import format_local, format_minutes

REPORT_FILE = DATA_DIR / "report.html"

ROMAN = ["0", "I", "II", "III", "IV", "V"]

CSS = """
:root {
  --bg: #f4f5f7; --surface: #ffffff; --surface-2: #eef0f3; --border: #d9dde3;
  --text: #1b1f24; --muted: #5f6873; --accent: #1f6fb2;
  --ok: #1d7a46; --ok-bg: #e3f4ea; --queued: #1f6fb2; --queued-bg: #e2eefa;
  --miss: #b23a1f; --miss-bg: #fbe8e3; --bar: #1f6fb2;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #0e1116; --surface: #161b22; --surface-2: #1d232c; --border: #2b333d;
    --text: #e3e8ee; --muted: #8b96a3; --accent: #58a6e8;
    --ok: #4cc48a; --ok-bg: #143324; --queued: #58a6e8; --queued-bg: #132a40;
    --miss: #ef7a5d; --miss-bg: #3a1c15; --bar: #58a6e8;
  }
}
:root[data-theme="dark"] {
  --bg: #0e1116; --surface: #161b22; --surface-2: #1d232c; --border: #2b333d;
  --text: #e3e8ee; --muted: #8b96a3; --accent: #58a6e8;
  --ok: #4cc48a; --ok-bg: #143324; --queued: #58a6e8; --queued-bg: #132a40;
  --miss: #ef7a5d; --miss-bg: #3a1c15; --bar: #58a6e8;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--text);
  font: 14px/1.6 "Segoe UI", "Yu Gothic UI", "Hiragino Sans", "Meiryo", sans-serif;
}
.wrap { max-width: 1200px; margin: 0 auto; padding: 24px 16px 64px; }
header h1 { margin: 0; font-size: 22px; }
header p { margin: 4px 0 0; color: var(--muted); }
nav { display: flex; flex-wrap: wrap; gap: 8px; margin: 20px 0 8px; }
nav a {
  padding: 4px 12px; border: 1px solid var(--border); border-radius: 999px;
  color: var(--text); text-decoration: none; background: var(--surface);
}
nav a:hover { border-color: var(--accent); color: var(--accent); }
h2 { font-size: 18px; margin: 32px 0 12px; }
h3 { font-size: 15px; margin: 0 0 10px; }
.card {
  background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 16px;
}
.muted { color: var(--muted); }
.num { font-variant-numeric: tabular-nums; }
.warn {
  background: var(--miss-bg); color: var(--miss); border-radius: 8px; padding: 8px 12px; margin: 8px 0;
}

/* チェック表 */
.legend { display: flex; flex-wrap: wrap; gap: 16px; margin-bottom: 10px; color: var(--muted); }
.table-scroll { overflow-x: auto; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); }
table.matrix { border-collapse: collapse; width: 100%; min-width: 480px; }
.matrix th, .matrix td { padding: 8px 10px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: top; }
.matrix thead th { background: var(--surface-2); font-weight: 600; white-space: nowrap; }
.matrix tr.cat td { background: var(--surface-2); color: var(--muted); font-size: 12px; font-weight: 600; letter-spacing: .04em; }
.matrix .item { white-space: nowrap; }
.matrix .item small { display: block; color: var(--muted); }
.badge { display: inline-block; padding: 1px 8px; border-radius: 6px; font-weight: 600; white-space: nowrap; }
.badge.ok { color: var(--ok); background: var(--ok-bg); }
.badge.queued { color: var(--queued); background: var(--queued-bg); }
.badge.missing { color: var(--miss); background: var(--miss-bg); }
details.cell summary { cursor: pointer; list-style: none; }
details.cell summary::-webkit-details-marker { display: none; }
details.cell summary::after { content: " ▸"; color: var(--muted); }
details.cell[open] summary::after { content: " ▾"; }
ul.req { list-style: none; margin: 8px 0 0; padding: 0; font-size: 13px; }
ul.req li { display: flex; gap: 8px; justify-content: space-between; padding: 2px 0; border-top: 1px dashed var(--border); }
ul.req .lv { white-space: nowrap; color: var(--muted); }
ul.req .q { color: var(--queued); }

/* キャラクター */
.char { scroll-margin-top: 16px; }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(140px, 100%), 1fr)); gap: 10px; margin-bottom: 12px; }
.stat { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 10px 14px; }
.stat .label { color: var(--muted); font-size: 12px; }
.stat .value { font-size: 20px; font-weight: 600; }
.cols { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 12px; }
.cols > *, .stats > *, section { min-width: 0; }
@media (max-width: 760px) { .cols { grid-template-columns: minmax(0, 1fr); } .stat .value { font-size: 17px; } }
.bars { display: grid; grid-template-columns: minmax(0, 11em) 1fr auto; gap: 4px 10px; align-items: center; font-size: 13px; }
.bars .track { height: 8px; background: var(--surface-2); border-radius: 4px; overflow: hidden; }
.bars .fill { height: 100%; background: var(--bar); border-radius: 4px; }
.bars .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
ol.queue { margin: 0; padding: 0; list-style: none; font-size: 13px; }
ol.queue li { display: flex; justify-content: space-between; gap: 8px; padding: 4px 0; border-bottom: 1px solid var(--border); }
ol.queue li:last-child { border-bottom: 0; }
.attrs { display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: 13px; color: var(--muted); margin-top: 8px; }
.attrs b { color: var(--text); font-weight: 600; }
details.all { margin-top: 12px; }
details.all > summary { cursor: pointer; font-weight: 600; }
.search { width: 100%; max-width: 320px; margin: 10px 0; padding: 6px 10px; border: 1px solid var(--border);
  border-radius: 6px; background: var(--surface); color: var(--text); font: inherit; }
table.skills { border-collapse: collapse; width: 100%; font-size: 13px; }
.skills th, .skills td { padding: 4px 8px; border-bottom: 1px solid var(--border); text-align: left; }
.skills th { color: var(--muted); font-weight: 600; }
.skills td.r, .skills th.r { text-align: right; }
.pips { display: inline-flex; gap: 2px; vertical-align: middle; }
.pips i { width: 9px; height: 9px; border: 1px solid var(--accent); border-radius: 2px; }
.pips i.on { background: var(--accent); }
footer { margin-top: 40px; color: var(--muted); font-size: 12px; }
"""

SCRIPT = """
document.querySelectorAll('input.search').forEach(input => {
  const rows = document.querySelectorAll('#' + input.dataset.target + ' tbody tr');
  input.addEventListener('input', () => {
    const q = input.value.trim().toLowerCase();
    rows.forEach(r => { r.hidden = q && !r.textContent.toLowerCase().includes(q); });
  });
});
"""


def _pips(level):
    return '<span class="pips">' + "".join(
        f'<i class="{"on" if i < level else ""}"></i>' for i in range(5)
    ) + "</span>"


def _badge(result):
    status = result["status"]
    if status == "ok":
        return '<span class="badge ok">✓ 使用可</span>'
    if status == "queued":
        return f'<span class="badge queued">⏳ {escape(format_local(result["ready_at"]))}</span>'
    return f'<span class="badge missing">✗ あと {escape(format_minutes(result["total_minutes"]))}</span>'


def _check_cell(result):
    if result is None:
        return '<td class="muted">-</td>'
    if result["status"] == "ok":
        return f"<td>{_badge(result)}</td>"
    items = []
    for m in result["missing"]:
        note = '<span class="q">キュー済</span> ' if m["queued"] else ""
        if not m["injected"]:
            note += "未注入 "
        items.append(
            f'<li><span>{escape(m["name"])}</span>'
            f'<span class="lv">{note}{ROMAN[m["have"]]} → {ROMAN[m["need"]]}'
            f' · {escape(format_minutes(m["minutes"]))}</span></li>'
        )
    return (
        f'<td><details class="cell"><summary>{_badge(result)}</summary>'
        f'<ul class="req">{"".join(items)}</ul></details></td>'
    )


def _check_section(characters, targets, checks, unresolved):
    parts = ['<section id="check"><h2>艦・装備チェック</h2>']
    for name in unresolved:
        parts.append(f'<div class="warn">「{escape(name)}」が見つかりませんでした（英語名または日本語名の完全一致で指定してください）</div>')
    if not targets:
        parts.append('<div class="card muted">targets.txt にチェックしたい艦・装備を書くと、ここに表示されます。</div></section>')
        return "".join(parts)

    parts.append(
        '<div class="legend"><span><span class="badge ok">✓ 使用可</span> 必要スキルを満たしている</span>'
        '<span><span class="badge queued">⏳ 日時</span> 不足分がキューに入っており、その日時に使用可</span>'
        '<span><span class="badge missing">✗ あと…</span> 不足スキルの合計訓練時間（クリックで内訳）</span></div>'
    )
    parts.append('<div class="table-scroll"><table class="matrix"><thead><tr><th>艦・装備</th>')
    for c in characters:
        parts.append(f"<th>{escape(c['character_name'])}</th>")
    parts.append("</tr></thead><tbody>")

    current_cat = None
    for target in targets:
        if target["category"] != current_cat:
            current_cat = target["category"]
            parts.append(f'<tr class="cat"><td colspan="{len(characters) + 1}">{escape(current_cat)}</td></tr>')
        label = escape(target["input"])
        sub = f'<small>{escape(target["name"])}</small>' if target["name"].lower() != target["input"].lower() else ""
        parts.append(f'<tr><td class="item">{label}{sub}</td>')
        for c in characters:
            parts.append(_check_cell(checks.get((target["type_id"], c["character_id"]))))
        parts.append("</tr>")
    parts.append("</tbody></table></div></section>")
    return "".join(parts)


def _queue_end(character):
    queue = character["skill_queue"]
    if not queue:
        return "空"
    return format_local(queue[-1].get("finish_date"))


def _character_section(c):
    cid = f"char-{c['character_id']}"
    skills = c["skills"]
    lv5 = sum(s["trained_level"] == 5 for s in skills)
    stale = ' <span class="badge missing">前回取得データ</span>' if c.get("stale") else ""

    parts = [f'<section class="char" id="{cid}"><h2>{escape(c["character_name"])}{stale}</h2>']
    parts.append(f'<p class="muted">取得日時: {escape(format_local(c.get("fetched_at")))}</p>')
    if not c["skill_queue"]:
        parts.append('<div class="warn">スキルキューが空です。スキルを訓練していません。</div>')

    stats = [
        ("総 SP", f"{c['total_sp']:,}"),
        ("未割り当て SP", f"{c['unallocated_sp']:,}"),
        ("習得スキル", f"{len(skills)}"),
        ("Lv V", f"{lv5}"),
        ("キュー完了", _queue_end(c)),
    ]
    parts.append('<div class="stats">')
    for label, value in stats:
        parts.append(f'<div class="stat"><div class="label">{label}</div><div class="value num">{escape(value)}</div></div>')
    parts.append("</div>")

    # グループ別 SP
    group_sp = {}
    for s in skills:
        group_sp[s["group"]] = group_sp.get(s["group"], 0) + s["skillpoints"]
    top = max(group_sp.values(), default=1) or 1
    bars = []
    for group, sp in sorted(group_sp.items(), key=lambda x: -x[1]):
        bars.append(
            f'<span class="name" title="{escape(group)}">{escape(group)}</span>'
            f'<span class="track"><span class="fill" style="width:{sp / top * 100:.1f}%;display:block"></span></span>'
            f'<span class="num">{sp:,}</span>'
        )

    # キュー
    queue_items = [
        f'<li><span>{escape(q["name"])} {ROMAN[q["finished_level"]]}</span>'
        f'<span class="muted num">{escape(format_local(q.get("finish_date")))}</span></li>'
        for q in c["skill_queue"]
    ] or ['<li class="muted">（空）</li>']

    attrs = c.get("attributes")
    attrs_html = ""
    if attrs:
        names = [("perception", "知覚"), ("memory", "記憶"), ("willpower", "意志"), ("intelligence", "知性"), ("charisma", "魅力")]
        attrs_html = '<div class="attrs">' + "".join(
            f"<span>{jp} <b>{attrs.get(key, '-')}</b></span>" for key, jp in names
        ) + "</div>"

    parts.append(
        '<div class="cols">'
        f'<div class="card"><h3>グループ別 SP</h3><div class="bars">{"".join(bars)}</div>{attrs_html}</div>'
        f'<div class="card"><h3>スキルキュー（完了予定）</h3><ol class="queue">{"".join(queue_items)}</ol></div>'
        "</div>"
    )

    # 全スキル
    table_id = f"skills-{c['character_id']}"
    rows = "".join(
        f'<tr><td>{escape(s["name"])}</td><td class="muted">{escape(s["group"])}</td>'
        f'<td>{_pips(s["trained_level"])}</td><td class="r num">{s["skillpoints"]:,}</td></tr>'
        for s in skills
    )
    parts.append(
        f'<details class="all card"><summary>全スキル一覧（{len(skills)}）</summary>'
        f'<input class="search" type="search" placeholder="スキル名・グループで絞り込み" data-target="{table_id}">'
        f'<div class="table-scroll" style="border:0"><table class="skills" id="{table_id}">'
        '<thead><tr><th>スキル</th><th>グループ</th><th>レベル</th><th class="r">SP</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></div></details>"
    )
    parts.append("</section>")
    return "".join(parts)


def build_report(characters, targets, checks, unresolved, path=REPORT_FILE):
    """
    characters: fetch_character の出力のリスト（"stale": True は前回データ）
    targets:    [{"category", "input", "type_id", "name"}, ...]
    checks:     {(type_id, character_id): check_target の結果}
    unresolved: 見つからなかった名前のリスト
    """
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    total_sp = sum(c["total_sp"] for c in characters)

    nav = ['<nav><a href="#check">艦・装備チェック</a>']
    nav += [f'<a href="#char-{c["character_id"]}">{escape(c["character_name"])}</a>' for c in characters]
    nav.append("</nav>")

    body = [
        '<div class="wrap"><header><h1>EVE スキルチェッカー</h1>',
        f'<p>{now} 生成 · {len(characters)} キャラクター · 合計 <span class="num">{total_sp:,}</span> SP</p></header>',
        "".join(nav),
        _check_section(characters, targets, checks, unresolved),
        "".join(_character_section(c) for c in characters),
        "<footer>訓練時間は Omega クローン・現在の属性値での見積もりです（加速器・ブースターは考慮しません）。</footer></div>",
    ]

    html = (
        '<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>EVE スキルチェッカー</title><style>{CSS}</style></head>"
        f'<body>{"".join(body)}<script>{SCRIPT}</script></body></html>'
    )
    path.write_text(html, encoding="utf-8")
    return path
