"use strict";
// お金: 残高・収支・転売の実績・契約・LP・コーポレーション

let characters = [];
let groups = [];
let ids = new Set();

const isk = (n) => `${fmtIsk(n)} ISK`;
const signed = (n) => `<span class="${n >= 0 ? "ok-text" : "warn-text"}">${n >= 0 ? "+" : ""}${fmtIsk(n)}</span>`;
const days = () => Number($("#days").value);

async function section(id, url, render) {
  const box = $(`#${id}`);
  box.innerHTML = `<p class="muted">${tr("読み込み中…")}</p>`;
  try {
    const d = await request("GET", url);
    box.innerHTML = render(d);
  } catch (e) {
    box.innerHTML = `<div class="warn">${esc(e.message)}</div>`;
  }
}

function renderSummary(d) {
  const ok = d.characters.filter((c) => c.balance != null);
  const total = ok.reduce((s, c) => s + c.balance, 0);
  const income = ok.reduce((s, c) => s + c.income, 0);
  const expense = ok.reduce((s, c) => s + c.expense, 0);
  const cards = ok.sort((a, b) => b.balance - a.balance).map((c) => `<div class="stat-card"><small class="muted">${esc(c.character_name)}</small>
    <b title="${esc(fullIsk(c.balance))}">${isk(c.balance)}</b><small>${signed(c.income + c.expense)} <span class="muted">${tr("/ {0} 日", d.days)}</span></small></div>`).join("");
  const cats = d.categories.slice(0, 20).map((c) => `<tr><td>${esc(c.label)}</td><td class="r num">${c.income ? signed(c.income) : "-"}</td>
    <td class="r num">${c.expense ? signed(c.expense) : "-"}</td><td class="r num">${signed(c.income + c.expense)}</td><td class="r muted">${fmtNum(c.count)}</td></tr>`).join("");
  return `${charErrors(d.characters)}
    <div class="stat-row"><div class="stat-card total"><small class="muted">${tr("合計の残高")}</small><b title="${esc(fullIsk(total))}">${isk(total)}</b>
      <small>${tr("収入 {0} · 支出 {1}", signed(income), signed(expense))}</small></div>${cards}</div>
    <div class="cols">
      <div class="card"><h3>${tr("合計の残高の推移")}</h3>${svgChart(d.daily.map((p) => ({ x: p.date.slice(5), y: p.balance })))}</div>
      <div class="card"><h3>${tr("日ごとの収支")}</h3>${svgChart(d.daily.map((p) => ({ x: p.date.slice(5), y: p.net })), { kind: "bar", color: "var(--ok)" })}</div>
    </div>
    <h3>${tr("収支の内訳（{0} 日）", d.days)}</h3>
    <div class="table-scroll"><table class="orders"><thead><tr><th>${tr("種類")}</th><th class="r">${tr("収入")}</th><th class="r">${tr("支出")}</th><th class="r">${tr("差し引き")}</th><th class="r">${tr("件数")}</th></tr></thead>
      <tbody>${cats || `<tr><td colspan="5" class="muted">${tr("記録がありません")}</td></tr>`}</tbody></table></div>`;
}

function renderTrades(d) {
  const rows = d.items.slice(0, 100).map((i) => `<tr><td><b>${esc(nm(i))}</b><br><small class="muted">${nmSub(i)}</small></td>
    <td class="r num">${fmtNum(i.buy_qty)}<br><small class="muted">${i.avg_buy != null ? fmtIsk(i.avg_buy) : "-"}</small></td>
    <td class="r num">${fmtNum(i.sell_qty)}<br><small class="muted">${i.avg_sell != null ? fmtIsk(i.avg_sell) : "-"}</small></td>
    <td class="r num">${i.profit != null ? signed(i.profit) : `<span class="muted">${tr("仕入れ不明")}</span>`}</td>
    <td class="r num ${i.stock > 0 ? "" : "muted"}">${fmtNum(i.stock)}</td></tr>`).join("");
  const fees = d.fees.brokers_fee + d.fees.transaction_tax;
  return `${charErrors(d.characters)}
    <div class="stat-row"><div class="stat-card"><small class="muted">${tr("売買の利益（手数料の前）")}</small><b>${signed(d.gross)}</b></div>
      <div class="stat-card"><small class="muted">${tr("仲介手数料 + 売上税")}</small><b>${signed(-fees)}</b>
        <small class="muted">${tr("仲介 {0} · 税 {1}", fmtIsk(d.fees.brokers_fee), fmtIsk(d.fees.transaction_tax))}</small></div>
      <div class="stat-card total"><small class="muted">${tr("差し引きの利益（{0} 日）", d.days)}</small><b>${signed(d.net)}</b></div></div>
    <div class="table-scroll"><table class="orders"><thead><tr><th>${tr("品目")}</th><th class="r">${tr("買った数")}<br><small>${tr("平均買値")}</small></th>
      <th class="r">${tr("売った数")}<br><small>${tr("平均売値")}</small></th><th class="r">${tr("利益")}</th><th class="r">${tr("在庫の増減")}</th></tr></thead>
      <tbody>${rows || `<tr><td colspan="5" class="muted">${tr("期間内の取引はありません")}</td></tr>`}</tbody></table></div>`;
}

function renderContracts(d) {
  const rows = d.contracts.map((c) => {
    const money = c.type === "courier"
      ? `${tr("報酬 {0}", fmtIsk(c.reward))}<br><small class="muted">${tr("担保 {0} · {1} m³", fmtIsk(c.collateral), fmtNum(c.volume))}</small>`
      : `${fmtIsk(c.price)}${c.reward ? `<br><small class="muted">${tr("報酬 {0}", fmtIsk(c.reward))}</small>` : ""}`;
    const route = c.end_location && c.end_location !== c.start_location
      ? `${esc(c.start_location || "-")} → ${esc(c.end_location)}` : esc(c.start_location || "-");
    const expire = c.active ? `<br><small class="${new Date(c.date_expired) - Date.now() < 86400000 ? "warn-text" : "muted"}">${tr("期限 {0}", esc(timeLeft(c.date_expired)))}</small>` : "";
    return `<tr class="${c.active ? "" : "muted-row"}"><td><span class="badge ${c.active ? "queued" : "ok"}">${esc(c.status_label)}</span>${expire}</td>
      <td><b>${esc(c.type_label)}</b>${c.title ? `<br><small>${esc(c.title)}</small>` : ""}</td>
      <td><small>${esc(c.character_name)}<br><span class="muted">${tr("出: {0}{1}", esc(c.issuer_name || "-"), (c.acceptor_name ? ` ${tr("· 受: {0}", esc(c.acceptor_name))}` : ""))}</span></small></td>
      <td><small>${route}</small></td><td class="r num">${money}</td><td class="muted"><small>${esc(fmtLocal(c.date_issued))}</small></td></tr>`;
  }).join("");
  return `${charErrors(d.characters)}<div class="table-scroll"><table class="orders"><thead><tr><th>${tr("状態")}</th><th>${tr("種類")}</th><th>${tr("キャラクター")}</th><th>${tr("場所")}</th>
    <th class="r">${tr("金額 (ISK)")}</th><th>${tr("作成")}</th></tr></thead><tbody>${rows || `<tr><td colspan="6" class="muted">${tr("契約はありません（募集中・進行中と、30 日以内のもの）")}</td></tr>`}</tbody></table></div>`;
}

function renderLp(d) {
  if (!d.corporations.length) return charErrors(d.characters) + `<p class="muted">${tr("LP を持っていません。")}</p>`;
  return charErrors(d.characters) + d.corporations.map((c) => {
    const rows = c.offers.map((o) => `<tr><td><b>${esc(nm(o))}</b>${o.quantity > 1 ? ` ×${fmtNum(o.quantity)}` : ""}
        ${o.required.length ? `<br><small class="muted">${tr("必要: {0}", o.required.map((r) => `${esc(nm(r))} ×${fmtNum(r.quantity)}`).join(LIST_SEP))}</small>` : ""}</td>
      <td class="r num">${fmtNum(o.lp_cost)} LP${o.isk_cost ? `<br><small class="muted">+ ${fmtIsk(o.isk_cost)} ISK</small>` : ""}</td>
      <td class="r num">${o.sell != null ? fmtIsk(o.sell) : "-"}<br><small class="muted">${tr("買 {0}", o.buy != null ? fmtIsk(o.buy) : "-")}</small></td>
      <td class="r num"><b>${o.per_lp_sell != null ? fmtNum(Math.round(o.per_lp_sell)) : "-"}</b><br><small class="muted">${tr("買 {0}", o.per_lp_buy != null ? fmtNum(Math.round(o.per_lp_buy)) : "-")}</small></td>
      <td class="r num">${o.daily_volume == null ? "-" : fmtNum(Math.round(o.daily_volume))}${(o.daily_volume || 0) < 1 ? `<br><small class="warn-text">${tr("ほぼ売れない")}</small>` : ""}</td>
      <td class="r num">${fmtNum(o.affordable)}</td>
      <td><a class="btn small" href="/market?type_id=${o.type_id}">🛒</a></td></tr>`).join("");
    return `<div class="card lp-card"><div class="section-head"><h3>${esc(c.name)}</h3><span><b>${fmtNum(c.total)} LP</b>
        <a class="btn small" href="/lp?corp=${c.corporation_id}">${tr("交換プランを見る")}</a></span></div>
      <small class="muted">${c.by_character.map((b) => `${esc(b.character_name)} ${fmtNum(b.points)}`).join(" · ")}</small>
      <div class="table-scroll"><table class="orders"><thead><tr><th>${tr("交換品")}</th><th class="r">${tr("費用")}</th><th class="r">${tr("Jita 売値")}</th>
        <th class="r">ISK / LP<br><small>${tr("売り注文 / 買い注文に売る")}</small></th><th class="r">${tr("1 日の取引量")}<br><small>${tr("7 日平均")}</small></th><th class="r">${tr("交換できる回数")}</th><th></th></tr></thead>
        <tbody>${rows || `<tr><td colspan="7" class="muted">${tr("交換品がありません")}</td></tr>`}</tbody></table></div></div>`;
  }).join("");
}

function renderCorp(d) {
  if (!d.corporations.length) return `<p class="muted">${tr("キャラクターがいません。")}</p>`;
  return d.corporations.map((c) => {
    if (c.npc) return `<div class="card"><b>${esc(c.name)}</b> <span class="muted">${tr("NPC コーポ（{0}）", esc(c.members.join(LIST_SEP)))}</span></div>`;
    const wallets = c.wallets ? `<div class="stat-row">${c.wallets.map((w) => `<div class="stat-card"><small class="muted">${esc(c.division_names?.[w.division] || `${tr("口座 {0}", w.division)}`)}</small>
      <b>${isk(w.balance)}</b></div>`).join("")}</div><small class="muted">${tr("{0} の権限で取得", esc(c.wallet_by))}</small>` : "";
    const assets = c.assets ? `<h3>${tr("資産（目安 {0}・{1} 種類）", isk(c.assets.value), fmtNum(c.assets.types))}</h3>
      <div class="table-scroll"><table class="orders"><thead><tr><th>${tr("品目")}</th><th class="r">${tr("数量")}</th><th class="r">${tr("金額（目安）")}</th></tr></thead>
      <tbody>${c.assets.top.map((a) => `<tr><td>${esc(nm(a))}</td><td class="r num">${fmtNum(a.quantity)}</td><td class="r num">${fmtIsk(a.value)}</td></tr>`).join("")}</tbody></table></div>` : "";
    const errs = (c.errors || []).map((e) => `<li>${tr("{0}（{1}）: {2}", e.what === "wallets" ? tr("口座") : tr("資産"), esc(e.character_name), e.needs_scope ? `${tr("<a href=\"/login\">再ログイン</a>が必要")}` : e.forbidden ? tr("役職が足りません") : esc(e.error))}</li>`).join("");
    return `<div class="card"><h3>${esc(c.name)}</h3><small class="muted">${esc(c.members.join(LIST_SEP))}</small>
      ${wallets}${assets}${errs ? `<ul class="small-note muted">${errs}</ul>` : ""}</div>`;
  }).join("");
}

function loadAll() {
  const q = idsQuery(ids);
  section("summary", `/api/wallet/summary?days=${days()}&${q}`, renderSummary);
  section("trades", `/api/wallet/trades?days=${days()}&${q}`, renderTrades);
  section("contracts", `/api/wallet/contracts?${q}`, renderContracts);
  section("lp", `/api/wallet/lp?${q}`, renderLp);
  section("corp", `/api/wallet/corp?${q}`, renderCorp);
}

$("#days").addEventListener("change", loadAll);
$("#reload").addEventListener("click", loadAll);

(async () => {
  try {
    const d = await request("GET", "/api/characters");
    characters = d.characters;
    groups = d.groups;
    ids = renderCharFilter($("#char-filter"), characters, groups, (next) => { ids = next; loadAll(); });
    loadAll();
  } catch (e) {
    toast(e.message, "error");
  }
})();
