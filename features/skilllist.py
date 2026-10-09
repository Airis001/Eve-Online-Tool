"""スキル一覧: 選んだキャラクターの全スキル（習得済み・訓練キュー・未注入）をグループごとに出す。"""


import requests
from flask import jsonify

from accounts import ThreadPoolExecutor
from live import safe

from .common import error, int_arg, jita_prices

SKILL_CATEGORY_ID = 16
# スキルインジェクター 1 個で入る SP（使う時点の総 SP で減る）: (総 SP の上限, ラージ, スモール)
INJECTOR_YIELDS = [(5_000_000, 500_000, 100_000), (50_000_000, 400_000, 80_000),
                   (80_000_000, 300_000, 60_000), (float("inf"), 150_000, 30_000)]


def injector_yield(total_sp):
    """総 SP が total_sp のときに、ラージ・スモール 1 個で入る SP。"""
    return next((large, small) for limit, large, small in INJECTOR_YIELDS if total_sp < limit)


def plan_injectors(need, total_sp, price_large, price_small):
    """need SP を入れるのに必要なインジェクターの数。1 個ずつ使って総 SP が増えるにつれ、入る量が減るのも考える。

    ラージだけの場合と、端数をスモールで埋める場合（安い方）を返す。
    """
    large_only, sp, total = 0, need, total_sp
    while sp > 0:
        sp -= injector_yield(total)[0]
        total += injector_yield(total)[0]
        large_only += 1
    # ラージで埋められるところまで使い、残りはラージ 1 個かスモール何個かの安い方
    large, small, sp, total = 0, 0, need, total_sp
    while sp > injector_yield(total)[0]:
        y = injector_yield(total)[0]
        sp, total, large = sp - y, total + y, large + 1
    if sp > 0:
        n_small, rest, t = 0, sp, total
        while rest > 0:
            rest, t, n_small = rest - injector_yield(t)[1], t + injector_yield(t)[1], n_small + 1
        if price_large and price_small and n_small * price_small < price_large:
            small = n_small
        else:
            large += 1

    def cost(n_large, n_small):
        if (n_large and not price_large) or (n_small and not price_small):
            return None
        return n_large * (price_large or 0) + n_small * (price_small or 0)
    return {"large_only": {"large": large_only, "isk": cost(large_only, 0)},
            "mixed": {"large": large, "small": small, "isk": cost(large, small)}}


def register(app, ctx):
    live, core = ctx.live, ctx.core

    def group_names():
        """スキルのグループ: 英語名 → 日本語名（ESI。1 週間キャッシュ）。"""
        cat, _ = safe(live.public, f"/universe/categories/{SKILL_CATEGORY_ID}/", 86400 * 7)
        ids = (cat or {}).get("groups", [])

        def one(gid):
            en, _ = safe(live.public, f"/universe/groups/{gid}/", 86400 * 7)
            ja, _ = safe(live.public, f"/universe/groups/{gid}/", 86400 * 7, {"language": "ja"})
            return (en or {}).get("name"), (ja or {}).get("name")
        with ThreadPoolExecutor(max_workers=8) as pool:
            return {en: ja for en, ja in pool.map(one, ids) if en}

    @app.get("/api/sp-cost")
    def api_sp_cost():
        """sp の SP を、未割り当て SP とスキルインジェクター（Jita で即買い）で入れる場合の数と費用。"""
        char_id = int_arg("character_id")
        sp = int_arg("sp", 0, lo=0, hi=10**9)
        character = next((c for c in ctx.ready_characters() if c["character_id"] == char_id), None)
        if not character:
            return error("キャラクターが見つかりません", 404)
        unallocated = character.get("unallocated_sp") or 0
        total_sp = character.get("total_sp") or 0
        need = max(sp - unallocated, 0)
        ids = {n: ctx.catalog.find_by_name(n) for n in ("Large Skill Injector", "Small Skill Injector")}
        try:
            prices = jita_prices(ctx, [t for t in ids.values() if t])
        except (RuntimeError, requests.RequestException):
            prices = {}
        price_large = (prices.get(ids["Large Skill Injector"]) or {}).get("sell")
        price_small = (prices.get(ids["Small Skill Injector"]) or {}).get("sell")
        large_yield, small_yield = injector_yield(total_sp)
        return jsonify({"sp": sp, "unallocated": unallocated, "need": need, "total_sp": total_sp,
                        "yield_large": large_yield, "yield_small": small_yield,
                        "price_large": price_large, "price_small": price_small,
                        **plan_injectors(need, total_sp, price_large, price_small)})

    @app.get("/api/skill-list")
    def api_skill_list():
        char_id = int_arg("character_id")
        character = next((c for c in ctx.ready_characters() if c["character_id"] == char_id), None)
        if not character:
            return error("キャラクターが見つかりません（スキルチェッカーで取得してください）", 404)
        groups = group_names()
        queue = {}
        for q in character.get("skill_queue") or []:
            sid = q.get("skill_id")
            if sid:
                queue[sid] = max(queue.get(sid, 0), q.get("finished_level", 0))

        def label(skill_id, fallback_en, group_en):
            item = ctx.catalog.get(skill_id) or {}
            return {"ja": item.get("ja") or fallback_en, "en": item.get("en") or fallback_en,
                    "group": group_en, "group_ja": groups.get(group_en) or group_en}

        trained = {}
        for s in character.get("skills", []):
            trained[s["skill_id"]] = {"skill_id": s["skill_id"], **label(s["skill_id"], s.get("name", ""), s.get("group", "")),
                                      "level": s.get("trained_level", 0), "active": s.get("active_level", s.get("trained_level", 0)),
                                      "sp": s.get("skillpoints", 0), "queued": queue.get(s["skill_id"]), "injected": True}
        try:
            catalog = core.load_skill_catalog()
        except (RuntimeError, requests.RequestException):
            catalog = {}
        missing = [{"skill_id": sid, **label(sid, v["name"], v["group"]), "level": 0, "active": 0, "sp": 0,
                    "queued": queue.get(sid), "injected": False}
                   for sid, v in catalog.items() if sid not in trained]
        return jsonify({
            "character_id": char_id, "character_name": character["character_name"],
            "total_sp": character.get("total_sp", 0), "unallocated_sp": character.get("unallocated_sp", 0),
            "fetched_at": character.get("fetched_at"),
            "skills": sorted(trained.values(), key=lambda s: (s["group"], s["en"])),
            "not_injected": sorted(missing, key=lambda s: (s["group"], s["en"])),
        })
