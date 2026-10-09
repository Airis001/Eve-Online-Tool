"""星系のルート（SDE のゲートのつながりで計算する）。

ESI の「安全優先」は、どの星系をどれだけ避けるかを選べない。ここでは「セキュリティが min_sec 以上の星系だけを
通る最短ルート」を幅優先探索で求める（0.5 ならハイセクだけ。0.6 以上にすると、襲撃の多い 0.5 の星系も避けられる）。

SDE には、使えなくなったゲート（ゲームのルートでは通れない）も載っている。そのため、求めたルートのゲートは
呼び出し側でゲームのルート（ESI）と照らし合わせ、通れないものを blocked に入れて求め直す。
"""

from collections import deque

from wormhole import display_security


def edge(a, b):
    """ゲートの区間の名前（向きによらない）。"""
    return (a, b) if a < b else (b, a)


def shortest(gates, systems, origin, dest, min_sec, avoid=(), blocked=frozenset(), max_low=0):
    """origin → dest の星系 ID の並び（見つからなければ None）。出発地・目的地はセキュリティに関係なく通れる。

    gates: {星系 ID: {行き先の星系 ID: …}}、systems: {星系 ID: [英語名, 日本語名, セキュリティ, …]}
    blocked: 通れないゲートの区間 {edge(a, b)}
    max_low: セキュリティが min_sec に足りない星系（ローセクなど。ヌルセクは除く）を、途中で何か所まで通ってよいか
    「いる星系 × 足りない星系を通った数」を状態にした幅優先探索なので、上限を守るなかで一番短いルートになる。
    """
    avoid = set(avoid) - {origin, dest}

    def cost(sid):
        """その星系に入ると「足りない星系」を何か所使うか（入れないなら None）。"""
        if sid == dest:
            return 0
        info = systems.get(sid)
        if info is None or sid in avoid:
            return None
        sec = display_security(info[2])
        if sec >= min_sec:
            return 0
        return 1 if sec > 0 else None  # ヌルセク・ワームホールなどは通らない

    start = (origin, 0)
    prev = {start: None}
    queue = deque([start])
    while queue:
        state = queue.popleft()
        sid, used = state
        if sid == dest:
            route = []
            while state is not None:
                route.append(state[0])
                state = prev[state]
            return route[::-1]
        for nxt in gates.get(sid, {}):
            c = cost(nxt)
            if c is None or used + c > max_low or edge(sid, nxt) in blocked:
                continue
            key = (nxt, used + c)
            if key not in prev:
                prev[key] = state
                queue.append(key)
    return None


def waypoints_for(route, game_route):
    """ゲームのオートパイロットに route どおり進ませるための経由地（最後は目的地）。

    game_route(a, b): ゲームが a → b に選ぶルート（星系 ID の並び）。ゲームのルートが route と同じになる
    一番遠い星系を二分探索で探し、そこを経由地にして先へ進む。
    """
    points = []
    start = 0
    last = len(route) - 1
    while start < last:
        lo, hi = start + 1, last  # route[start..lo] は 1 ジャンプなので必ず一致する
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if game_route(route[start], route[mid]) == route[start:mid + 1]:
                lo = mid
            else:
                hi = mid - 1
        points.append(route[lo])
        start = lo
    return points


def distances(gates, systems, origin, min_sec, blocked=frozenset(), max_low=0, limit=None):
    """origin から各星系までの最小ジャンプ数 {星系 ID: ジャンプ数}（shortest と同じ通り方の決まり）。limit ジャンプまで。"""
    def cost(sid):
        info = systems.get(sid)
        if info is None:
            return None
        sec = display_security(info[2])
        if sec >= min_sec:
            return 0
        return 1 if sec > 0 else None

    best = {origin: 0}
    seen = {(origin, 0)}
    queue = deque([(origin, 0, 0)])
    while queue:
        sid, used, jumps = queue.popleft()
        if limit is not None and jumps >= limit:
            continue
        for nxt in gates.get(sid, {}):
            c = cost(nxt)
            if c is None or used + c > max_low or edge(sid, nxt) in blocked or (nxt, used + c) in seen:
                continue
            seen.add((nxt, used + c))
            best.setdefault(nxt, jumps + 1)
            queue.append((nxt, used + c, jumps + 1))
    return best


def open_tour(start, points, dist):
    """start から points をすべて回る順番（戻らない一筆書き）。dist(a, b) = ジャンプ数（行けなければ None）。

    最近傍法で作ってから 2-opt で区間の向きを入れ替えて縮める（数十か所なら一瞬）。行けない星系は unreachable に入れる。
    戻り値: (順番, 合計ジャンプ数, 行けない星系)
    """
    points = list(dict.fromkeys(p for p in points if p != start))
    unreachable = [p for p in points if dist(start, p) is None]
    left = [p for p in points if p not in unreachable]
    order = []
    here = start
    while left:
        nxt = min(left, key=lambda p: (dist(here, p) if dist(here, p) is not None else float("inf"), p))
        if dist(here, nxt) is None:  # ここからは行けない（別の場所からなら行ける）: 最後に回す
            unreachable += left
            break
        order.append(nxt)
        left.remove(nxt)
        here = nxt

    def total(path):
        legs = [dist(a, b) for a, b in zip([start, *path], path)]
        return None if any(x is None for x in legs) else sum(legs)

    improved = True
    while improved and len(order) > 2:
        improved = False
        for i in range(len(order) - 1):
            for k in range(i + 1, len(order)):
                cand = order[:i] + order[i:k + 1][::-1] + order[k + 1:]
                t, now = total(cand), total(order)
                if t is not None and now is not None and t < now:
                    order, improved = cand, True
    return order, total(order) or 0, unreachable


class OverCapacity(ValueError):
    """積み込み済みの荷物だけでカーゴの容量を超えている。"""


URGENT_WEIGHT = 2.0  # 緊急の荷物の受取・配達が 1 ジャンプ遅れるごとに、ジャンプ数にこれだけ足して比べる


def pdp_tour(start, tasks, dist, volumes=None, capacity=None, urgent=None):
    """受取と配達の順番（Pickup and Delivery Problem）。どの荷物も「受取場所 → その配達先」の順に回る。

    tasks: [(受取場所 or None, 配達先)]（None = すでに積んでいる）、dist(a, b) = ジャンプ数（行けなければ None）。
    volumes・capacity: 荷物の体積とカーゴの容量（m³）。どの時点でも積んでいる合計が容量を超えない順番にする
    （一度に積めなければ、途中で配達して空けてから次を受け取りに行く）。capacity が無ければ容量は考えない。
    urgent: 緊急の荷物（True/False の並び）。比べる値は「合計ジャンプ数 + URGENT_WEIGHT × 緊急の荷物の受取・配達までの
    ジャンプ数の合計」なので、合計ジャンプ数が少し増えても、緊急の荷物を早く受け取り・届ける順番になる。
    近い場所から順に作り（配達は受取のあとだけ、受取は空きがあるときだけ選べる）、1 か所ずつ動かす・区間を逆向きにするで縮める。
    戻り値: (順番 [("P" or "D", 荷物の番号, 星系)], 合計ジャンプ数, 行けない荷物の番号)
    容量より大きい荷物は「行けない荷物」に入れる。積み込み済みの荷物だけで容量を超えるときは OverCapacity。
    """
    volumes = volumes or [0] * len(tasks)
    urgent = urgent or [False] * len(tasks)
    cap = capacity if capacity and capacity > 0 else float("inf")

    def reach(s):
        return s == start or dist(start, s) is not None
    unreachable = [i for i, (p, d) in enumerate(tasks)
                   if not reach(d) or (p is not None and not reach(p)) or volumes[i] > cap]
    loaded = {i for i, (p, _) in enumerate(tasks) if p is None and i not in unreachable}
    initial = sum(volumes[i] for i in loaded)
    if initial > cap:
        raise OverCapacity(initial)
    nodes = [(kind, i, s) for i, (p, d) in enumerate(tasks) if i not in unreachable
             for kind, s in (("P", p), ("D", d)) if s is not None]

    def leg(a, b):
        x = dist(a, b)
        return x if x is not None else 10 ** 6  # 片道だけ行けない区間（ふつうは無い）は大きな値

    def jumps(seq):
        return sum(leg(a, n[2]) for a, n in zip([start, *[n[2] for n in seq]], seq))

    def cost(seq):
        """比べる値: 合計ジャンプ数 + 緊急の荷物の受取・配達が遅いほど増える分。"""
        total = delay = 0
        here = start
        for _, i, system in seq:
            total += leg(here, system)
            here = system
            if urgent[i]:
                delay += total
        return total + URGENT_WEIGHT * delay

    def feasible(seq):
        picked, load = set(loaded), initial
        for kind, i, _ in seq:
            if kind == "P":
                picked.add(i)
                load += volumes[i]
                if load > cap:
                    return False
            elif i not in picked:
                return False
            else:
                load -= volumes[i]
        return True

    # 近い順に作る（緊急の荷物は近いとみなして先に。同じ距離なら配達を先に: 荷物を早く降ろしてカーゴを空ける）
    seq, here, left, picked, load = [], start, list(nodes), set(loaded), initial
    while left:
        ok = [n for n in left if (n[0] == "P" and load + volumes[n[1]] <= cap) or (n[0] == "D" and n[1] in picked)]
        n = min(ok, key=lambda n: (leg(here, n[2]) / (1 + URGENT_WEIGHT * len(left)) if urgent[n[1]] else leg(here, n[2]),
                                   n[0] != "D"))
        seq.append(n)
        left.remove(n)
        if n[0] == "P":
            picked.add(n[1])
            load += volumes[n[1]]
        else:
            load -= volumes[n[1]]
        here = n[2]

    best = cost(seq)
    improved = True
    while improved:
        improved = False
        # 1 か所を別の位置へ動かす
        for a in range(len(seq)):
            rest = seq[:a] + seq[a + 1:]
            for b in range(len(rest) + 1):
                if b == a:
                    continue
                cand = rest[:b] + [seq[a]] + rest[b:]
                if feasible(cand) and (c := cost(cand)) < best:
                    seq, best, improved = cand, c, True
                    break
            if improved:
                break
        if improved:
            continue
        # 区間を逆向きにする（2-opt）
        for i in range(len(seq) - 1):
            for k in range(i + 1, len(seq)):
                cand = seq[:i] + seq[i:k + 1][::-1] + seq[k + 1:]
                if feasible(cand) and (c := cost(cand)) < best:
                    seq, best, improved = cand, c, True
                    break
            if improved:
                break
    return seq, jumps(seq), unreachable
