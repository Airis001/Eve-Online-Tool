"""ミッション: 敵の勢力ごとの与ダメージの属性・弱点と、戦闘ミッションの検索（名前・説明文・出てくる勢力の推定）。

データは CCP の静的データ（SDE）から sde.py が取り出したもの。受注中のミッションは ESI で取れないので、名前で探してもらう。
ミッションの敵の勢力は SDE に決まった形では無い（factionID は敵のこともあれば依頼主のこともある）ので、
名前と説明文に出てくる勢力の名前から推定し、画面で選び直せるようにする。
"""

import re
import unicodedata

from flask import jsonify, request

import i18n
from i18n import tr

from .common import error

SEARCH_LIMIT = 20    # 表示するミッション名の数
VARIANT_LIMIT = 12   # 同じ名前のミッションの、説明文・勢力の違うものを出す数
# 説明文（英語）に出てくる言葉 → 勢力。海賊を先に（帝国の名前は依頼主として出てくることが多い）
MENTIONS = [
    (r"\bgurist", 500010), (r"\bserpentis", 500020), (r"\bangel(s| cartel)?\b", 500011), (r"\bblood raider", 500012),
    (r"\bsansha", 500019), (r"\brogue drone|\bdrones?\b", 500025), (r"\bmordu", 500018), (r"\bkhanid", 500008),
    (r"\bthukker", 500015), (r"\bconcord\b", 500006), (r"\bamarr", 500003), (r"\bcaldari", 500001),
    (r"\bgallente", 500004), (r"\bminmatar", 500002),
]


def normalize(s):
    return unicodedata.normalize("NFKC", s or "").casefold().strip()


def register(app, ctx):
    sde = ctx.sde

    def lang_index():
        langs = sde.data.get("faction_langs") or ["ja", "en"]
        lang = i18n.lang()
        return langs.index(lang) if lang in langs else langs.index("en")

    def faction_name(fid):
        names = sde.faction_names.get(fid)
        if not names:
            return str(fid)
        return names[lang_index()] or names[1]

    def preparing():
        """古い版（敵の勢力・ミッションが無い）なら作り直しを始めて、待ってもらう。"""
        if sde.status["state"] != "building":
            sde.build_async()
        return error(tr("静的データ（SDE）を準備しています（{0}%）。しばらくしてから開き直してください。", sde.status.get("progress", 0)), 503)

    def not_ready():
        if not sde.ready or not getattr(sde, "npc_profiles", None):
            return preparing()
        return None

    @app.get("/api/missions/factions")
    def api_mission_factions():
        """勢力ごとの与ダメージの割合・受けるダメージの割合（弱点）・HP の層。"""
        if (res := not_ready()):
            return res
        rows = [{"faction_id": f, "name": faction_name(f), "profiles": p} for f, p in sde.npc_profiles.items()]
        return jsonify({"factions": rows, "damage_types": ["em", "thermal", "kinetic", "explosive"]})

    @app.get("/api/missions/search")
    def api_mission_search():
        """ミッションを名前（どの言語でも）で探す。同じ名前のものはまとめて、説明文・勢力の違いごとに出す。"""
        if (res := not_ready()):
            return res
        data = sde.missions()
        if not data:
            return preparing()
        q = normalize(request.args.get("q"))
        if len(q) < 2:
            return jsonify({"results": [], "query": q})
        lang = i18n.lang()
        texts = data["texts"]
        groups = {}
        for m in data["missions"]:
            if not any(q in normalize(n) for n in m["name"].values()):
                continue
            en = m["name"].get("en") or next(iter(m["name"].values()))
            groups.setdefault(en, []).append(m)
        results = []
        exact = sorted(groups, key=lambda en: (normalize(en) != q, not normalize(en).startswith(q), en))
        for en in exact[:SEARCH_LIMIT]:
            variants, seen = [], set()
            for m in groups[en]:
                brief_id = m["brief"].get(lang, m["brief"].get("en"))
                english = (en + " " + texts[m["brief"]["en"]] if "en" in m["brief"] else en).lower()
                mentioned = [f for rx, f in MENTIONS if re.search(rx, english) and f in sde.npc_profiles]
                key = (m.get("faction"), tuple(mentioned))  # 文の言い回しだけ違うものはまとめる
                if key in seen:
                    continue
                seen.add(key)
                variants.append({"id": m["id"], "faction": m.get("faction"),
                                 "faction_name": faction_name(m["faction"]) if m.get("faction") else None,
                                 "mentioned": [{"faction_id": f, "name": faction_name(f)} for f in mentioned],
                                 "brief": texts[brief_id] if brief_id is not None else ""})
            name = groups[en][0]["name"]
            results.append({"en": en, "name": name.get(lang) or en, "count": len(groups[en]),
                            "variants": variants[:VARIANT_LIMIT], "more": max(len(variants) - VARIANT_LIMIT, 0)})
        return jsonify({"results": results, "total": len(groups), "query": q})
