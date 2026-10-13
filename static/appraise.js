"use strict";
// 査定: 貼り付けたアイテムの Jita での合計額

let result = null;

async function run() {
  const text = $("#ap-text").value;
  if (!text.trim()) { toast(tr("アイテムを貼り付けてください。"), "error"); return; }
  $("#ap-out").innerHTML = `<p class="muted">${tr("価格を調べています…")}</p>`;
  try {
    result = await request("POST", "/api/tools/appraise", { text });
  } catch (e) {
    $("#ap-out").innerHTML = `<div class="warn">${esc(e.message)}</div>`;
    return;
  }
  const d = result;
  $("#ap-out").innerHTML = `<div class="stat-row">
      <div class="stat-card total"><small class="muted">${tr("Jita の売値で（売り注文を出して売る）")}</small><b>${fmtIsk(d.sell_total)} ISK</b></div>
      <div class="stat-card"><small class="muted">${tr("Jita の買値で（すぐ売る）")}</small><b>${fmtIsk(d.buy_total)} ISK</b></div>
      <div class="stat-card"><small class="muted">${tr("体積")}</small><b>${fmtNum(Math.round(d.volume * 10) / 10)} m³</b><small class="muted">${tr("{0} 品目", d.items.length)}</small></div></div>
    ${d.unknown.length ? `<p class="warn-text small-note">${tr("分からなかった名前: {0}", esc(d.unknown.join(LIST_SEP)))}</p>` : ""}
    <div class="table-scroll"><table class="orders"><thead><tr><th>${tr("アイテム")}</th><th class="r">${tr("数量")}</th><th class="r">${tr("売値")}</th><th class="r">${tr("出品価格")}<br><small>${tr("📋 でコピー")}</small></th><th class="r">${tr("売値の合計")}</th><th class="r">${tr("買値の合計")}</th><th class="r">${tr("体積")}</th></tr></thead>
    <tbody>${d.items.map((i) => `<tr><td><b>${esc(nm(i))}</b><br><small class="muted">${nmSub(i)}</small></td><td class="r num">${fmtNum(i.qty)}</td>
      <td class="r num">${i.sell != null ? fmtIsk(i.sell) : `<span class="warn-text">${tr("なし")}</span>`}</td>
      <td class="r">${i.sell != null ? copyPriceButton(undercutPrice(i.sell)) : "-"}</td><td class="r num">${fmtIsk(i.sell_total)}</td>
      <td class="r num">${fmtIsk(i.buy_total)}</td><td class="r num">${fmtNum(Math.round(i.volume * 10) / 10)} m³</td></tr>`).join("")}</tbody></table></div>`;
}

$("#ap-run").addEventListener("click", run);

// ---------- 今の艦のカーゴを売る ----------

async function cargoSale(force = false) {
  const box = $("#cs-out");
  box.innerHTML = `<p class="muted">${tr("カーゴと価格を調べています…")}</p>`;
  saveJson("cargo-sale:settings", { char: Number($("#cs-char").value), loc: Number($("#cs-loc").value) });
  let d;
  try {
    d = await request("GET", `/api/tools/cargo-sale?character_id=${$("#cs-char").value}&location=${$("#cs-loc").value}${force ? "&force=1" : ""}`);
  } catch (e) {
    box.innerHTML = `<div class="warn">${esc(e.message)}</div>`;
    return;
  }
  const head = `<p class="small-note">${tr("🚀 {0}{1} · 売るキャラクター: <b>{2}</b>（売上税 {3}・仲介手数料 {4}）", esc(nm(d.ship)), d.ship.name ? ` 「${esc(d.ship.name)}」` : "", esc(d.trader?.name || "-"), fmtPct(d.tax, 2), fmtPct(d.broker, 2))}</p>`;
  if (!d.items.length) { box.innerHTML = head + `<p class="muted">${tr("カーゴは空です。")}</p>`; return; }
  const rows = d.items.map((i) => `<tr><td><b>${esc(nm(i))}</b><br><small class="muted">${nmSub(i)}</small></td>
    <td class="r num">${fmtNum(i.qty)}</td>
    <td class="r num">${i.list_price != null ? `${copyPriceButton(i.list_price)}<br><small class="muted">${tr("売り注文 {0} 件", fmtNum(i.sell_orders))}</small>` : `<span class="muted">${tr("売り注文なし")}</span>`}</td>
    <td class="r num ${i.better === "list" ? "ok-text" : ""}">${i.list_net != null ? fmtIsk(i.list_net) : "-"}</td>
    <td class="r num ${i.better === "instant" ? "ok-text" : ""}">${i.instant_net != null ? fmtIsk(i.instant_net) : "-"}</td>
    <td class="r num">${i.daily_volume != null ? fmtNum(Math.round(i.daily_volume)) : "-"}${i.days_to_sell != null && i.days_to_sell > 1 ? `<br><small class="warn-text">${tr("売り切りまで 約 {0} 日", fmtNum(Math.ceil(i.days_to_sell)))}</small>` : ""}</td></tr>`).join("");
  box.innerHTML = `${head}<div class="stat-row">
      <div class="stat-card"><small class="muted">${tr("売り注文を出して全部売れた場合（手取り）")}</small><b>${fmtIsk(d.list_total)} ISK</b></div>
      <div class="stat-card"><small class="muted">${tr("買い注文にすぐ売った場合（手取り）")}</small><b>${fmtIsk(d.instant_total)} ISK</b></div>
      <div class="stat-card total"><small class="muted">${tr("品目ごとに高い方を選んだ場合")}</small><b>${fmtIsk(d.best_total)} ISK</b></div></div>
    <div class="table-scroll"><table class="orders"><thead><tr><th>${tr("品目")}</th><th class="r">${tr("数量")}</th><th class="r">${tr("出品価格（1 個）")}</th>
      <th class="r">${tr("売り注文の手取り")}<br><small>${tr("税＋仲介手数料の後")}</small></th><th class="r">${tr("即売りの手取り")}<br><small>${tr("税の後")}</small></th><th class="r">${tr("1 日の取引量")}<br><small>${tr("7 日平均")}</small></th></tr></thead>
      <tbody>${rows}</tbody></table></div>
    <p class="muted small-note">${tr("緑は品目ごとに手取りが多い方です。ほかのキャラクターのカーゴの品物をトレードキャラクターが売るには、先に受け渡し（契約・トレード）が必要です。")}</p>`;
}

$("#cs-run").addEventListener("click", () => cargoSale());
$("#cs-force").addEventListener("click", () => cargoSale(true));

(async () => {
  try {
    const [{ characters }, locs] = await Promise.all([request("GET", "/api/characters"), request("GET", "/api/market/locations")]);
    const saved = loadJson("cargo-sale:settings", {});
    $("#cs-char").innerHTML = characters.filter((c) => !c.missing).map((c) =>
      `<option value="${c.character_id}" ${c.character_id === saved.char ? "selected" : ""}>${esc(c.character_name)}</option>`).join("");
    $("#cs-loc").innerHTML = [...locs.hubs, ...locs.owned].map((l) =>
      `<option value="${l.id}" ${l.id === saved.loc ? "selected" : ""}>${esc(l.short || l.name)}</option>`).join("");
  } catch (e) {
    toast(e.message, "error");
  }
})();
$("#ap-copy").addEventListener("click", async () => {
  if (!result) { toast(tr("先に査定してください。"), "error"); return; }
  const lines = [`${tr("合計（Jita 売値）: {0} / 買値: {1}", fullIsk(result.sell_total), fullIsk(result.buy_total))}`,
    ...result.items.map((i) => `${nm(i)}\t${i.qty}\t${Math.round(i.sell_total)}`)];
  await navigator.clipboard.writeText(lines.join("\n"));
  toast(tr("コピーしました。"), "ok");
});
