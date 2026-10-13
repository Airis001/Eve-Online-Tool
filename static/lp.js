"use strict";
// LP の換金: 持っている LP で、どの交換品を交換して売るのが良いか（1 LP あたりの利益と直近の取引量から）

const LP_KEY = "lp:params";
let characters = [];
let groups = [];
let ids = new Set();
let corps = [];
let store = null;

const num = (sel) => Number($(sel).value) || 0;
const corpEntry = () => corps.find((c) => c.corporation_id === Number($("#lp-corp").value));

function saveParams() {
  saveJson(LP_KEY, { corp: Number($("#lp-corp").value) || null, hub: Number($("#lp-hub").value) || null, method: $("#lp-method").value,
    days: $("#lp-days").value, share: $("#lp-share").value, min_volume: $("#lp-min-volume").value, sort: $("#lp-sort").value });
}

// 使える LP: 「使う LP」の入力があればそれ（1 人分として扱う）、無ければキャラクターごとの LP
function buckets() {
  const manual = $("#lp-points").value.trim();
  if (manual !== "") return [{ name: null, points: Math.max(Number(manual) || 0, 0) }];
  return (corpEntry()?.by_character || []).map((b) => ({ name: b.character_name, points: b.points }));
}

// 交換品ごとの数字（売り方・日数・割合で変わる）
function evaluate(o, lp) {
  const net = $("#lp-method").value === "instant" ? o.instant : o.listed;
  const perLp = net != null ? net / o.lp_cost : null;
  const exchanges = lp.reduce((s, b) => s + Math.floor(b.points / o.lp_cost), 0);
  const perDay = (o.volume || 0) * num("#lp-share") / 100;  // 自分が 1 日に売れる数の目安
  const sellable = Math.floor(perDay * num("#lp-days") / o.quantity);  // 期間内に売れる交換回数
  const fraction = exchanges ? Math.min(exchanges, sellable) / exchanges : (sellable >= 1 ? 1 : 0);
  return { ...o, net, perLp, exchanges, sellable, perDay, score: perLp != null ? perLp * fraction : null,
    sellDays: perDay > 0 ? exchanges * o.quantity / perDay : null, total: net != null ? net * exchanges : null };
}

// LP を、1 LP あたりの利益が高い順に、期間内に売れる数まで割り当てる（キャラクターごとに）
function makePlan(items, lp) {
  const left = lp.map((b) => ({ ...b }));
  const plan = [];
  const usable = items.filter((i) => i.perLp > 0 && !i.missing_required && (i.volume || 0) >= num("#lp-min-volume"))
    .sort((a, b) => b.perLp - a.perLp);
  for (const i of usable) {
    let want = i.sellable;
    const by = [];
    for (const b of left) {
      const k = Math.min(want, Math.floor(b.points / i.lp_cost));
      if (k <= 0) continue;
      b.points -= k * i.lp_cost;
      want -= k;
      by.push({ name: b.name, count: k });
      if (!want) break;
    }
    const count = by.reduce((s, b) => s + b.count, 0);
    if (count) plan.push({ item: i, count, by, lp: count * i.lp_cost, cost: count * i.cost, profit: count * i.net });
  }
  return { plan, left: left.reduce((s, b) => s + b.points, 0) };
}

function priceCell(o) {
  const flag = (out) => (out ? ` <small class="warn-text" title="${esc(tr("実際の取引価格（7 日平均）から大きく外れた注文なので、計算に使いません"))}">⚠</small>` : "");
  return `${o.sell != null ? fmtIsk(o.sell) : "-"}${flag(o.listed_out)}<br><small class="muted">${tr("買 {0}", o.buy != null ? fmtIsk(o.buy) : "-")}${flag(o.instant_out)}</small>
    ${o.average != null ? `<br><small class="muted">${tr("平均 {0}", fmtIsk(o.average))}</small>` : ""}`;
}

function nameCell(o) {
  const req = o.required.length
    ? `<br><small class="${o.missing_required ? "warn-text" : "muted"}">${tr("必要: {0}", o.required.map((r) => `${esc(nm(r))} ×${fmtNum(r.quantity)}`).join(LIST_SEP))}</small>` : "";
  return `<b>${esc(nm(o))}</b>${o.quantity > 1 ? ` ×${fmtNum(o.quantity)}` : ""}<br><small class="muted">${nmSub(o)}</small>${req}`;
}

function costCell(o) {
  const extra = o.cost - o.isk_cost;
  return `${fmtNum(o.lp_cost)} LP${o.isk_cost ? `<br><small class="muted">+ ${fmtIsk(o.isk_cost)} ISK</small>` : ""}${extra > 0 ? `<br><small class="muted">${tr("+ アイテム {0}", fmtIsk(extra))}</small>` : ""}`;
}

const perLpText = (v) => (v == null ? "-" : `<span class="${v > 0 ? "" : "warn-text"}">${fmtNum(Math.round(v))}</span>`);

function render() {
  if (!store) return;
  saveParams();
  const lp = buckets();
  const totalLp = lp.reduce((s, b) => s + b.points, 0);
  const items = store.offers.map((o) => evaluate(o, lp));
  const { plan, left } = makePlan(items, lp);
  const used = plan.reduce((s, p) => s + p.lp, 0);
  const cost = plan.reduce((s, p) => s + p.cost, 0);
  const profit = plan.reduce((s, p) => s + p.profit, 0);
  const corp = corpEntry();
  const holders = corp && $("#lp-points").value.trim() === "" ? corp.by_character.map((b) => `${esc(b.character_name)} ${fmtNum(b.points)}`).join(" · ") : "";

  $("#lp-summary").innerHTML = `<div class="stat-row">
      <div class="stat-card total"><small class="muted">${tr("使える LP（{0}）", esc(store.name))}</small><b>${fmtNum(totalLp)} LP</b>${holders ? `<small class="muted">${holders}</small>` : ""}</div>
      <div class="stat-card"><small class="muted">${tr("プランで使う LP")}</small><b>${fmtNum(used)} LP</b><small class="muted">${tr("余り {0} LP", fmtNum(left))}</small></div>
      <div class="stat-card"><small class="muted">${tr("交換に必要な ISK")}</small><b>${fmtIsk(cost)} ISK</b><small class="muted">${tr("ISK とアイテムの代金")}</small></div>
      <div class="stat-card"><small class="muted">${tr("プランの利益（手数料込み）")}</small><b class="ok-text">${fmtIsk(profit)} ISK</b>
        <small class="muted">${used ? tr("平均 {0} ISK/LP", fmtNum(Math.round(profit / used))) : ""}</small></div></div>
    <p class="muted small-note">${tr("{0} の価格と取引量 · 手数料（{1}）売上税 {2}・仲介手数料 {3} · 交換品 {4} 件のうち、見込みの高い {5} 件を調べました（設計図 {6} 件は除外）", esc(store.hub), esc(store.trader || "-"), fmtPct(store.tax, 2), fmtPct(store.broker, 2), fmtNum(store.total_offers), fmtNum(store.offers.length), fmtNum(store.skipped))}</p>`;

  const planRows = plan.map((p) => `<tr><td>${nameCell(p.item)}</td>
      <td class="r num"><b>${fmtNum(p.count)}</b><br><small class="muted">${tr("{0} 個", fmtNum(p.count * p.item.quantity))}</small>${p.by.length > 1 || p.by[0]?.name ? `<br><small class="muted">${p.by.map((b) => `${esc(b.name || "")} ${fmtNum(b.count)}`).join(" · ")}</small>` : ""}</td>
      <td class="r num">${fmtNum(p.lp)} LP${p.cost ? `<br><small class="muted">${fmtIsk(p.cost)} ISK</small>` : ""}</td>
      <td class="r num">${fmtNum(Math.round(p.item.perLp))}</td>
      <td class="r num ok-text"><b>+${fmtIsk(p.profit)}</b></td>
      <td class="r num">${p.item.perDay > 0 ? tr("{0} 日", fmtNum(Math.ceil(p.count * p.item.quantity / p.item.perDay))) : "-"}</td>
      <td><a class="btn small" href="/market?type_id=${p.item.type_id}" title="${esc(tr("マーケットで見る"))}">🛒</a></td></tr>`).join("");
  $("#lp-plan").innerHTML = totalLp <= 0
    ? `<p class="muted">${tr("このコーポの LP を持っていません。「使う LP」に数を入れると、その LP で計算します。")}</p>`
    : `<div class="table-scroll"><table class="orders"><thead><tr><th>${tr("交換品")}</th><th class="r">${tr("交換する回数")}</th><th class="r">${tr("使う LP")}<br><small>${tr("必要な ISK")}</small></th>
        <th class="r">ISK / LP</th><th class="r">${tr("利益")}</th><th class="r">${tr("売り切るまで")}</th><th></th></tr></thead>
      <tbody>${planRows || `<tr><td colspan="7" class="muted">${tr("条件に合う交換品がありません")}</td></tr>`}</tbody></table></div>`;

  const sortKey = { score: (i) => i.score, per_lp: (i) => i.perLp, volume: (i) => i.volume, orders: (i) => i.orders, total: (i) => i.total }[$("#lp-sort").value];
  const minVolume = num("#lp-min-volume");
  const shown = items.filter((i) => (i.volume || 0) >= minVolume)
    .sort((a, b) => (sortKey(b) ?? -Infinity) - (sortKey(a) ?? -Infinity));
  const instant = $("#lp-method").value === "instant";
  const rows = shown.map((i) => `<tr><td>${nameCell(i)}</td><td class="r num">${costCell(i)}</td><td class="r num">${priceCell(i)}</td>
      <td class="r num"><b>${perLpText(i.perLp)}</b><br><small class="muted">${instant ? tr("売り注文 {0}", perLpText(i.listed != null ? i.listed / i.lp_cost : null)) : tr("すぐ売る {0}", perLpText(i.instant != null ? i.instant / i.lp_cost : null))}</small></td>
      <td class="r num">${i.volume != null ? fmtNum(Math.round(i.volume)) : "-"}${(i.volume || 0) < 1 ? `<br><small class="warn-text">${tr("ほぼ売れない")}</small>` : ""}</td>
      <td class="r num">${i.orders != null ? fmtNum(Math.round(i.orders)) : "-"}</td>
      <td class="r num">${fmtNum(i.exchanges)}<br><small class="muted">${i.sellDays != null && i.exchanges ? tr("売り切るまで {0} 日", fmtNum(Math.ceil(i.sellDays))) : ""}</small></td>
      <td class="r num">${i.total != null ? `<span class="${i.total > 0 ? "ok-text" : "warn-text"}">${fmtIsk(i.total)}</span>` : "-"}</td>
      <td><a class="btn small" href="/market?type_id=${i.type_id}" title="${esc(tr("マーケットで見る"))}">🛒</a></td></tr>`).join("");
  $("#lp-offers").innerHTML = `<div class="table-scroll"><table class="orders"><thead><tr><th>${tr("交換品")}</th><th class="r">${tr("費用")}</th><th class="r">${tr("{0} の価格", esc(store.hub))}<br><small>${tr("最安の売り値 / 最高の買い値")}</small></th>
      <th class="r">ISK / LP<br><small>${tr("手数料込み")}</small></th><th class="r">${tr("1 日の取引量")}<br><small>${tr("直近 {0} 日の平均", store.recent_days)}</small></th>
      <th class="r">${tr("1 日の取引件数")}<br><small>${tr("直近 {0} 日の平均", store.recent_days)}</small></th><th class="r">${tr("交換できる回数")}</th>
      <th class="r">${tr("LP をすべて使ったとき")}<br><small>${tr("利益")}</small></th><th></th></tr></thead>
    <tbody>${rows || `<tr><td colspan="9" class="muted">${tr("条件に合う交換品がありません")}</td></tr>`}</tbody></table></div>
    <p class="muted small-note">${tr("「売り注文」は最安より 0.01 ISK 安く出品する場合（売上税＋仲介手数料、売れるまで待つ）、「すぐ売る」は買い注文に売る場合（売上税のみ）の、1 LP あたりの利益です。交換に必要な ISK と、必要なアイテムを売り先で買う代金を引いています。取引量・取引件数は売り先の地域の ESI の履歴です（当日の分は翌日に反映されます）。")}</p>`;
}

async function loadStore() {
  const corp = Number($("#lp-corp").value);
  store = null;
  if (!corp) {
    $("#lp-summary").innerHTML = "";
    $("#lp-plan").innerHTML = `<p class="muted">${tr("LP を持っていません。")}</p>`;
    $("#lp-offers").innerHTML = "";
    return;
  }
  $("#lp-plan").innerHTML = `<p class="muted">${tr("LP ストアと価格・取引量を読み込んでいます…（初回は 30 秒ほどかかります）")}</p>`;
  $("#lp-offers").innerHTML = "";
  try {
    const d = await request("GET", `/api/lp/store?corp_id=${corp}&hub=${$("#lp-hub").value}`);
    if (Number($("#lp-corp").value) !== corp) return;  // 読み込み中に選び直された
    store = d;
    render();
  } catch (e) {
    $("#lp-plan").innerHTML = `<div class="warn">${esc(e.message)}</div>`;
  }
}

async function loadCorps() {
  $("#lp-summary").innerHTML = "";
  $("#lp-plan").innerHTML = `<p class="muted">${tr("読み込み中…")}</p>`;
  try {
    const d = await request("GET", `/api/lp/corps?${idsQuery(ids)}`);
    corps = [...d.corporations, ...d.others];
    const saved = loadJson(LP_KEY, null) || {};
    const current = Number($("#lp-corp").value) || Number(new URLSearchParams(location.search).get("corp")) || saved.corp;
    const held = d.corporations.map((c) => `<option value="${c.corporation_id}">${esc(c.name)} · ${fmtNum(c.total)} LP</option>`).join("");
    const others = d.others.map((c) => `<option value="${c.corporation_id}">${esc(c.name)}</option>`).join("");
    $("#lp-corp").innerHTML = (held ? `<optgroup label="${esc(tr("LP を持っているコーポ"))}">${held}</optgroup>` : "")
      + (others ? `<optgroup label="${esc(tr("ほかのコーポ"))}">${others}</optgroup>` : "");
    if (corps.some((c) => c.corporation_id === current)) $("#lp-corp").value = current;
    if (!$("#lp-hub").options.length) {
      $("#lp-hub").innerHTML = d.hubs.map((h) => `<option value="${h.station_id}">${esc(h.name)}</option>`).join("");
      if (saved.hub && d.hubs.some((h) => h.station_id === saved.hub)) $("#lp-hub").value = saved.hub;
    }
    $("#lp-errors").innerHTML = charErrors(d.characters);
    await loadStore();
  } catch (e) {
    $("#lp-plan").innerHTML = `<div class="warn">${esc(e.message)}</div>`;
  }
}

$("#lp-corp").addEventListener("change", loadStore);
$("#lp-hub").addEventListener("change", loadStore);
$("#lp-reload").addEventListener("click", loadCorps);
for (const sel of ["#lp-method", "#lp-days", "#lp-sort"]) $(sel).addEventListener("change", render);
for (const sel of ["#lp-points", "#lp-share", "#lp-min-volume"]) $(sel).addEventListener("input", render);

(async () => {
  const saved = loadJson(LP_KEY, null) || {};
  const lpParam = new URLSearchParams(location.search).get("lp");
  if (lpParam) $("#lp-points").value = lpParam;
  for (const [sel, key] of [["#lp-method", "method"], ["#lp-days", "days"], ["#lp-share", "share"], ["#lp-min-volume", "min_volume"], ["#lp-sort", "sort"]]) {
    if (saved[key] != null) $(sel).value = saved[key];
  }
  try {
    const d = await request("GET", "/api/characters");
    characters = d.characters;
    groups = d.groups;
    ids = renderCharFilter($("#char-filter"), characters, groups, (next) => { ids = next; loadCorps(); });
    loadCorps();
  } catch (e) {
    toast(e.message, "error");
  }
})();
