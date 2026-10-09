"""艦・装備の必要スキル判定と訓練時間の計算。

必要スキルは ESI の型情報 (dogma 属性) から取得し、前提スキルを再帰的にたどって
「最終的に必要なスキルとレベル」の一覧に展開する。型情報は type_cache.json にキャッシュする。
"""

import datetime as dt
import json
import math
import threading
from concurrent.futures import ThreadPoolExecutor

from i18n import tr
from paths import BASE_DIR, DATA_DIR

TYPE_CACHE_FILE = DATA_DIR / "type_cache.json"
TARGETS_FILE = BASE_DIR / "targets.txt"
TARGETS_JSON_FILE = DATA_DIR / "targets.json"

# (必要スキル ID の属性, 必要レベルの属性)
REQUIRED_SKILL_ATTRS = [(182, 277), (183, 278), (184, 279), (1285, 1286), (1289, 1287), (1290, 1288)]
ATTR_SKILL_RANK = 275
ATTR_PRIMARY = 180
ATTR_SECONDARY = 181
CHARACTER_ATTRIBUTES = {164: "charisma", 165: "intelligence", 166: "memory", 167: "perception", 168: "willpower"}


# ---------- 目標リスト ----------

def load_targets(path=TARGETS_FILE):
    """targets.txt を [(カテゴリ, 名前), ...] で返す。

    書式: 1 行 1 アイテム。"[カテゴリ名]" の行で以降のカテゴリを指定。"#" 以降はコメント。
    """
    if not path.exists():
        return []
    targets = []
    category = "その他"
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            category = line[1:-1].strip() or "その他"
        else:
            targets.append((category, line))
    return targets


def load_target_list(path=TARGETS_JSON_FILE):
    """Web アプリで編集したチェックリスト [{"type_id", "label", "category"}, ...]。未作成なら None。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_target_list(targets, path=TARGETS_JSON_FILE):
    path.write_text(json.dumps(targets, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------- 型情報 ----------

def type_info(data, name=None):
    """ESI の /universe/types/{id}/ の応答から、判定に必要な情報だけを取り出す。"""
    attrs = {a["attribute_id"]: a["value"] for a in data.get("dogma_attributes", [])}
    requirements = [
        [int(attrs[s]), int(attrs.get(lv, 1))]
        for s, lv in REQUIRED_SKILL_ATTRS
        if attrs.get(s)
    ]
    return {
        "name": name or data["name"],
        "requirements": requirements,
        "rank": attrs.get(ATTR_SKILL_RANK),
        "primary": CHARACTER_ATTRIBUTES.get(int(attrs.get(ATTR_PRIMARY, 0))),
        "secondary": CHARACTER_ATTRIBUTES.get(int(attrs.get(ATTR_SECONDARY, 0))),
    }


class TypeCache:
    """ESI の型情報のうち、スキル判定に必要な部分だけを保持する。"""

    def __init__(self, esi_get, esi_post, path=TYPE_CACHE_FILE):
        self.esi_get = esi_get
        self.esi_post = esi_post
        self.path = path
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            self.types = {int(k): v for k, v in raw.items()}
        except (FileNotFoundError, json.JSONDecodeError):
            self.types = {}
        self.dirty = False
        self._lock = threading.RLock()  # Web アプリでは複数スレッドから使われる

    def save(self):
        with self._lock:
            if self.dirty:
                self.path.write_text(json.dumps(self.types, ensure_ascii=False), encoding="utf-8")
                self.dirty = False

    def _fetch(self, type_id):
        return type_id, type_info(self.esi_get(f"/universe/types/{type_id}/"))

    def put(self, type_id, info):
        with self._lock:
            self.types[type_id] = info
            self.dirty = True

    def ensure(self, type_ids):
        """未取得の型情報をまとめて取得する（並列）。"""
        missing = [t for t in set(type_ids) if t not in self.types]
        if not missing:
            return
        with ThreadPoolExecutor(max_workers=10) as pool:
            fetched = list(pool.map(self._fetch, missing))
        for type_id, info in fetched:
            self.put(type_id, info)

    def get(self, type_id):
        self.ensure([type_id])
        return self.types[type_id]

    def full_requirements(self, type_id):
        """前提スキルまで展開した {skill_id: 必要レベル} を返す。"""
        required = {}
        frontier = [type_id]
        seen = set()
        while frontier:
            self.ensure(frontier)
            next_frontier = []
            for t in frontier:
                if t in seen:
                    continue
                seen.add(t)
                for skill_id, level in self.types[t]["requirements"]:
                    if level > required.get(skill_id, 0):
                        required[skill_id] = level
                    next_frontier.append(skill_id)
            frontier = next_frontier
        return required

    def resolve_names(self, names):
        """名前（英語または日本語、完全一致）→ (type_id, 英語名)。見つからない名前は含まない。"""
        found = {}
        remaining = list(dict.fromkeys(names))
        for lang in ("en", "ja"):
            if not remaining:
                break
            res = self.esi_post("/universe/ids/", remaining, params={"language": lang})
            by_name = {t["name"].lower(): t["id"] for t in res.get("inventory_types", [])}
            for name in list(remaining):
                type_id = by_name.get(name.lower())
                if type_id:
                    found[name] = type_id
                    remaining.remove(name)
        self.ensure(found.values())
        return {name: (type_id, self.types[type_id]["name"]) for name, type_id in found.items()}


# ---------- SP・訓練時間 ----------

def sp_for_level(rank, level):
    """指定レベルに到達するのに必要な累計 SP。"""
    if level <= 0:
        return 0
    # 浮動小数点誤差（例: 8000.0000001）で 1 SP 多くならないよう丸めてから切り上げる
    return math.ceil(round(250 * rank * math.sqrt(32) ** (level - 1), 6))


def sp_per_minute(skill_info, attributes):
    """Omega クローンでの訓練速度（主属性 + 副属性 / 2）。"""
    if not attributes or not skill_info.get("primary"):
        return None
    return attributes[skill_info["primary"]] + attributes[skill_info["secondary"]] / 2


# ---------- 判定 ----------

def _queue_index(character):
    """{skill_id: [(finished_level, finish_date), ...]}（レベル順）"""
    index = {}
    for q in character["skill_queue"]:
        index.setdefault(q["skill_id"], []).append((q["finished_level"], q.get("finish_date")))
    for entries in index.values():
        entries.sort(key=lambda e: e[0])
    return index


def _queued_finish(queue_index, skill_id, level):
    """skill_id が level に達するキュー項目があれば (True, 完了日時)。"""
    for finished_level, finish_date in queue_index.get(skill_id, []):
        if finished_level >= level:
            return True, finish_date
    return False, None


def merged_requirements(type_cache, type_ids):
    """複数アイテムの必要スキルを合わせた {skill_id: 最大必要レベル}。"""
    required = {}
    for type_id in set(type_ids):
        for skill_id, level in type_cache.full_requirements(type_id).items():
            required[skill_id] = max(level, required.get(skill_id, 0))
    return required


def level_breakdown(info, have, need, current_sp, rate):
    """have → need の各レベルに必要な SP と訓練時間 [{"level", "sp", "minutes"}]。"""
    rank = info["rank"] or 1
    levels = []
    for lv in range(have + 1, need + 1):
        # 訓練途中の SP があれば、最初のレベルはその分を差し引く
        sp = max(sp_for_level(rank, lv) - max(sp_for_level(rank, lv - 1), current_sp), 0)
        levels.append({"level": lv, "sp": sp, "minutes": sp / rate if rate else None})
    return levels


def check_types(type_cache, type_ids, character):
    """character（fetch_character の出力）が type_ids をすべて使えるか判定する。

    戻り値の status:
      "ok"      必要スキルをすべて満たしている
      "queued"  不足分はすべてスキルキューに入っている
      "missing" 不足スキルがある
    """
    trained = {s["skill_id"]: s for s in character["skills"]}
    queue_index = _queue_index(character)
    attributes = character.get("attributes")
    missing = []
    total_minutes = 0.0
    time_known = True
    for skill_id, need in merged_requirements(type_cache, type_ids).items():
        have_skill = trained.get(skill_id)
        have = have_skill["trained_level"] if have_skill else 0
        if have >= need:
            continue
        info = type_cache.get(skill_id)
        current_sp = have_skill["skillpoints"] if have_skill else 0
        sp_needed = max(sp_for_level(info["rank"] or 1, need) - current_sp, 0)
        rate = sp_per_minute(info, attributes)
        minutes = sp_needed / rate if rate else None
        if minutes is None:
            time_known = False
        else:
            total_minutes += minutes
        queued, finish = _queued_finish(queue_index, skill_id, need)
        missing.append({
            "skill_id": skill_id,
            "name": info["name"],
            "have": have,
            "need": need,
            "injected": have_skill is not None,
            "queued": queued,
            "queue_finish": finish,
            "sp_needed": sp_needed,
            "minutes": minutes,
            "levels": level_breakdown(info, have, need, current_sp, rate),
        })

    missing.sort(key=lambda m: (m["queued"], m["name"]))
    if not missing:
        status = "ok"
    elif all(m["queued"] for m in missing):
        status = "queued"
    else:
        status = "missing"

    ready_at = None
    if status == "queued":
        ready_at = max((m["queue_finish"] for m in missing if m["queue_finish"]), default=None)

    return {
        "status": status,
        "missing": missing,
        "total_minutes": total_minutes if time_known else None,
        "ready_at": ready_at,
        # スキルインジェクターの必要数の計算用
        "unallocated_sp": character.get("unallocated_sp", 0),
        "character_sp": character.get("total_sp", 0),
    }


def check_target(type_cache, type_id, character):
    return check_types(type_cache, [type_id], character)


def find_blockers(type_cache, type_ids, character):
    """type_ids のうち、単体で使えないアイテム（フィットの原因モジュール）を時間の長い順に返す。"""
    blockers = []
    for type_id in dict.fromkeys(type_ids):
        result = check_target(type_cache, type_id, character)
        if result["status"] != "ok":
            blockers.append({
                "type_id": type_id,
                "name": type_cache.get(type_id)["name"],
                "status": result["status"],
                "total_minutes": result["total_minutes"],
                "ready_at": result["ready_at"],
            })
    blockers.sort(key=lambda b: -(b["total_minutes"] or 0))
    return blockers


# ---------- スキルプラン ----------

def build_plan(type_cache, type_ids, character, skill_targets=None):
    """type_ids を使えるようにするための訓練手順（前提スキルが先に来る順）。

    skill_targets: {skill_id: level} を渡すと、そのスキルをそのレベルまで上げる手順も加える
                   （例: CPU・PG を足りさせるための CPU Management V）。

    戻り値: {"steps": [{skill_id, name, level, sp, minutes, queued, finish_at}], "total_minutes", "unqueued_minutes",
             "total_sp", "unqueued_sp"}
      sp: そのレベルまでに必要な SP（途中まで訓練済みなら残りの分）
      finish_at: キュー済みの手順はキューの完了日時。それ以外は、今のキューが終わってから
                 キュー外の分を順に訓練した場合の完了見込み。
    """
    trained = {s["skill_id"]: s for s in character["skills"]}
    queue_index = _queue_index(character)
    attributes = character.get("attributes")
    planned = {}  # skill_id → 手順に入れた最高レベル
    steps = []

    def have_level(skill_id):
        skill = trained.get(skill_id)
        return skill["trained_level"] if skill else 0

    def add(skill_id, level, depth=0):
        current = planned.get(skill_id, have_level(skill_id))
        if level <= current or depth > 50:
            return
        # 前提スキルを先に
        for req_id, req_level in type_cache.get(skill_id)["requirements"]:
            add(req_id, req_level, depth + 1)
        info = type_cache.get(skill_id)
        rank = info["rank"] or 1
        rate = sp_per_minute(info, attributes)
        current_sp = trained[skill_id]["skillpoints"] if skill_id in trained else 0
        for lv in range(current + 1, level + 1):
            sp_from = max(sp_for_level(rank, lv - 1), current_sp)
            sp_to = sp_for_level(rank, lv)
            minutes = max(sp_to - sp_from, 0) / rate if rate else None
            queued, finish = _queued_finish(queue_index, skill_id, lv)
            steps.append({"skill_id": skill_id, "name": info["name"], "level": lv, "sp": max(sp_to - sp_from, 0), "minutes": minutes,
                          "queued": queued, "queue_finish": finish})
        planned[skill_id] = level

    # 目標アイテムの直接の必要スキルから順にたどる（前提は add の中で先に入る）
    type_cache.ensure(type_ids)
    targets = [req for type_id in dict.fromkeys(type_ids) for req in type_cache.get(type_id)["requirements"]]
    targets += list((skill_targets or {}).items())
    for skill_id, level in targets:
        type_cache.full_requirements(skill_id)  # 前提スキルの型情報をまとめて取得しておく
        add(skill_id, level)

    # キュー外の手順は、今のスキルキューが終わってから訓練する前提で見積もる
    start = dt.datetime.now(dt.timezone.utc)
    for q in character["skill_queue"]:
        if q.get("finish_date"):
            start = max(start, dt.datetime.fromisoformat(q["finish_date"].replace("Z", "+00:00")))
    now = start
    elapsed = 0.0
    for step in steps:
        if step["queued"] or step["minutes"] is None:
            step["finish_at"] = step["queue_finish"] if step["queued"] else None
            continue
        elapsed += step["minutes"]
        step["finish_at"] = (now + dt.timedelta(minutes=elapsed)).isoformat(timespec="seconds")

    known = [s["minutes"] for s in steps if s["minutes"] is not None]
    return {
        "steps": steps,
        "total_minutes": sum(known) if len(known) == len(steps) else None,
        "unqueued_minutes": sum(s["minutes"] or 0 for s in steps if not s["queued"]),
        "total_sp": sum(s["sp"] for s in steps),
        "unqueued_sp": sum(s["sp"] for s in steps if not s["queued"]),
    }


def plan_to_text(plan, include_queued=False):
    """ゲームのスキルキューに貼り付ける用のテキスト（1 行に「英語スキル名 レベル」）。"""
    return "\n".join(
        f"{s['name']} {s['level']}" for s in plan["steps"] if include_queued or not s["queued"]
    )


# ---------- EFT 形式 ----------

def parse_eft(text):
    """EFT 形式のフィット（Pyfa・zKillboard などのコピー）を解析する。

    戻り値: {"ship": 艦名, "name": フィット名,
             "items": [アイテム名, ...]（重複あり・順番どおり・弾薬やドローンも含む）,
             "fitted": [スロットに装着するモジュール名, ...]（重複あり。弾薬と数量付きの行は除く）}
    """
    lines = [line.strip() for line in text.strip().splitlines()]
    lines = [line for line in lines if line]
    if not lines or not (lines[0].startswith("[") and "]" in lines[0]):
        raise ValueError("1 行目は [艦名, フィット名] の形式にしてください。")
    header = lines[0][1:lines[0].index("]")]
    ship, _, name = header.partition(",")
    items = []
    fitted = []
    loaded = []  # fitted と同じ並びで、装填している弾薬の名前（無ければ None）
    bay = []  # [(アイテム名, 個数)] ドローン・カーゴ
    for line in lines[1:]:
        if line.startswith("[") and line.endswith("]"):
            continue  # [Empty High slot] など
        line = line.split(" /offline")[0].strip()
        parts = [p.strip() for p in line.split(",")]  # 「モジュール, チャージ」
        for n, part in enumerate(parts):
            base, sep, count = part.rpartition(" x")
            in_bay = bool(sep and count.isdigit())  # 「Hobgoblin II x5」はドローン・カーゴ
            if in_bay:
                part = base.strip()
            if part:
                items.append(part)
                if n == 0 and not in_bay:
                    fitted.append(part)
                    loaded.append(parts[1] if len(parts) > 1 and parts[1] else None)
                elif in_bay:
                    bay.append((part, int(count)))
    return {"ship": ship.strip(), "name": name.strip() or ship.strip(), "items": items, "fitted": fitted,
            "loaded": loaded, "bay": bay}


def format_minutes(minutes):
    if minutes is None:
        return "不明"
    minutes = int(math.ceil(minutes))
    days, rem = divmod(minutes, 60 * 24)
    hours, mins = divmod(rem, 60)
    if days:
        return tr("{0}日 {1}時間", days, hours)
    if hours:
        return tr("{0}時間 {1}分", hours, mins)
    return tr("{0}分", mins)


def format_local(iso):
    """ESI の UTC 日時をローカル時刻の文字列に。"""
    if not iso:
        return "-"
    t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
    return t.strftime("%Y-%m-%d %H:%M")
