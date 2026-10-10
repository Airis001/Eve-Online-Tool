"""訳の辞書（static/i18n/<言語>.json）を検証する。

  py check_i18n.py            全言語の足りない訳・{0} などの数やタグのちがい・使われていない訳を表示
  py check_i18n.py --missing  英語で足りない訳だけを JSON（{"日本語": ""}）で表示（辞書に足す下書き用）
  py check_i18n.py --missing de   ほかの言語で足りない訳を {"日本語": "英語訳"} で表示

集める文言:
  - JS・Python の tr("…") の 1 つ目の引数
  - Python の日本語の文字列（API の応答でそのまま訳すもの。docstring・print() の中は除く）
  - static/*.html のタグのあいだの文字と、title・placeholder などの属性（i18n.translate_html と同じ区切り方）
  - targets.txt（チェックリストの初期内容）の見出し
"""

import ast
import json
import re
import sys
from pathlib import Path

import i18n

ROOT = Path(__file__).resolve().parent
JS_TR = re.compile(r'\btr\(\s*"((?:\\.|[^"\\])*)"')
PLACEHOLDER = re.compile(r"\{(\d+)[^}]*\}")
EFT_HEAD = re.compile(r"\[[^,\]]+, ([^\]]+)\]")
TAG = re.compile(r"</?[a-zA-Z][a-zA-Z0-9]*")
KANA = re.compile(r"[぀-ヿ]")  # ひらがな・カタカナ（訳に残っていたら訳し忘れ）
# コマンドで使うだけのファイル（画面には出ない）
CLI_ONLY = {"check_i18n.py", "validate_templates.py", "build_exe.py", "report.py", "i18n.py"}


def js_keys():
    keys = {}
    for path in sorted(p for p in (ROOT / "static").glob("*.js") if p.name != "i18n.js"):
        text = path.read_text(encoding="utf-8")
        for m in JS_TR.finditer(text):
            keys.setdefault(json.loads(f'"{m[1]}"'), f"{path.name}:{text.count(chr(10), 0, m.start()) + 1}")
    return keys


def py_keys():
    keys = {}
    for path in sorted([*ROOT.glob("*.py"), *(ROOT / "features").glob("*.py")]):
        if path.name in CLI_ONLY:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        skip = set()
        for node in ast.walk(tree):
            # docstring
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and node.body:
                first = node.body[0]
                if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                    skip.add(id(first.value))
            # print() の中・正規表現（re.〇〇）・f-string の部品
            if isinstance(node, ast.Call) and (
                    (isinstance(node.func, ast.Name) and node.func.id == "print")
                    or (isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "re")):
                skip.update(id(n) for n in ast.walk(node))
            if isinstance(node, ast.JoinedStr):
                skip.update(id(n) for n in node.values)
        for node in ast.walk(tree):
            # 1 文字だけのもの（ひらがなの範囲の判定など）は文言ではない
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip \
                    and len(node.value) > 1 and i18n.JP.search(node.value):
                where = f"{path.relative_to(ROOT)}:{node.lineno}"
                value = node.value
                eft = EFT_HEAD.match(value)
                if eft and "\n" in value:  # EFT 形式のフィット（画面に出るのはフィット名）
                    value = eft[1]
                if re.search(r"<[a-z]", value):  # HTML の部品（サインインのページなど）は HTML と同じ単位で
                    for key in html_text_keys(value):
                        keys.setdefault(key, where)
                    continue
                keys.setdefault(value, where)
    return keys


def targets_keys():
    """targets.txt（チェックリストの初期内容）の見出し [〇〇]。"""
    path = ROOT / "targets.txt"
    if not path.exists():
        return {}
    heads = re.findall(r"^\[(.+)\]\s*$", path.read_text(encoding="utf-8"), re.M)
    return {h: "targets.txt" for h in heads if i18n.JP.search(h)}


def html_keys():
    keys = {}
    for path in sorted((ROOT / "static").glob("*.html")):
        for key in html_text_keys(path.read_text(encoding="utf-8")):
            keys.setdefault(key, path.name)
    return keys


def html_text_keys(html):
    """HTML から、i18n.translate_html が訳す単位の文字を取り出す。"""
    found = []
    for kind, part in i18n.html_parts(html):
        if part.startswith("<!--"):
            continue
        if kind == "tag":
            found += [i18n._norm(m[2]) for m in i18n._ATTR.finditer(part)]
        else:
            found.append(i18n._norm(part))
    return [k for k in found if k and i18n.JP.search(k)]


def check_table(language, table, used):
    """1 言語分の問題を表示し、足りない訳の数を返す。"""
    missing = [k for k in used if not table.get(k)]
    for key in missing:
        print(f"[{language}] 訳なし  {used[key]}  {json.dumps(key, ensure_ascii=False) if chr(10) in key else key}")
    for key, text in table.items():
        if not text:
            continue
        if sorted(set(PLACEHOLDER.findall(key))) != sorted(set(PLACEHOLDER.findall(text))):
            print(f"[{language}] {{}}の数  {key}  →  {text}")
        if sorted(TAG.findall(key)) != sorted(TAG.findall(text)):
            print(f"[{language}] タグのちがい  {key}  →  {text}")
        # 訳を見出しと同じにしたもの（記号だけなど）は意図どおり。中国語は漢字を使うので調べない
        if language != "zh" and text != key and KANA.search(text):
            print(f"[{language}] 日本語が残る  {key}  →  {text}")
    return len(missing)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    used = {**targets_keys(), **html_keys(), **py_keys(), **js_keys()}
    en = i18n.en_dict()
    if "--missing" in sys.argv:
        rest = sys.argv[sys.argv.index("--missing") + 1:]
        if rest:
            table = i18n._dict_file(rest[0])
            print(json.dumps({k: en.get(k, "") for k in used if not table.get(k)}, ensure_ascii=False, indent=1))
        else:
            print(json.dumps({k: "" for k in used if not en.get(k)}, ensure_ascii=False, indent=1))
        return
    summary = []
    for language in i18n.LANGS:
        if language == "ja":
            continue
        table = i18n._dict_file(language)
        missing = check_table(language, table, used)
        summary.append(f"{language} {len(table)} 件（訳なし {missing}）")
    unused = [k for k in en if k not in used]
    print(f"文言 {len(used)} 件 · " + " · ".join(summary) + f" · 英語の辞書だけにある {len(unused)} 件（サーバーの値など、使われ方で必要なものもある）")


if __name__ == "__main__":
    main()
