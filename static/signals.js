"use strict";
// シグネチャ・星系: スキャンの記録・Thera / Turnur の繋がり・星系の活動・インカージョン

const KIND_LABEL = { wormhole: "🌀 WH", data: tr("💾 データ"), relic: tr("🏺 レリック"), gas: tr("☁ ガス"), ore: tr("⛏ 鉱石"), combat: tr("⚔ 戦闘"), anomaly: tr("✦ アノマリ"), unknown: tr("❔ 未判別") };
const SIGNALS_KEY = "signals:settings";
const saved = loadJson(SIGNALS_KEY, {});
let sigData = null;

function secBadge(s) {
  if (!s) return "";
  const cls = { highsec: "sec-hi", lowsec: "sec-low", nullsec: "sec-null", pochven: "sec-null" }[s.kind] || "sec-wh";
  const label = s.kind === "wormhole" || s.kind === "pochven" ? s.label : (s.security_display ?? 0).toFixed(1);
  return `<span class="badge ${cls}">${esc(label)}</span>`;
}

const systemCell = (s) => `<b>${esc(s.name)}</b> ${secBadge(s)}<br><small class="muted">${esc(nm(s, "region_ja", "region") || s.region || "")}</small>`;
const ago = (iso) => {
  const min = (Date.now() - new Date(iso)) / 60000;
  return min < 60 ? `${tr("{0} 分前", Math.max(1, Math.round(min)))}` : min < 1440 ? `${tr("{0} 時間前", Math.round(min / 60))}` : `${tr("{0} 日前", Math.round(min / 1440))}`;
};

// ---------- 1. 記録したシグネチャ ----------

async function loadSigs() {
  try {
    sigData = await request("GET", `/api/sigs/systems?days=${$("#sig-days").value}`);
    renderSigs();
  } catch (e) {
    $("#sigs").innerHTML = `<div class="warn">${esc(e.message)}</div>`;
  }
}

function renderSigs() {
  const kind = $("#sig-kind").value;
  let rows = sigData.systems.filter((r) => !kind || r.counts[kind] > 0);
  const n = (r) => (kind ? r.counts[kind] : r.total);
  if ($("#sig-sort").value === "count") rows = [...rows].sort((a, b) => n(b) - n(a));
  if (!rows.length) {
    $("#sigs").innerHTML = `<p class="muted">${tr("記録がありません。<a href=\"/wormhole\">ワームホールのページ</a>でスキャン結果を貼り付けてください。")}</p>`;
    return;
  }
  const kinds = ["wormhole", "data", "relic", "gas", "ore", "combat", "unknown"];
  $("#sigs").innerHTML = `<p class="muted small-note">${tr("{0} 星系", rows.length)}</p><div class="table-scroll"><table class="orders"><thead><tr><th>${tr("星系")}</th><th class="r">${tr("合計")}</th>
    ${kinds.map((k) => `<th class="r">${KIND_LABEL[k]}</th>`).join("")}<th>${tr("スキャン")}</th><th></th></tr></thead><tbody>
    ${rows.map((r) => `<tr><td>${systemCell(r.system)}</td>
      <td class="r num"><b>${r.total}</b>${r.diff != null && r.diff !== 0 ? `<br><small class="${r.diff > 0 ? "ok-text" : "warn-text"}">${r.diff > 0 ? "+" : ""}${r.diff}</small>` : ""}</td>
      ${kinds.map((k) => `<td class="r num ${r.counts[k] ? "" : "muted"}">${r.counts[k] || "-"}</td>`).join("")}
      <td><small>${esc(ago(r.at))}${r.by ? `<br><span class="muted">${esc(r.by)}</span>` : ""}<br><span class="muted">${tr("{0} 回", r.scans)}</span></small></td>
      <td><details class="mini-details"><summary>${tr("中身")}</summary><ul class="sig-list">${r.sigs.map((s) => `<li><b>${esc(s.id)}</b> ${KIND_LABEL[s.kind] || ""} <small class="muted">${esc(s.name || "")} ${esc(s.signal || "")}</small></li>`).join("")}</ul></details>
        <button class="icon-btn" type="button" title="${tr("この星系の記録を消す")}" data-del="${r.system.id}">×</button></td></tr>`).join("")}</tbody></table></div>`;
}

$("#sigs").addEventListener("click", async (ev) => {
  const b = ev.target.closest("[data-del]");
  if (!b || !confirm(tr("この星系の記録をすべて消しますか？"))) return;
  try {
    await request("DELETE", `/api/sigs/system/${b.dataset.del}`);
    loadSigs();
  } catch (e) {
    toast(e.message, "error");
  }
});
["#sig-kind", "#sig-sort"].forEach((s) => $(s).addEventListener("change", () => sigData && renderSigs()));
$("#sig-days").addEventListener("change", loadSigs);
$("#sig-reload").addEventListener("click", loadSigs);

// ---------- 2. Thera・Turnur ----------

async function originName() {
  const typed = $("#scout-from").value.trim();
  if (typed) return typed;
  try {
    const d = await request("GET", "/api/wormhole/locations");
    return d.characters.find((c) => c.character_id === gameCharId())?.system?.name || "";
  } catch {
    return "";
  }
}

const SIZE_ORDER = ["small", "medium", "large", "xlarge", "capital"];

async function loadScout() {
  const box = $("#scout");
  box.innerHTML = `<p class="muted">${tr("調べています…")}</p>`;
  const from = await originName();
  saveJson(SIGNALS_KEY, { ...loadJson(SIGNALS_KEY, {}), scoutFrom: $("#scout-from").value.trim() });
  let d;
  try {
    d = await request("GET", `/api/sigs/scout${from ? `?from=${encodeURIComponent(from)}` : ""}`);
  } catch (e) {
    box.innerHTML = `<div class="warn">${esc(e.message)}</div>`;
    return;
  }
  const size = $("#scout-size").value;
  const kind = $("#scout-kind").value;
  const rows = d.connections.filter((r) => (!size || SIZE_ORDER.indexOf(r.size) >= SIZE_ORDER.indexOf(size))
    && (!kind || r.destination.kind === kind || (kind === "nullsec" && r.destination.kind === "pochven")));
  box.innerHTML = `<p class="muted small-note">${tr("{0}{1} 件 · 出典: {2}", (d.origin ? `${tr("出発地: <b>{0}</b> ·", esc(d.origin.name))} ` : ""), rows.length, esc(d.source))}</p>
    <div class="table-scroll"><table class="orders"><thead><tr><th>${tr("ハブ")}</th><th>${tr("出口の星系")}</th><th class="r">${tr("出発地から")}</th><th>${tr("穴")}</th><th>${tr("通れる艦")}</th><th>${tr("残り")}</th><th></th></tr></thead><tbody>
    ${rows.map((r) => `<tr><td><b>${esc(r.hub)}</b><br><small class="muted">${esc(r.hub_signature || "")}</small></td>
      <td>${systemCell(r.destination)}<br><small class="muted">${tr("シグネチャ {0}", esc(r.signature || "?"))}</small></td>
      <td class="r num">${r.jumps != null ? `${tr("<b>{0}</b> ジャンプ", r.jumps)}` : `<span class="muted">-</span>`}</td>
      <td>${esc(r.wh_type || "")}</td><td><small>${esc(r.size_label || "")}</small></td>
      <td><small>${r.expires_at ? esc(timeLeft(r.expires_at)) : "-"}</small></td>
      <td>${r.destination.kind !== "wormhole" ? `<button class="btn small" type="button" data-dest="${r.destination.id}" data-name="${esc(r.destination.name)}">${tr("🎯 目的地")}</button>` : ""}</td></tr>`).join("")}
    </tbody></table></div>`;
}

$("#scout").addEventListener("click", (ev) => {
  const b = ev.target.closest("[data-dest]");
  if (b) gameAction("/api/ui/waypoint", { destination_id: Number(b.dataset.dest), clear: true }, `${tr("目的地を {0} に設定しました", b.dataset.name)}`);
});
$("#scout-run").addEventListener("click", loadScout);
$("#scout-reload").addEventListener("click", loadScout);
["#scout-size", "#scout-kind"].forEach((s) => $(s).addEventListener("change", loadScout));

// ---------- 3. 星系の活動 ----------

let regionsLoaded = false;

async function loadActivity() {
  const box = $("#activity");
  box.innerHTML = `<p class="muted">${tr("読み込み中…")}</p>`;
  const p = new URLSearchParams({ sec: $("#act-sec").value, sort: $("#act-sort").value, limit: $("#act-limit").value });
  if ($("#act-region").value) p.set("region", $("#act-region").value);
  saveJson(SIGNALS_KEY, { ...loadJson(SIGNALS_KEY, {}), act: Object.fromEntries(p) });
  let d;
  try {
    d = await request("GET", `/api/sigs/activity?${p}`);
  } catch (e) {
    box.innerHTML = `<div class="warn">${esc(e.message)}</div>`;
    return;
  }
  if (!regionsLoaded) {
    const cur = $("#act-region").value;
    $("#act-region").innerHTML = `<option value="">${tr("すべて")}</option>` + d.regions.map((r) => `<option value="${r.id}">${LANG !== "ja" ? esc(r.name) : tr("{0}（{1}）", esc(r.name_ja || r.name), esc(r.name))}</option>`).join("");
    $("#act-region").value = cur;
    regionsLoaded = true;
  }
  box.innerHTML = `<p class="muted small-note">${tr("{0} / {1} 星系 · {2}", d.systems.length, fmtNum(d.total), esc(d.note))}</p>
    <div class="table-scroll"><table class="orders"><thead><tr><th>${tr("星系")}</th><th class="r">${tr("NPC 撃墜")}</th><th class="r">${tr("艦の撃墜")}</th><th class="r">${tr("ポッド")}</th><th class="r">${tr("ジャンプ数")}</th><th></th></tr></thead><tbody>
    ${d.systems.map((r) => `<tr><td>${systemCell(r.system)}</td><td class="r num">${fmtNum(r.npc_kills)}</td>
      <td class="r num ${r.ship_kills >= 10 ? "warn-text" : ""}">${fmtNum(r.ship_kills)}</td><td class="r num">${fmtNum(r.pod_kills)}</td>
      <td class="r num">${r.jumps != null ? fmtNum(r.jumps) : "-"}</td>
      <td>${r.system.kind !== "wormhole" ? `<button class="btn small" type="button" data-dest="${r.system.id}" data-name="${esc(r.system.name)}">🎯</button>` : ""}</td></tr>`).join("")}
    </tbody></table></div>`;
}

$("#activity").addEventListener("click", (ev) => {
  const b = ev.target.closest("[data-dest]");
  if (b) gameAction("/api/ui/waypoint", { destination_id: Number(b.dataset.dest), clear: true }, `${tr("目的地を {0} に設定しました", b.dataset.name)}`);
});
["#act-region", "#act-sec", "#act-sort", "#act-limit"].forEach((s) => $(s).addEventListener("change", loadActivity));

// ---------- インカージョン ----------

async function loadIncursions() {
  const box = $("#incursions");
  try {
    const d = await request("GET", "/api/sigs/incursions");
    box.innerHTML = d.incursions.length ? `<div class="clone-grid">${d.incursions.map((i) => `<div class="card">
      <h3>${esc(i.constellation || "")} ${secBadge(i.staging)}</h3>
      <div>${tr("拠点: <b>{0}</b> <small class=\"muted\">{1}</small>", esc(i.staging.name), esc(nm(i.staging, "region_ja", "region") || i.staging.region || ""))}</div>
      <small class="muted">${tr("状態 {0} · 影響度 {1}{2}", esc(i.state || ""), fmtPct((i.influence || 0) * 100, 0), i.has_boss ? tr(" · ボス出現") : "")}</small>
      <div class="small-note">${i.systems.map((s) => `${esc(s.name)} ${secBadge(s)}`).join(" ")}</div></div>`).join("")}</div>`
      : `<p class="muted">${tr("インカージョンはありません。")}</p>`;
  } catch (e) {
    box.innerHTML = `<div class="warn">${esc(e.message)}</div>`;
  }
}

(async () => {
  if (saved.scoutFrom) $("#scout-from").value = saved.scoutFrom;
  if (saved.act) {
    ["sec", "sort", "limit"].forEach((k) => { if (saved.act[k]) $(`#act-${k}`).value = saved.act[k]; });
    if (saved.act.region) $("#act-region").innerHTML += `<option value="${saved.act.region}" selected>${tr("前回の地域")}</option>`;
  }
  try {
    const { characters } = await request("GET", "/api/characters");
    $("#game-char").innerHTML = gameCharSelect(characters.filter((c) => !c.missing));
  } catch (e) {
    toast(e.message, "error");
  }
  loadSigs();
  loadScout();
  loadActivity();
  loadIncursions();
})();
