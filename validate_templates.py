"""fit_templates.py の定番フィットを検証する。

  py validate_templates.py

確認すること: 名前が実在するか / スロット数 / その艦に装着できるか（canFitShip・同グループの装着数上限）/
リグのサイズ / ドローンがドローンベイに入るか / 全スキル V で PG・CPU・キャリブレーションが足りるか。
あわせて全スキル V での DPS の目安と容量を表示する。
"""

import json
import sys

import fetch_skills as core
import fit_rules
import fitting
import skill_check
from dps import DpsCalculator
from fit_templates import TEMPLATES
from item_catalog import ItemCatalog



def all_v_character():
    skills = core.load_skill_catalog()
    return {"skills": [{"skill_id": s, "trained_level": 5, "skillpoints": 10_000_000, "name": v["name"]}
                       for s, v in skills.items()],
            "skill_queue": [], "attributes": {"perception": 20, "memory": 20, "willpower": 20,
                                              "intelligence": 20, "charisma": 19}}


def main():
    type_cache = skill_check.TypeCache(core.esi_get, core.esi_post)
    catalog = ItemCatalog(core.esi_get, core.esi_post)
    data = fitting.FittingData(core.esi_get)
    calc = DpsCalculator(data, type_cache)
    char = all_v_character()
    levels = {s["skill_id"]: 5 for s in char["skills"]}
    volumes = {}
    problems = 0

    for t in TEMPLATES:
        errors = []
        fit = skill_check.parse_eft(t["eft"])
        names = [fit["ship"], *fit["items"]]
        ids = {n: catalog.find_by_name(n) for n in names}
        missing = [n for n, i in ids.items() if not i]
        if missing:
            print(f"✖ {fit['name']}: 見つからない名前 {missing}")
            problems += 1
            continue
        ship = ids[fit["ship"]]
        fitted = [ids[n] for n in fit["fitted"]]
        loaded = [ids[c] if c else None for c in fit["loaded"]]
        bay = [(ids[n], q) for n, q in fit["bay"]]
        data.ensure([ship, *fitted, *[b for b, _ in bay]])

        # スロット・ハードポイント・装着できるか・リグのサイズ・同グループの上限・ドローンベイ
        def volume_of(t):
            if t not in volumes:
                volumes[t] = core.esi_get(f"/universe/types/{t}/").get("volume", 0)
            return volumes[t]
        drones = [(d, q) for d, q in bay if data.attr(d, 1272, 0)]
        errors += fit_rules.fit_errors(data, lambda t: type_cache.get(t)["name"], ship, fitted, drones, volume_of)

        # PG・CPU・キャリブレーション（全スキル V）
        r = fitting.check_resources(data, type_cache, ship, fitted, char)
        for k in ("power", "cpu", "calibration"):
            if not r[k]["ok"]:
                errors.append(f"{k} {r[k]['used']} / {r[k]['total']}")

        dps = calc.compute(ship, fitted, loaded, bay, levels)
        holds = ", ".join(f"{k} {v['total']:,.0f}" for k, v in r["holds"].items())
        status = "✖" if errors else "✓"
        problems += bool(errors)
        print(f"{status} [{t['role']}] {fit['name']}: DPS {dps['total']} (ミサイル {dps['missile']}・ドローン {dps['drone']}) "
              f"PG {r['power']['used']:.0f}/{r['power']['total']:.0f} CPU {r['cpu']['used']:.0f}/{r['cpu']['total']:.0f} "
              f"| {holds} {dps['notes'] or ''} {r['approximate'] or ''}")
        for e in errors:
            print(f"      - {e}")

    data.save()
    type_cache.save()
    print(f"\n問題のあるフィット: {problems} / {len(TEMPLATES)}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
