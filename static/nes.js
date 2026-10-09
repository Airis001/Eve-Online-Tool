"use strict";
// PLEX とニューエデンストア: ストアの商品を PLEX で買って売るか、PLEX をそのまま売るか

let data = null;
let editing = null;

const isk = (n) => (n == null ? "-" : `${fmtIsk(n)} ISK`);
const signed = (n) => (n == null ? "-" : `<span class="${n >= 0 ? "ok-text" : "warn-text"}">${n >= 0 ? "+" : ""}${fmtIsk(n)}</span>`);

function verdict(o) {
  if (o.gain_list == null && o.gain_instant == null) return `<span class="badge missing">${tr("比べられません")}</span>`;
  const g = o.gain_list ?? o.gain_instant;
  return g > 0 ? `<span class="badge ok">${tr("✓ 商品を買って売る方が得")}</span>` : `<span class="badge missing">${tr("✕ PLEX のまま売る方が得")}</span>`;
}

// ループ: 売ったお金で PLEX を買い直して、また商品を買って売ると儲かるか
function loopBlock(o) {
  const b = o.best_loop;
  if (!b) return `<p class="muted small-note">${tr("🔁 ループ: 価格が足りないため計算できません。")}</p>`;
  const ok = b.profit > 0;
  const rows = o.loops.map((l) => `<tr class="${l === b ? "nes-best" : ""}"><td>${esc(l.buy)} → ${esc(l.sell)}</td>
    <td class="r num">${fmtIsk(l.cost)}</td><td class="r num">${fmtIsk(l.net)}</td><td class="r num">${signed(l.profit)}</td><td class="r num">${fmtPct(l.roi, 1)}</td></tr>`).join("");
  const perDay = o.loops_per_day != null
    ? `${tr("1 日に回せる回数の目安 <b>{0}</b> 回{1}", o.loops_per_day >= 1 ? fmtNum(Math.floor(o.loops_per_day)) : o.loops_per_day.toFixed(2), (o.loop_profit_per_day ? `${tr("（1 日 約 {0} ISK）", fmtIsk(o.loop_profit_per_day))}` : ""))}`
    : tr("1 日に回せる回数は分かりません（取引量の分からない品目があります）");
  return `<div class="nes-loop ${ok ? "ok" : "ng"}"><div><b>${tr("🔁 ループ")}</b> ${ok
      ? `<span class="badge ok">${tr("✓ 儲かる")}</span> ${tr("一番良い組み合わせで 1 周 <b>{0}</b> ISK（{1}）", signed(b.profit), fmtPct(b.roi, 1))}`
      : `<span class="badge missing">${tr("✕ 儲からない")}</span> ${tr("一番良い組み合わせでも 1 周 {0} ISK", signed(b.profit))}`}</div>
    <small class="muted">${perDay}</small>
    <details class="mini-details"><summary>${tr("組み合わせ別")}</summary>
      <div class="table-scroll"><table class="orders"><thead><tr><th>${tr("買い方 → 売り方")}</th><th class="r">${tr("PLEX {0} の代金", fmtNum(o.plex))}</th><th class="r">${tr("商品の手取り")}</th><th class="r">${tr("1 周の利益")}</th><th class="r">${tr("利益率")}</th></tr></thead>
      <tbody>${rows}</tbody></table></div>
      <p class="muted small-note">${tr("PLEX を売り注文から即買いするのは手数料なし、買い注文で買うのは仲介手数料込みです。何周も回すと、商品の売値が下がり PLEX の値段が上がるので、利益は小さくなっていきます。")}</p></details></div>`;
}

function offerCard(o) {
  const rows = o.rows.map((r) => `<tr><td>${esc(nm(r))}</td><td class="r num">${fmtNum(r.qty)}</td>
    <td class="r num">${r.sell != null ? fmtIsk(r.sell) : `<span class="warn-text">${tr("注文なし")}</span>`}</td>
    <td class="r num">${r.buy != null ? fmtIsk(r.buy) : "-"}</td>
    <td class="r num">${r.daily_volume != null ? fmtNum(Math.round(r.daily_volume)) : "-"}${r.daily_volume != null && r.qty > r.daily_volume ? `<br><small class="warn-text">${tr("売り切りに {0} 日", fmtNum(Math.ceil(r.qty / Math.max(r.daily_volume, 0.1))))}</small>` : ""}</td></tr>`).join("");
  return `<div class="card nes-card"><div class="section-head"><h3>${esc(o.name)} <small class="muted">${fmtNum(o.plex)} PLEX</small></h3>
      <span>${verdict(o)} <button class="btn small" type="button" data-edit="${o.id}">${tr("編集")}</button>
        <button class="icon-btn" type="button" title="${tr("削除")}" data-del="${o.id}">×</button></span></div>
    <div class="table-scroll"><table class="orders nes-compare"><thead><tr><th></th><th class="r">${tr("売り注文を出す")}</th><th class="r">${tr("買い注文にすぐ売る")}</th></tr></thead><tbody>
      <tr><th>${tr("商品を売った手取り")}</th><td class="r num">${isk(o.items_list)}</td><td class="r num">${isk(o.items_instant)}</td></tr>
      <tr><th>${tr("PLEX（{0}）を売った手取り", fmtNum(o.plex))}</th><td class="r num">${isk(o.plex_list)}</td><td class="r num">${isk(o.plex_instant)}</td></tr>
      <tr><th>${tr("差（商品 − PLEX）")}</th><td class="r num"><b>${signed(o.gain_list)}</b></td><td class="r num"><b>${signed(o.gain_instant)}</b></td></tr>
      <tr><th>${tr("1 PLEX あたり")}</th><td class="r num">${isk(o.per_plex_list)}</td><td class="r num">${isk(o.per_plex_instant)}</td></tr>
    </tbody></table></div>
    ${loopBlock(o)}
    <details class="mini-details"><summary>${tr("中身 {0} 品目{1}", o.rows.length, (o.missing ? `${tr("（")}<span class="warn-text">${tr("売れない品目 {0}", o.missing)}</span>${tr("）")}` : ""))}</summary>
      <table class="orders"><thead><tr><th>${tr("品目")}</th><th class="r">${tr("数量")}</th><th class="r">${tr("Jita 売値")}</th><th class="r">${tr("Jita 買値")}</th><th class="r">${tr("1 日の取引量")}</th></tr></thead><tbody>${rows}</tbody></table></details></div>`;
}

function render() {
  const d = data;
  $("#nes-plex").innerHTML = `<div class="stat-row">
      <div class="stat-card total"><small class="muted">${tr("PLEX の最安の売り値")}</small><b>${isk(d.plex.sell)}</b><small class="muted">${tr("売り注文を出した手取り {0}", isk(d.plex.net_list))}</small></div>
      <div class="stat-card"><small class="muted">${tr("PLEX の最高の買い値")}</small><b>${isk(d.plex.buy)}</b><small class="muted">${tr("すぐ売った手取り {0}", isk(d.plex.net_instant))}</small></div>
      <div class="stat-card"><small class="muted">${tr("手数料（{0}）", esc(d.trader || "-"))}</small><b>${tr("税 {0}・仲介 {1}", fmtPct(d.tax, 2), fmtPct(d.broker, 2))}</b></div></div>`;
  $("#nes-offers").innerHTML = d.offers.length ? d.offers.map(offerCard).join("")
    : `<div class="card empty-card">${tr("商品が登録されていません。下の「商品を登録」から、ストアの商品と PLEX の価格を入れてください。")}</div>`;
  $("#nes-common").innerHTML = d.common.filter((c) => c.type_id).map((c) => `<button class="link" type="button" data-common="${esc(nm(c))}">${esc(nm(c))}</button>`).join(DOT_SEP);
}

async function load() {
  try {
    data = await request("GET", "/api/nes");
    render();
  } catch (e) {
    $("#nes-plex").innerHTML = `<div class="warn">${esc(e.message)}</div>`;
  }
}

function resetForm() {
  editing = null;
  $("#nes-name").value = "";
  $("#nes-plex-price").value = "";
  $("#nes-items").value = "";
  $("#nes-save").textContent = tr("登録する");
  $("#nes-cancel").hidden = true;
}

$("#nes-save").addEventListener("click", async () => {
  try {
    await request("POST", "/api/nes/offers", { id: editing, name: $("#nes-name").value, plex: Number($("#nes-plex-price").value), text: $("#nes-items").value });
    toast(editing ? tr("更新しました。") : tr("登録しました。"), "ok");
    resetForm();
    load();
  } catch (e) {
    toast(e.message, "error");
  }
});
$("#nes-cancel").addEventListener("click", resetForm);

document.addEventListener("click", async (ev) => {
  const c = ev.target.closest("[data-common]");
  if (c) {
    const cur = $("#nes-items").value.trim();
    $("#nes-items").value = `${cur ? `${cur}\n` : ""}${c.dataset.common} x1`;
    if (!$("#nes-name").value) $("#nes-name").value = c.dataset.common;
    $("#nes-plex-price").focus();
    return;
  }
  const e = ev.target.closest("[data-edit]");
  if (e) {
    const o = data.offers.find((x) => x.id === e.dataset.edit);
    editing = o.id;
    $("#nes-name").value = o.name;
    $("#nes-plex-price").value = o.plex;
    $("#nes-items").value = o.text || o.rows.map((r) => `${nm(r)} x${r.qty}`).join("\n");
    $("#nes-save").textContent = tr("更新する");
    $("#nes-cancel").hidden = false;
    $("#nes-name").scrollIntoView({ behavior: "smooth", block: "center" });
    return;
  }
  const d = ev.target.closest("[data-del]");
  if (d && confirm(tr("この商品を削除しますか？"))) {
    try {
      await request("DELETE", `/api/nes/offers/${d.dataset.del}`);
      load();
    } catch (err) {
      toast(err.message, "error");
    }
  }
});
$("#nes-reload").addEventListener("click", load);

load();
