"""画面の言語の切り替え（日本語・英語・ドイツ語・フランス語・スペイン語・ロシア語・韓国語・中国語）。

文言は日本語をそのまま見出しにして、static/i18n/<言語>.json に訳を置く（JS と共通）。
  tr("キャラクターが見つかりません。")          → 今の言語の訳。無ければ英語、それも無ければ日本語のまま
  tr("{0} 星系", 3)                            → {0}, {1} … に引数を入れる（書式は str.format と同じ）
言語は Cookie（lang）で決める。無いときはブラウザーの言語（Accept-Language）で、対応していない言語なら英語。
HTML のページ（static/*.html）の固定の文字は、返すときに translate_html で置き換える。
艦・装備の名前は、API の応答に今の言語の名前（loc / 〇〇_loc）を書き足す（localize_names）。
"""

import json
import re
from functools import lru_cache

from paths import BASE_DIR

LANGS = ("ja", "en", "de", "fr", "es", "ru", "ko", "zh")
# 言語の切り替えのメニューに出す名前（その言語での呼び方）
LANG_NAMES = {"ja": "日本語", "en": "English", "de": "Deutsch", "fr": "Français", "es": "Español",
              "ru": "Русский", "ko": "한국어", "zh": "中文"}
COOKIE = "lang"
DICT_DIR = BASE_DIR / "static" / "i18n"
DICT_FILE = DICT_DIR / "en.json"  # 英語（ほかの言語で訳が無いときにも使う）
JP = re.compile(r"[぀-ヿ㐀-鿿！-～]")


@lru_cache(maxsize=16)
def _dict_cached(language, mtime):
    try:
        return json.loads((DICT_DIR / f"{language}.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _dict_file(language):
    path = DICT_DIR / f"{language}.json"
    return _dict_cached(language, path.stat().st_mtime if path.exists() else 0)


def dict_for(language):
    """その言語の訳の辞書（訳が無い文言は英語）。日本語は空。ファイルを書き換えたら読み直す。"""
    if language == "ja":
        return {}
    if language == "en":
        return _dict_file("en")
    return _merged(language, *(_mtime(x) for x in ("en", language)))


def _mtime(language):
    path = DICT_DIR / f"{language}.json"
    return path.stat().st_mtime if path.exists() else 0


@lru_cache(maxsize=16)
def _merged(language, *_mtimes):
    return {**_dict_file("en"), **_dict_file(language)}


def dict_stamp(language):
    """辞書の更新時刻（ページの読み込み直しの判定用）。"""
    return max(_mtime("en"), _mtime(language)) if language != "ja" else 0


def en_dict():
    """英語訳の辞書。"""
    return dict_for("en")


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
    language = lang()
    if language != "ja":
        table = dict_for(language)
        text = table.get(text) or text
        args = [table.get(a, a) if isinstance(a, str) else a for a in args]
        kwargs = {k: table.get(v, v) if isinstance(v, str) else v for k, v in kwargs.items()}
    return text.format(*args, **kwargs) if args or kwargs else text


# ---------- 艦・装備の名前 ----------

_name_lookup = None  # (type_id, 言語) → その言語の名前（無ければ None）。app が SDE の名前を設定する


def set_name_lookup(func):
    global _name_lookup
    _name_lookup = func


def localized_name(type_id, language=None):
    """type_id の、今の言語（または language）の名前。日本語・英語以外で分からなければ None。"""
    language = language or lang()
    if _name_lookup is None or not isinstance(type_id, int) or language in ("ja", "en"):
        return None
    return _name_lookup(type_id, language)


def item_name(item, ja="ja", en="en"):
    """{"ja": 日本語名, "en": 英語名} のような項目の、今の言語の名前。"""
    if not item:
        return ""
    language = lang()
    if language == "ja":
        return item.get(ja) or item.get(en)
    base = en[:-2] if en.endswith("_en") else ""
    loc = localized_name(_id_of(item, base), language) if language != "en" else None
    return loc or item.get(en) or item.get(ja)


def _id_of(d, base):
    """名前（〇〇_en / en）に対応するアイテムの ID。"""
    keys = (f"{base}_type_id", f"{base}_id", base) if base else ("type_id", "id", "skill_id")
    for k in keys:
        v = d.get(k)
        if isinstance(v, int) and not isinstance(v, bool):
            return v
    return None


def localize_names(obj, language):
    """API の応答の中の英語名（en / 〇〇_en）の隣に、その言語の名前（loc / 〇〇_loc）を書き足す。

    英語名そのものは変えない（EFT のコピーやスキルプランなど、英語名を使う処理があるため）。
    """
    if language in ("ja", "en") or _name_lookup is None:
        return obj
    if isinstance(obj, dict):
        out = {k: localize_names(v, language) for k, v in obj.items()}
        for k, v in obj.items():
            if isinstance(v, str) and (k == "en" or k.endswith("_en")):
                base = k[:-3] if k != "en" else ""
                name = _name_lookup(_id_of(obj, base), language) if _id_of(obj, base) is not None else None
                if name:
                    out[f"{base}_loc" if base else "loc"] = name
        return out
    if isinstance(obj, (list, tuple)):
        return [localize_names(v, language) for v in obj]
    return obj


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
        table = dict_for(lang())
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
    if language == "ja":
        return html
    table = dict_for(language)
    out = []
    for kind, part in html_parts(html):
        if kind == "tag":
            if not part.startswith("<!--"):
                part = _ATTR.sub(lambda m: f'{m[1]}="{_translate_text(m[2], table)}"', part)
                part = part.replace('<html lang="ja"', f'<html lang="{language}"')
            out.append(part)
        else:
            out.append(_translate_text(part, table))
    return "".join(out)
