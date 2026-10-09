"use strict";
// マーケット: 取引拠点の相場の比較と、キャラクターのスキルを加味した転売の判定

const COMPARE_KEY = "market:compare-locations";
const FEES_KEY = "market:fees";
const TRADE_CHAR_KEY = "market:trade-character";

// 初期値は EVE のスキル説明（Accounting: 売上税 7.5% を 1 レベルごとに 11% 軽減。
// Broker Relations: NPC ステーションの仲介手数料 3% から 1 レベルごとに 0.3 ポイント軽減）
const DEFAULT_FEES = { baseTax: 7.5, accountingPerLevel: 11, baseBroker: 3.0, brokerPerLevel: 0.3, structureBroker: "" };
const BASE_ORDER_LIMIT = 5;
const STRUCTURE_MIN_ID = 1_000_000_000_000;
const PLEX_TYPE_ID = 44992;

let locations = null;       // /api/market/locations
let characters = [];
let watchlist = [];
let compareData = null;     // /api/market/compare
let detailItem = null;
let detailLocation = null;
let searchTimer = null;
let fees = { ...DEFAULT_FEES, ...loadJson(FEES_KEY, {}) };
let standings = {};         // NPC ステーション ID → スタンディングによる仲介手数料の軽減
let standingsScope = false; // スタンディングの権限が無い（再ログインが必要）

// ---------- 場所 ----------

const allLocations = () => [...(locations?.hubs || []), ...(locations?.owned || [])];
const locLabel = (loc) => loc.short || loc.name;
const isStructure = (id) => id >= STRUCTURE_MIN_ID;

function selectedLocationIds() {
  const saved = loadJson(COMPARE_KEY, null);
  const valid = new Set(allLocations().map((l) => l.id));
  const ids = (saved || locations.hubs.map((h) => h.id)).filter((id) => valid.has(id));
  return ids.length ? ids : locations.hubs.map((h) => h.id);
}

function renderLocationChecks() {
  const chosen = new Set(selectedLocationIds());
  const box = (l) => `<label class="fcheck"><input type="checkbox" data-loc="${l.id}" ${chosen.has(l.id) ? "checked" : ""}>
    ${isStructure(l.id) ? "🏰 " : ""}${esc(locLabel(l))}</label>`;
  const owned = locations.owned.length
    ? `<div class="sub-label">${tr("艦が置いてある場所")}</div><div class="fchecks">${locations.owned.map(box).join("")}</div>` : "";
  $("#location-checks").innerHTML = `<div class="fchecks">${locations.hubs.map(box).join("")}</div>${owned}`;
  $("#structure-note").hidden = locations.structure_markets || !locations.owned.some((l) => isStructure(l.id));
}

// ---------- 手数料 ----------

function tradeCharacter() {
  const id = Number($("#trade-char").value);
  return characters.find((c) => c.character_id === id);
}

// 選んだキャラクターの売上税・仲介手数料（%）
function feeRates(locationId) {
  const skills = tradeCharacter()?.trade_skills || {};
  const tax = Math.max(fees.baseTax * (1 - (fees.accountingPerLevel / 100) * (skills.accounting || 0)), 0);
  const npcBroker = Math.max(fees.baseBroker - fees.brokerPerLevel * (skills.broker_relations || 0), 0);
  const reduction = standings[locationId]?.reduction || 0;
  const broker = isStructure(locationId) && fees.structureBroker !== "" && fees.structureBroker != null
    ? Number(fees.structureBroker) : Math.max(npcBroker - reduction, 0);
  return { tax, broker, npcBroker };
}

function orderLimit(skills) {
  return BASE_ORDER_LIMIT + 4 * (skills.trade || 0) + 8 * (skills.retail || 0) + 16 * (skills.wholesale || 0) + 32 * (skills.tycoon || 0);
}

function renderFeeSummary() {
  const c = tradeCharacter();
  if (!c) { $("#fee-summary").innerHTML = `<span class="muted">${tr("キャラクターのデータがありません。")}</span>`; return; }
  const s = c.trade_skills;
  const { tax, npcBroker } = feeRates(0);
  $("#fee-summary").innerHTML = `
    <div><span class="muted">${tr("売上税")}</span> <b>${fmtPct(tax, 3)}</b> <span class="muted">${tr("（Accounting {0}）", ROMAN[s.accounting])}</span></div>
    <div><span class="muted">${tr("仲介手数料（NPC）")}</span> <b>${fmtPct(npcBroker, 3)}</b> <span class="muted">${tr("（Broker Relations {0}）", ROMAN[s.broker_relations])}</span></div>
    <div><span class="muted">${tr("スタンディングの軽減")}</span> ${standingsText()}</div>
    <div><span class="muted">${tr("注文数の上限")}</span> <b>${orderLimit(s)}</b> <span class="muted">${tr("（Trade {0}・Retail {1}・Wholesale {2}・Tycoon {3}）", ROMAN[s.trade], ROMAN[s.retail], ROMAN[s.wholesale], ROMAN[s.tycoon])}</span></div>`;
  document.querySelectorAll("[data-fee]").forEach((i) => { i.value = fees[i.dataset.fee]; });
}

function standingsText() {
  if (standingsScope) return `${tr("<a href=\"/login\">再ログイン</a>が必要")}`;
  const entries = Object.entries(standings).filter(([, st]) => Math.abs(st.reduction) > 0.0005);
  if (!entries.length) return `<span class="muted">${tr("なし")}</span>`;
  return entries.map(([id, st]) => {
    const loc = allLocations().find((l) => String(l.id) === id) || { name: id };
    return `${esc(locLabel(loc))} ${st.reduction >= 0 ? "−" : "+"}${fmtPct(Math.abs(st.reduction), 3)}`;
  }).join(DOT_SEP);
}

async function loadStandings() {
  const c = tradeCharacter();
  standings = {};
  standingsScope = false;
  if (!c) return;
  const stations = allLocations().filter((l) => !isStructure(l.id)).map((l) => l.id);
  try {
    const d = await request("GET", `/api/market/standings?character_id=${c.character_id}&locations=${stations.join(",")}`);
    standings = d.locations;
    standingsScope = Boolean(d.needs_scope);
  } catch { /* 取れなくても手数料はスキルだけで計算する */ }
  renderFeeSummary();
  renderTrades();
}

// ---------- 比較リスト・相場 ----------

async function loadCompare() {
  const box = $("#compare");
  if (!watchlist.length) {
    compareData = null;
    box.innerHTML = `<div class="card empty-card">${tr("上の検索でアイテムを選ぶと、比較リストに追加されます。")}</div>`;
    renderTrades();
    return;
  }
  box.innerHTML = `<span class="muted">${tr("相場を取得しています…")}</span>`;
  const locs = selectedLocationIds();
  try {
    compareData = await request("GET", `/api/market/compare?type_ids=${watchlist.map((w) => w.type_id).join(",")}&locations=${locs.join(",")}`);
  } catch (e) {
    box.innerHTML = `<div class="warn">${esc(e.message)}</div>`;
    return;
  }
  renderCompare();
  renderTrades();
}

const priceAt = (locId, typeId) => compareData?.prices[locId]?.[typeId] || { sell: null, buy: null };

function renderCompare() {
  const d = compareData;
  const locs = d.locations;
  const errors = Object.entries(d.errors).map(([id, msg]) =>
    `<div class="warn">${esc(locLabel(allLocations().find((l) => String(l.id) === id) || { name: id }))}: ${esc(msg)}</div>`).join("");
  let html = `<div class="table-scroll"><table class="matrix compare-table"><thead><tr><th>${tr("アイテム")}</th><th class="r">${tr("体積")}</th>`;
  html += locs.map((l) => `<th class="r">${esc(locLabel(allLocations().find((x) => x.id === l.id) || l))}</th>`).join("");
  html += `<th></th></tr></thead><tbody>`;
  for (const w of watchlist) {
    const t = String(w.type_id);
    const item = d.items[t] || w;
    const sells = locs.map((l) => priceAt(l.id, t).sell?.price).filter((v) => v != null);
    const buys = locs.map((l) => priceAt(l.id, t).buy?.price).filter((v) => v != null);
    const minSell = Math.min(...sells);
    const maxBuy = Math.max(...buys);
    const noOrders = !sells.length && !buys.length
      ? `<small class="warn-text">${tr("どの場所にも注文がありません{0}", w.type_id === PLEX_TYPE_ID ? tr("（PLEX はゲーム内の共通 PLEX マーケットで取引され、ESI の地域マーケットには出ません）") : "")}</small>` : "";
    html += `<tr><td class="item"><button class="link item-link" type="button" data-action="detail" data-id="${t}">${esc(nm(item))}</button><small>${nmSub(item)}</small>${noOrders}</td>
      <td class="r num muted">${item.volume != null ? `${fmtNum(item.volume)} m³` : "-"}</td>`;
    html += locs.map((l) => {
      const p = priceAt(l.id, t);
      const sell = p.sell ? `<span class="${p.sell.price === minSell ? "best-sell" : ""}" title="${tr("{0}・{1} 個", esc(fullIsk(p.sell.price)), fmtNum(p.sell.total_volume))}">${tr("売 {0}", fmtIsk(p.sell.price))}</span>` : `<span class="muted">${tr("売 -")}</span>`;
      const buy = p.buy ? `<span class="${p.buy.price === maxBuy ? "best-buy" : ""}" title="${tr("{0}・{1} 個", esc(fullIsk(p.buy.price)), fmtNum(p.buy.total_volume))}">${tr("買 {0}", fmtIsk(p.buy.price))}</span>` : `<span class="muted">${tr("買 -")}</span>`;
      return `<td class="r num price-cell">${sell}<br>${buy}</td>`;
    }).join("");
    html += `<td class="rm"><button class="icon-btn" type="button" title="${tr("比較リストから外す")}" data-action="remove" data-id="${t}">×</button></td></tr>`;
  }
  $("#compare").innerHTML = errors + html + `</tbody></table></div>
    <p class="muted small-note"><span class="best-sell">${tr("緑")}</span> ${tr("= 一番安く買える場所、")}<span class="best-buy">${tr("青")}</span> ${tr("= 一番高く売れる場所（買い注文）。")}</p>`;
}

// ---------- 転売の判定 ----------

// 1 アイテムについて、3 通りの転売のうち利益が最大になる場所の組み合わせを探す
function bestTrades(typeId) {
  const locs = compareData.locations.map((l) => l.id);
  const t = String(typeId);
  let instant = null;
  let listing = null;
  let station = null;
  for (const a of locs) {
    const pa = priceAt(a, t);
    for (const b of locs) {
      const pb = priceAt(b, t);
      const rb = feeRates(b);
      // 即売り: a の最安の売り注文から買い、b の最高の買い注文に売る（売上税のみ）
      if (pa.sell && pb.buy) {
        const profit = pb.buy.price * (1 - rb.tax / 100) - pa.sell.price;
        if (!instant || profit > instant.profit) {
          instant = { from: a, to: b, buy: pa.sell.price, sell: pb.buy.price, profit,
            qty: Math.min(pa.sell.volume, pb.buy.volume) };
        }
      }
      // 出品: a で買い、b に最安値と同じ価格で売り注文を出す（売上税 + 仲介手数料）
      if (a !== b && pa.sell && pb.sell) {
        const profit = pb.sell.price * (1 - (rb.tax + rb.broker) / 100) - pa.sell.price;
        if (!listing || profit > listing.profit) {
          listing = { from: a, to: b, buy: pa.sell.price, sell: pb.sell.price, profit, qty: pa.sell.volume };
        }
      }
    }
    // ステーション内: a で買い注文（仲介手数料）→ 売り注文（売上税 + 仲介手数料）
    if (pa.sell && pa.buy) {
      const r = feeRates(a);
      const cost = pa.buy.price * (1 + r.broker / 100);
      const profit = pa.sell.price * (1 - (r.tax + r.broker) / 100) - cost;
      if (!station || profit > station.profit) {
        station = { from: a, to: a, buy: cost, sell: pa.sell.price, profit, orders: { sell: pa.sell.orders, buy: pa.buy.orders } };
      }
    }
  }
  for (const deal of [instant, listing, station]) {
    if (deal) deal.margin = (deal.profit / deal.buy) * 100;
  }
  return { instant, listing, station };
}

function tradeCell(tr, volume, kind) {
  if (!tr) return `<td class="muted">${tr("注文なし")}</td>`;
  const name = (id) => esc(locLabel(allLocations().find((l) => l.id === id) || { name: String(id) }));
  const route = tr.from === tr.to ? name(tr.from) : `${name(tr.from)} → ${name(tr.to)}`;
  const cls = tr.profit > 0 ? "profit" : "loss";
  const perM3 = kind !== "station" && tr.from !== tr.to && volume ? `<small>${tr("1 m³ あたり {0} ISK", fmtIsk(tr.profit / volume))}</small>` : "";
  const qty = tr.qty != null ? `<small>${tr("最良価格の数量 {0} 個", fmtNum(tr.qty))}</small>` : "";
  const orders = tr.orders ? `<small class="${Math.min(tr.orders.sell, tr.orders.buy) < 5 ? "warn-text" : "muted"}">${tr("注文件数 売 {0}・買 {1}{2}", tr.orders.sell, tr.orders.buy, (Math.min(tr.orders.sell, tr.orders.buy) < 5 ? tr("（少ない）") : ""))}</small>` : "";
  return `<td class="trade-cell ${cls}"><b>${tr.profit > 0 ? "+" : ""}${fmtIsk(tr.profit)} ISK</b> <span>(${fmtPct(tr.margin, 1)})</span>
    <small>${route}</small><small class="muted">${tr("買 {0} → 売 {1}", fmtIsk(tr.buy), fmtIsk(tr.sell))}</small>${perM3}${qty}${orders}</td>`;
}

function renderTrades() {
  const box = $("#trades");
  if (!compareData || !watchlist.length) { box.innerHTML = ""; return; }
  if (!tradeCharacter()) { box.innerHTML = `<div class="card empty-card">${tr("キャラクターを登録すると、スキルを加味して判定できます。")}</div>`; return; }
  const rows = watchlist.map((w) => {
    const t = String(w.type_id);
    const item = compareData.items[t] || w;
    const best = bestTrades(t);
    const any = [best.instant, best.listing, best.station].some((deal) => deal && deal.profit > 0);
    return { any, html: `<tr><td class="item">${esc(nm(item))}${any ? ` <span class="badge ok">${tr("転売可能")}</span>` : ""}</td>
      ${tradeCell(best.instant, item.volume, "instant")}${tradeCell(best.listing, item.volume, "listing")}${tradeCell(best.station, item.volume, "station")}</tr>` };
  });
  rows.sort((a, b) => b.any - a.any);
  box.innerHTML = `<div class="table-scroll"><table class="matrix trade-table"><thead><tr><th>${tr("アイテム")}</th>
    <th>${tr("即売り（買い注文に売る）")}</th><th>${tr("出品（売り注文を出す）")}</th><th>${tr("ステーション内トレード")}</th></tr></thead>
    <tbody>${rows.map((r) => r.html).join("")}</tbody></table></div>
    <p class="muted small-note">${tr("{0} のスキルで計算しています。輸送の手間・危険、注文の競合（価格の更新）は考慮していません。", esc(tradeCharacter().character_name))}</p>`;
}

// ---------- 注文一覧 ----------

function orderRange(range) {
  if (range === "station") return tr("ステーション");
  if (range === "solarsystem") return tr("星系");
  if (range === "region") return tr("リージョン");
  if (/^\d+$/.test(range ?? "")) return `${tr("{0} ジャンプ", range)}`;
  return range ?? "";
}

function orderRows(orders, empty) {
  if (!orders.length) return `<tr><td colspan="4" class="muted">${empty}</td></tr>`;
  return orders.map((o) => `<tr><td class="r num" title="${esc(fullIsk(o.price))}">${fmtIsk(o.price)}</td><td class="r num">${fmtNum(o.volume)}</td>
    <td class="muted">${esc(orderRange(o.range))}</td><td class="muted num">${esc(fmtLocal(o.issued))}</td></tr>`).join("");
}

async function showDetail(typeId, locationId = detailLocation || selectedLocationIds()[0]) {
  detailItem = Number(typeId);
  detailLocation = Number(locationId);
  const section = $("#detail-section");
  const box = $("#detail");
  section.hidden = false;
  box.innerHTML = `<span class="muted">${tr("注文を取得しています…")}</span>`;
  let d;
  try {
    d = await request("GET", `/api/market/orders?location=${detailLocation}&type_id=${detailItem}`);
  } catch (e) {
    box.innerHTML = `<div class="warn">${esc(e.message)}</div>`;
    return;
  }
  const options = allLocations().map((l) => `<option value="${l.id}" ${l.id === detailLocation ? "selected" : ""}>${isStructure(l.id) ? "🏰 " : ""}${esc(locLabel(l))}</option>`).join("");
  const inList = watchlist.some((w) => w.type_id === detailItem);
  const best = d.best;
  const head = `<tr><th class="r">${tr("価格 (ISK)")}</th><th class="r">${tr("数量")}</th><th>${tr("範囲")}</th><th>${tr("出品日時")}</th></tr>`;
  box.innerHTML = `
    <div class="preview-head"><div><h3>${esc(nm(d.item))}</h3><small>${nmSub(d.item)}</small></div>
      <span class="actions">
        <select id="detail-location">${options}</select>
        ${inList ? `<span class="badge ok">${tr("比較リストに追加済み")}</span>` : `<button class="btn small primary" type="button" data-action="add" data-id="${detailItem}">${tr("＋ 比較リストに追加")}</button>`}
        ${gameCharSelect(characters)}<button class="btn small" type="button" data-action="open-game" data-id="${detailItem}">${tr("🎮 ゲームで開く")}</button>
        <button class="icon-btn" type="button" title="${tr("閉じる")}" data-action="close-detail">×</button></span></div>
    <div class="market-summary">
      <span>${tr("最安の売り <b class=\"sell\">{0}</b>{1}", best.sell ? `${fmtIsk(best.sell.price)} ISK` : tr("なし"), (best.sell ? `${tr("（{0} 個・{1} 件）", fmtNum(best.sell.total_volume), d.sell_count)}` : ""))}</span>
      <span>${tr("最高の買い <b class=\"buy\">{0}</b>{1}", best.buy ? `${fmtIsk(best.buy.price)} ISK` : tr("なし"), (best.buy ? `${tr("（{0} 個・{1} 件）", fmtNum(best.buy.total_volume), d.buy_count)}` : ""))}</span>
    </div>
    <div class="cols">
      <div><h3>${tr("売り注文（安い順）")}</h3><div class="table-scroll order-scroll"><table class="orders"><thead>${head}</thead><tbody>${orderRows(d.sell, tr("売り注文はありません"))}</tbody></table></div></div>
      <div><h3>${tr("買い注文（高い順）")}</h3><div class="table-scroll order-scroll"><table class="orders"><thead>${head}</thead><tbody>${orderRows(d.buy, tr("買い注文はありません"))}</tbody></table></div></div>
    </div>
    ${d.sell_count > d.sell.length || d.buy_count > d.buy.length ? `<p class="muted small-note">${tr("上位 50 件まで表示しています。")}</p>` : ""}
    <h3>${tr("相場の推移")}</h3><div id="detail-history"><p class="muted">${tr("読み込み中…")}</p></div>`;
  $("#detail-location").addEventListener("change", (ev) => showDetail(detailItem, ev.target.value));
  loadHistory(detailItem, allLocations().find((l) => l.id === detailLocation)?.region_id || 10000002);
}

// 相場の推移（リージョンの日ごとの平均価格・取引量）
async function loadHistory(typeId, regionId) {
  const box = $("#detail-history");
  if (!box) return;
  try {
    const d = await request("GET", `/api/market/history?type_id=${typeId}&region=${regionId}`);
    if (typeId !== detailItem) return;
    const last = d.history.slice(-90);
    box.innerHTML = last.length ? `<div class="stat-row">
        <div class="stat-card"><small class="muted">${tr("1 日の取引量（7 日平均）")}</small><b>${fmtNum(Math.round(d.volume_7))}</b></div>
        <div class="stat-card"><small class="muted">${tr("1 日の取引量（30 日平均）")}</small><b>${fmtNum(Math.round(d.volume_30))}</b></div>
        <div class="stat-card"><small class="muted">${tr("平均価格（30 日）")}</small><b>${fmtIsk(d.price_30)} ISK</b></div></div>
      <div class="cols"><div><h3>${tr("平均価格（90 日）")}</h3>${svgChart(last.map((r) => ({ x: r.date.slice(5), y: r.average })))}</div>
        <div><h3>${tr("取引量")}</h3>${svgChart(last.map((r) => ({ x: r.date.slice(5), y: r.volume })), { kind: "bar", fmt: fmtNum })}</div></div>
      <p class="muted small-note">${tr("リージョン全体の値です。出品するときは「1 日の取引量」と出品数を比べて、売り切れるまでの日数の目安にしてください。")}</p>`
      : `<p class="muted">${tr("取引の記録がありません。")}</p>`;
  } catch (e) {
    box.innerHTML = `<p class="muted">${tr("相場の推移を取得できませんでした（{0}）", esc(e.message))}</p>`;
  }
}

// ---------- 自分の注文 ----------

function myOrderRow(o) {
  let state;
  if (o.market_error) state = `<span class="muted" title="${esc(o.market_error)}">${tr("比較できません")}</span>`;
  else if (o.beaten) {
    state = `<span class="badge missing">${o.is_buy_order ? tr("上回られた") : tr("下回られた")}</span>
      <br><small>${tr("他 {0}（{1}{2}）", fmtIsk(o.best_other), o.is_buy_order ? "+" : "−", fmtIsk(Math.abs(o.best_other - o.price)))}</small>`;
  } else state = `<span class="badge ok">${o.is_buy_order ? tr("最高値") : tr("最安値")}</span>`;
  const left = o.days_left > 0 ? `${tr("あと {0}", esc(fmtMinutes(o.days_left * 1440)))}` : tr("期限切れ");
  return `<tr><td>${state}</td><td><button class="link item-link" type="button" data-action="detail" data-id="${o.type_id}">${esc(nm(o))}</button>
    <br><small class="muted">${esc(o.character_name)} · ${o.is_buy_order ? tr("買い") : tr("売り")}</small></td>
    <td class="r num" title="${esc(fullIsk(o.price))}">${fmtIsk(o.price)}</td><td class="r num">${fmtNum(o.volume_remain)} / ${fmtNum(o.volume_total)}</td>
    <td><small>${esc(o.location || "-")}</small></td><td class="${o.days_left < 3 ? "warn-text" : "muted"}"><small>${left}</small></td></tr>`;
}

async function loadMyOrders(force = false) {
  const box = $("#my-orders");
  box.innerHTML = `<p class="muted">${tr("読み込み中…")}</p>`;
  try {
    const d = await request("GET", `/api/market/my-orders${force ? "?force=1" : ""}`);
    const beaten = d.orders.filter((o) => o.beaten).length;
    const expiring = d.orders.filter((o) => o.days_left < 3).length;
    box.innerHTML = charErrors(d.characters) + `<p>${tr("{0} 件 · <b class=\"{1}\">価格で負けている {2} 件</b> · 期限まで 3 日未満 {3} 件", d.orders.length, beaten ? "warn-text" : "", beaten, expiring)}</p>
      <div class="table-scroll"><table class="orders"><thead><tr><th>${tr("状態")}</th><th>${tr("品目")}</th><th class="r">${tr("価格")}</th><th class="r">${tr("残り / 数量")}</th><th>${tr("場所")}</th><th>${tr("期限")}</th></tr></thead>
      <tbody>${d.orders.map(myOrderRow).join("") || `<tr><td colspan="6" class="muted">${tr("出品中の注文はありません")}</td></tr>`}</tbody></table></div>`;
  } catch (e) {
    box.innerHTML = `<div class="warn">${esc(e.message)}</div>`;
  }
}

$("#orders-reload").addEventListener("click", () => loadMyOrders(true));

// ---------- 保険 ----------

let insTimer = null;
$("#ins-search").addEventListener("input", () => {
  clearTimeout(insTimer);
  insTimer = setTimeout(async () => {
    const q = $("#ins-search").value.trim();
    const list = $("#ins-results");
    if (!q) { list.hidden = true; return; }
    try {
      const d = await request("GET", `/api/search?checks=0&q=${encodeURIComponent(q)}`);
      const ships = d.results.filter((r) => r.category === tr("艦船"));
      list.innerHTML = ships.length
        ? ships.map((r) => `<li data-ins="${r.id}"><span class="names"><b>${esc(nm(r))}</b><small>${nmSub(r, " · ")}${esc(r.group)}</small></span></li>`).join("")
        : `<li class="empty">${tr("艦が見つかりません")}</li>`;
      list.hidden = false;
    } catch (e) {
      toast(e.message, "error");
    }
  }, 200);
});

async function showInsurance(typeId) {
  const box = $("#insurance");
  box.innerHTML = `<p class="muted">${tr("読み込み中…")}</p>`;
  try {
    const d = await request("GET", `/api/market/insurance?type_id=${typeId}`);
    const price = d.jita_sell;
    const rows = d.levels.map((l) => `<tr><td>${esc(l.name)}</td><td class="r num">${fmtIsk(l.cost)}</td><td class="r num">${fmtIsk(l.payout)}</td>
      <td class="r num">${fmtIsk(l.net)}</td><td class="r num">${price != null ? fmtIsk(price - l.net) : "-"}</td></tr>`).join("");
    box.innerHTML = `<div class="card"><h3>${esc(nm(d))} <small class="muted">${nmSub(d)}</small></h3>
      <p>${tr("Jita 4-4: 売値 <b>{0}</b> · 買値 {1}", price != null ? `${fmtIsk(price)} ISK` : tr("なし"), d.jita_buy != null ? `${fmtIsk(d.jita_buy)} ISK` : tr("なし"))}</p>
      <div class="table-scroll"><table class="orders"><thead><tr><th>${tr("等級")}</th><th class="r">${tr("掛け金")}</th><th class="r">${tr("支払われる額")}</th>
        <th class="r">${tr("失ったときの戻り")}<br><small>${tr("支払額 − 掛け金")}</small></th><th class="r">${tr("実質の損失")}<br><small>${tr("Jita 売値 − 戻り")}</small></th></tr></thead>
      <tbody>${rows}</tbody></table></div>
      <p class="muted small-note">${tr("保険は 12 週間有効です。T2・T3 の艦は、艦の価格に比べて支払額が小さくなります。")}</p></div>`;
  } catch (e) {
    box.innerHTML = `<div class="warn">${esc(e.message)}</div>`;
  }
}

// ---------- 検索 ----------

async function runSearch() {
  const q = $("#item-search").value.trim();
  const list = $("#item-results");
  if (!q) { list.hidden = true; return; }
  try {
    const data = await request("GET", `/api/search?checks=0&q=${encodeURIComponent(q)}`);
    list.innerHTML = data.results.length
      ? data.results.map((r) => `<li data-id="${r.id}"><span class="names"><b>${esc(nm(r))}</b><small>${nmSub(r, " · ")}${esc(r.category)} / ${esc(r.group)}</small></span></li>`).join("")
      : `<li class="empty">${data.catalog.searchable ? `${tr("「{0}」に一致するアイテムはありません", esc(q))}` : tr("名前一覧を作成中です")}</li>`;
    list.hidden = false;
  } catch (e) {
    toast(e.message, "error");
  }
}

async function addToWatchlist(typeId) {
  await request("POST", "/api/market/watchlist", { type_id: Number(typeId) });
  watchlist = (await request("GET", "/api/market/watchlist")).items;
  await loadCompare();
}

// ---------- イベント ----------

document.addEventListener("click", async (ev) => {
  const ins = ev.target.closest("#ins-results li[data-ins]");
  if (ins) {
    $("#ins-results").hidden = true;
    $("#ins-search").value = "";
    showInsurance(ins.dataset.ins);
    return;
  }
  if (!ev.target.closest("#ins-search")) $("#ins-results").hidden = true;
  const li = ev.target.closest("#item-results li[data-id]");
  if (li) {
    $("#item-results").hidden = true;
    $("#item-search").value = "";
    try { await addToWatchlist(li.dataset.id); } catch (e) { toast(e.message, "error"); }
    return;
  }
  if (!ev.target.closest(".search-wrap")) $("#item-results").hidden = true;
  const el = ev.target.closest("[data-action]");
  if (!el) return;
  try {
    switch (el.dataset.action) {
      case "remove":
        await request("DELETE", `/api/market/watchlist/${el.dataset.id}`);
        watchlist = watchlist.filter((w) => String(w.type_id) !== el.dataset.id);
        await loadCompare();
        break;
      case "detail":
        await showDetail(el.dataset.id);
        $("#detail-section").scrollIntoView({ behavior: "smooth" });
        break;
      case "add":
        await addToWatchlist(el.dataset.id);
        await showDetail(el.dataset.id);
        break;
      case "open-game":
        await gameAction("/api/ui/market", { type_id: Number(el.dataset.id) }, tr("ゲームのマーケット画面を開きました"));
        break;
      case "close-detail":
        $("#detail-section").hidden = true;
        detailItem = null;
        break;
    }
  } catch (e) {
    toast(e.message, "error");
  }
});

$("#item-search").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(runSearch, 200);
});

$("#location-checks").addEventListener("change", (ev) => {
  if (!ev.target.matches("input[data-loc]")) return;
  const ids = [...document.querySelectorAll("#location-checks input[data-loc]:checked")].map((i) => Number(i.dataset.loc));
  if (!ids.length) { ev.target.checked = true; toast(tr("場所を 1 つ以上選んでください。"), "error"); return; }
  saveJson(COMPARE_KEY, ids);
  loadCompare();
});

$("#trade-char").addEventListener("change", () => {
  saveJson(TRADE_CHAR_KEY, Number($("#trade-char").value));
  renderFeeSummary();
  renderTrades();
  loadStandings();
});

document.querySelector(".fee-settings").addEventListener("input", (ev) => {
  const key = ev.target.dataset.fee;
  if (!key) return;
  fees[key] = key === "structureBroker" && ev.target.value === "" ? "" : Number(ev.target.value) || 0;
  saveJson(FEES_KEY, fees);
  renderFeeSummary();
  renderTrades();
});

$("#fee-reset").addEventListener("click", () => {
  fees = { ...DEFAULT_FEES };
  saveJson(FEES_KEY, fees);
  renderFeeSummary();
  renderTrades();
});

$("#reload-btn").addEventListener("click", () => loadCompare());

// ---------- 起動 ----------

(async () => {
  try {
    const [locs, chars, watch] = await Promise.all([
      request("GET", "/api/market/locations"),
      request("GET", "/api/characters"),
      request("GET", "/api/market/watchlist"),
    ]);
    locations = locs;
    characters = chars.characters.filter((c) => !c.missing);
    watchlist = watch.items;

    const savedChar = loadJson(TRADE_CHAR_KEY, null);
    $("#trade-char").innerHTML = characters.map((c) =>
      `<option value="${c.character_id}" ${c.character_id === savedChar ? "selected" : ""}>${tr("{0} （Accounting {1}・Broker Relations {2}）", esc(c.character_name), ROMAN[c.trade_skills.accounting], ROMAN[c.trade_skills.broker_relations])}</option>`).join("");

    renderLocationChecks();
    renderFeeSummary();
    loadStandings();
    loadMyOrders();
    await loadCompare();

    // /market?type_id=... で開かれたら、その注文一覧を表示する（スキルチェッカーの「マーケットで見る」から）
    const typeId = new URLSearchParams(location.search).get("type_id");
    if (typeId) {
      await showDetail(typeId);
      $("#detail-section").scrollIntoView();
    }
  } catch (e) {
    toast(e.message, "error");
  }
})();
