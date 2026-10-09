"""画面の言語（日本語・英語）の切り替え。

文言は日本語をそのまま見出しにして、static/i18n/en.json に英語訳を置く（JS と共通）。
  tr("キャラクターが見つかりません。")          → 英語のときは訳、なければ日本語のまま
  tr("{0} 星系", 3)                            → {0}, {1} … に引数を入れる（書式は str.format と同じ）
言語は Cookie（lang）で決める。無いときはブラウザーの言語（Accept-Language）で、日本語以外なら英語。
HTML のページ（static/*.html）の固定の文字は、返すときに translate_html で置き換える。
"""

import json
import re
from functools import lru_cache

from paths import BASE_DIR

LANGS = ("ja", "en")
COOKIE = "lang"
DICT_FILE = BASE_DIR / "static" / "i18n" / "en.json"
JP = re.compile(r"[぀-ヿ㐀-鿿！-～]")


@lru_cache(maxsize=1)
def _dict_cached(mtime):
    try:
        return json.loads(DICT_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def en_dict():
    """英語訳の辞書（ファイルを書き換えたら読み直す）。"""
    try:
        return _dict_cached(DICT_FILE.stat().st_mtime)
    except FileNotFoundError:
        return {}


def lang():
    """今のリクエストの言語（リクエストの外では日本語）。"""
    try:
        from flask import has_request_context, request
    except ImportError:
        return "ja"
    if not has_request_context():
        return "ja"
    chosen = request.cookies.get(COOKIE)
    if chosen in LANGS:
        return chosen
    return request.accept_languages.best_match(LANGS, default="en") if request.accept_languages else "ja"


def tr(text, *args, **kwargs):
    """text を今の言語にする。args / kwargs があれば {0} / {name} に入れる（辞書に載っている値は訳して入れる）。"""
    if lang() == "en":
        table = en_dict()
        text = table.get(text) or text
        args = [table.get(a, a) if isinstance(a, str) else a for a in args]
        kwargs = {k: table.get(v, v) if isinstance(v, str) else v for k, v in kwargs.items()}
    return text.format(*args, **kwargs) if args or kwargs else text


def item_name(item, ja="ja", en="en"):
    """{"ja": 日本語名, "en": 英語名} のような項目の、今の言語の名前。"""
    if not item:
        return ""
    return (item.get(en) or item.get(ja)) if lang() == "en" else (item.get(ja) or item.get(en))


_PAREN_TAIL = re.compile(r"^(.+?)((?:（[^（）]*）)+)$")


def _lookup(text, table):
    """辞書の訳。無ければ、末尾のかっこ書きを分けて訳す（例: "定番 Tristan ドローン（T1 装備）"）。"""
    if text in table:
        return table[text]
    m = _PAREN_TAIL.match(text)
    if m and m[1] in table:
        tails = re.findall(r"（[^（）]*）", m[2])
        if all(t in table for t in tails):
            return table[m[1]] + "".join(table[t] for t in tails)
    return text


def translate_data(obj, table=None):
    """API の応答（JSON にする値）の中の、辞書にそのまま載っている文字列を訳す（辞書のキーは訳さない）。

    カテゴリ名・役割名・エラーメッセージなど、サーバーが日本語で決めている値を、画面の言語に合わせるため。
    値を埋め込んだ文は、作るところで tr("…{0}…", 値) にしておく。
    """
    if table is None:
        table = en_dict()
    if isinstance(obj, str):
        return _lookup(obj, table) if JP.search(obj) else obj
    if isinstance(obj, dict):
        return {k: translate_data(v, table) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [translate_data(v, table) for v in obj]
    return obj


# ---------- HTML のページ ----------

_TAG = re.compile(r"(<!--.*?-->|<[^>]+>)", re.S)
_TAG_NAME = re.compile(r"</?([a-zA-Z][a-zA-Z0-9]*)")
_ATTR = re.compile(r'\b(title|placeholder|aria-label|alt|content|data-tip)="([^"]*)"')
# 文の途中に入るタグ。これをはさんだ文は、タグごと 1 つの文として訳す（例: "{0} は <a href=…>再ログイン</a> が必要です"）
INLINE_TAGS = {"a", "b", "strong", "i", "em", "small", "code", "kbd", "s", "u", "sup", "sub"}


def _norm(text):
    return re.sub(r"\s+", " ", text).strip()


def _is_inline(part):
    m = _TAG_NAME.match(part)
    return bool(m) and m[1].lower() in INLINE_TAGS


def _sentence(run):
    """文中のタグをはさんだひと続きの文字 run を、訳す単位に分ける。

    外側から見て、日本語の文字がタグの外に直接ある階層を、タグごと 1 つの文にする
    （例: "{0} は <a href=…>再ログイン</a> が必要です"）。リンクが並んでいるだけなら、リンクの文字ごと。
    """
    # 文中のタグの入れ子を木にする: 要素は [開くタグ, [子], 閉じるタグ]、文字はそのまま
    root = []
    stack = [root]
    opened = []
    for p in (p for p in _TAG.split(run) if p):
        if p.startswith("</") and opened:
            elem = opened.pop()
            elem[2] = p
            stack.pop()
        elif p.startswith("<") and not p.startswith("</") and not p.endswith("/>"):
            elem = [p, [], ""]
            stack[-1].append(elem)
            stack.append(elem[1])
            opened.append(elem)
        else:
            stack[-1].append(p)

    def flat(nodes):
        return "".join(n if isinstance(n, str) else n[0] + flat(n[1]) + n[2] for n in nodes)

    def units(nodes):
        if JP.search("".join(n for n in nodes if isinstance(n, str) and not n.startswith("<"))):
            return [("text", flat(nodes))]
        out = []
        for n in nodes:
            if isinstance(n, str):
                out.append(("tag" if n.startswith("<") else "text", n))
            else:
                out += [("tag", n[0]), *units(n[1])] + ([("tag", n[2])] if n[2] else [])
        return out

    return units(root)


def html_parts(html):
    """HTML を [("tag", タグ) | ("text", 訳す単位の文字)] に分ける。"""
    parts = []
    run = ""
    for part in _TAG.split(html):
        if not part:
            continue
        if part.startswith("<!--") or (part.startswith("<") and not _is_inline(part)):
            if run:
                parts += _sentence(run)
                run = ""
            parts.append(("tag", part))
        else:
            run += part
    if run:
        parts += _sentence(run)
    return parts


def _translate_text(text, table):
    key = _norm(text)
    if not key or not JP.search(key):
        return text
    lead = text[:len(text) - len(text.lstrip())]
    trail = text[len(text.rstrip()):]
    return lead + table[key] + trail if key in table else text


def translate_html(html, language):
    """ページの固定の文字を訳す（タグのあいだの文と、title・placeholder などの属性）。"""
    if language != "en":
        return html
    table = en_dict()
    out = []
    for kind, part in html_parts(html):
        if kind == "tag":
            if not part.startswith("<!--"):
                part = _ATTR.sub(lambda m: f'{m[1]}="{_translate_text(m[2], table)}"', part)
                part = part.replace('<html lang="ja"', '<html lang="en"')
            out.append(part)
        else:
            out.append(_translate_text(part, table))
    return "".join(out)
