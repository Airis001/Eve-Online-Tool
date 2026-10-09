"use strict";
// 資産: 全キャラクターの持ち物の検索と、場所ごとの合計

let data = null;
let ids = new Set();

function matches(text, q) {
  return !q || q.split(/\s+/).every((w) => text.includes(w));
}

function render() {
  if (!data) return;
  const q = $("#as-q").value.trim().toLowerCase();
  const view = $("#as-view").value;
  $("#as-summary").innerHTML = `${charErrors(data.characters)}<div class="stat-row">
    <div class="stat-card total"><small class="muted">${tr("資産の合計（目安）")}</small><b>${fmtIsk(data.total)} ISK</b></div>
    <div class="stat-card"><small class="muted">${tr("場所")}</small><b>${fmtNum(data.locations.length)}</b></div>
    <div class="stat-card"><small class="muted">${tr("品目（場所・キャラクターごと）")}</small><b>${fmtNum(data.items.length)}</b></div></div>`;
  if (view === "locations") {
    const rows = data.locations.filter((l) => matches(`${l.name} ${l.characters.join(" ")}`.toLowerCase(), q));
    $("#as-body").innerHTML = `<div class="table-scroll"><table class="orders"><thead><tr><th>${tr("場所")}</th><th>${tr("キャラクター")}</th><th class="r">${tr("品目")}</th><th class="r">${tr("金額（目安）")}</th></tr></thead>
      <tbody>${rows.map((l) => `<tr><td><button class="link" type="button" data-loc="${esc(l.name)}">${esc(l.name)}</button></td>
        <td><small>${esc(l.characters.join(LIST_SEP))}</small></td><td class="r num">${fmtNum(l.count)}</td><td class="r num">${fmtIsk(l.value)}</td></tr>`).join("")}</tbody></table></div>`;
    return;
  }
  const rows = data.items.filter((i) => matches(`${nm(i)} ${i.en} ${i.location} ${i.character_name} ${i.inside || ""}`.toLowerCase(), q));
  const shown = rows.slice(0, 500);
  const sum = rows.reduce((s, i) => s + i.value, 0);
  $("#as-body").innerHTML = `<p class="muted small-note">${tr("{0} 件 · 合計 {1} ISK{2}", fmtNum(rows.length), fmtIsk(sum), (rows.length > shown.length ? `${tr("（上位 {0} 件を表示）", shown.length)}` : ""))}</p>
    <div class="table-scroll"><table class="orders"><thead><tr><th>${tr("アイテム")}</th><th class="r">${tr("数量")}</th><th class="r">${tr("金額（目安）")}</th><th>${tr("場所")}</th><th>${tr("キャラクター")}</th></tr></thead>
    <tbody>${shown.map((i) => `<tr><td><b>${esc(nm(i))}</b>${i.inside ? `<br><small class="muted">${tr("{0} の中", esc(i.inside))}</small>` : ""}</td>
      <td class="r num">${fmtNum(i.qty)}</td><td class="r num">${fmtIsk(i.value)}</td><td><small>${esc(i.location)}</small></td>
      <td><small>${esc(i.character_name)}</small></td></tr>`).join("")}</tbody></table></div>`;
}

async function load() {
  $("#as-body").innerHTML = `<p class="muted">${tr("読み込み中…（キャラクターが多いと少し時間がかかります）")}</p>`;
  try {
    data = await request("GET", `/api/assets?${idsQuery(ids)}`);
    render();
  } catch (e) {
    $("#as-body").innerHTML = `<div class="warn">${esc(e.message)}</div>`;
  }
}

$("#as-q").addEventListener("input", render);
$("#as-view").addEventListener("change", render);
$("#as-body").addEventListener("click", (ev) => {
  const b = ev.target.closest("[data-loc]");
  if (!b) return;
  $("#as-view").value = "items";
  $("#as-q").value = b.dataset.loc.toLowerCase();
  render();
});
$("#reload").addEventListener("click", load);

(async () => {
  try {
    const d = await request("GET", "/api/characters");
    ids = renderCharFilter($("#char-filter"), d.characters, d.groups, (next) => { ids = next; load(); });
    load();
  } catch (e) {
    toast(e.message, "error");
  }
})();
