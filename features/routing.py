"""SDE のゲートのつながりを使ったルート（移動・ハブ間の転売・流通ミッションで共有）。

SDE には、使えなくなったゲート（ゲームのルートでは通れない）も載っている。そのため求めたルートのゲートは
ゲームのルート（ESI の最短ルートが 1 ジャンプか）と照らし合わせ、通れないものを避けて求め直す。
確かめた結果は gate_checks.json に保存して使い回す（全員で共有。個人の情報は入らない）。
"""

import json
import threading
from datetime import datetime, timedelta, timezone

import routes
from accounts import ThreadPoolExecutor
from paths import DATA_DIR

GATE_CHECKS_FILE = DATA_DIR / "gate_checks.json"
GATE_CHECK_DAYS = 7
ROUTE_RETRIES = 30
MIN_SEC_CHOICES = (0.5, 0.6, 0.7, 0.8, 0.9)  # 通ってよいセキュリティの下限
MAX_LOW_LIMIT = 3  # セキュリティの足りない星系（ローセクなど）を通ってよい数の上限
_gate_checks = None
_gate_lock = threading.Lock()


class NotReady(Exception):
    """ルートの計算に使う静的データ（SDE）を準備中。"""


def gate_checks():
    """{"a-b": [通れるか, 確かめた日時]}"""
    global _gate_checks
    if _gate_checks is None:
        try:
            _gate_checks = json.loads(GATE_CHECKS_FILE.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            _gate_checks = {}
    return _gate_checks


def known_blocked():
    """これまでに分かった、通れないゲートの区間。"""
    with _gate_lock:
        return {tuple(map(int, k.split("-"))) for k, (ok, _) in gate_checks().items() if not ok}


def gate_usable(ctx, a, b):
    """a と b のあいだのゲートを、ゲームのルートで通れるか（最短ルートが 1 ジャンプか）。結果は保存して使い回す。"""
    x, y = routes.edge(a, b)
    key = f"{x}-{y}"
    now = datetime.now(timezone.utc)
    with _gate_lock:
        hit = gate_checks().get(key)
    if hit and now - datetime.fromisoformat(hit[1]) < timedelta(days=GATE_CHECK_DAYS):
        return hit[0]
    usable = len(ctx.live.public(f"/route/{x}/{y}/", ttl=86400, params={"flag": "shortest"})) == 2
    with _gate_lock:
        gate_checks()[key] = [usable, now.isoformat(timespec="seconds")]
        GATE_CHECKS_FILE.write_text(json.dumps(gate_checks()), encoding="utf-8")
    return usable


def ensure_ready(ctx):
    """ゲートのデータが無ければ作り始めて NotReady（進み具合 %）。"""
    if not ctx.sde.gates:
        if ctx.sde.status["state"] != "building":
            ctx.sde.build_async()
        raise NotReady(ctx.sde.status.get("progress", 0))


def safe_route(ctx, origin, dest, min_sec=0.5, avoid=(), max_low=0):
    """セキュリティが min_sec 以上の星系だけ（足りない星系は max_low か所まで）を通る最短ルート（見つからなければ None）。
    通れないゲートが見つかったら、避けて求め直す。"""
    ensure_ready(ctx)
    blocked = known_blocked()
    for _ in range(ROUTE_RETRIES):
        route = routes.shortest(ctx.sde.gates, ctx.sde.systems, origin, dest, min_sec, avoid, blocked, max_low)
        if not route:
            return None
        pairs = list(zip(route, route[1:]))
        with ThreadPoolExecutor(max_workers=8) as pool:
            usable = list(pool.map(lambda p: gate_usable(ctx, *p), pairs))
        bad = {routes.edge(a, b) for (a, b), ok in zip(pairs, usable) if not ok}
        if not bad:
            return route
        blocked |= bad
    return None


def route_options(args):
    """リクエストの min_sec・max_low（不正な値は既定値に）。"""
    try:
        min_sec = float(args.get("min_sec", 0.5))
    except (TypeError, ValueError):
        min_sec = 0.5
    try:
        max_low = int(args.get("max_low", 0))
    except (TypeError, ValueError):
        max_low = 0
    return (min_sec if min_sec in MIN_SEC_CHOICES else 0.5), max(0, min(max_low, MAX_LOW_LIMIT))
