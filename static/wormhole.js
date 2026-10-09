"use strict";
// ワームホール: 今いる星系・穴の判別・通れる艦・穴の潰しの計算・スキャン結果の整理

const WH_CHAR_KEY = "wormhole:character";
const ROLL_KEY = "wormhole:roll";
const SCAN_KEY = "wormhole:scan";      // {星系名: [シグネチャ]}（前回の貼り付け）
const SIG_CODE_KEY = "wormhole:codes"; // {"星系名:ABC-123": "H296"}
const MASS_SPREAD = 0.1;               // 穴の総質量のばらつき（±10%）
// ゲーム内の穴の見た目の状態 → 残りの質量（総質量に対する割合）
const STATES = {
  fresh: { label: tr("通常（50% 以上）"), lo: 0.5, hi: 1 },
  reduced: { label: tr("縮小（50% 未満）"), lo: 0.1, hi: 0.5 },
  critical: { label: tr("危険（10% 未満）"), lo: 0, hi: 0.1 },
};

let types = [];
const byCode = new Map();
let charId = null;
let ships = null;
let locations = [];
let currentCode = "";

const fmtMass = (kg) => {
  if (kg == null) return "-";
  const m = kg / 1e6;
  return `${m.toLocaleString(LOCALE, { maximumFractionDigits: m < 10 ? 2 : 1 })}M kg`;
};
const massTitle = (kg) => `${fmtNum(Math.round(kg))} kg`;
const fmtHours = (h) => (h == null ? "-" : h >= 24 && h % 24 === 0 ? `${tr("{0} 日（{1} 時間）", h / 24, h)}` : `${tr("{0} 時間", fmtNum(h))}`);

function classBadge(label, kind) {
  const cls = { highsec: "sec-hi", lowsec: "sec-low", nullsec: "sec-null", pochven: "sec-null" }[kind] || "sec-wh";
  return `<span class="badge ${cls}">${esc(label)}</span>`;
}

function targetKind(cls) {
  return { 7: "highsec", 8: "lowsec", 9: "nullsec", 25: "pochven", "-1": "pochven" }[cls] || "wormhole";
}

// ---------- 今いる星系 ----------

function systemLink(s) {
  const url = s.kind === "wormhole" ? `https://anoik.is/systems/${encodeURIComponent(s.name)}`
    : `https://evemaps.dotlan.net/system/${encodeURIComponent(s.name.replace(/ /g, "_"))}`;
  return `<a href="${url}" target="_blank" rel="noopener noreferrer">${esc(s.name)}</a>`;
}

function locationCard(c) {
  let body;
  if (c.needs_login) body = `<span class="muted">${tr("今いる星系を表示するには <a href=\"/login\">再ログイン</a> が必要です。")}</span>`;
  else if (c.error) body = `<span class="warn-text">${tr("取得できませんでした（{0}）", esc(c.error))}</span>`;
  else {
    const s = c.system;
    const sec = s.kind === "wormhole" ? "" : `<span class="muted">${tr("セキュリティ {0}", s.security_display.toFixed(1))}</span>`;
    body = `<div class="wh-loc-system"><b>${systemLink(s)}</b> ${classBadge(s.label, s.kind)} ${sec}</div>
      <small class="muted">${esc(s.region)} / ${esc(s.constellation)}${c.docked ? tr(" · ドック中") : ""}</small>
      ${c.ship ? `<div class="small-note">🚀 ${esc(nm(c.ship))}${c.ship.name ? ` <span class="muted">「${esc(c.ship.name)}」</span>` : ""}</div>` : ""}`;
  }
  const current = c.character_id === charId ? " current" : "";
  return `<div class="wh-loc${current}"><div class="wh-loc-name">${esc(c.character_name)}</div>${body}</div>`;
}

async function loadLocations() {
  $("#loc-refresh").disabled = true;
  try {
    ({ characters: locations } = await request("GET", "/api/wormhole/locations"));
    renderLocations();
  } catch (e) {
    $("#locations").innerHTML = `<div class="warn">${esc(e.message)}</div>`;
  } finally {
    $("#loc-refresh").disabled = false;
  }
}

function renderLocations() {
  $("#locations").innerHTML = locations.length ? locations.map(locationCard).join("")
    : `<p class="muted">${tr("キャラクターがいません。<a href=\"/login\">キャラクターを追加</a>してください。")}</p>`;
  const me = locations.find((c) => c.character_id === charId);
  $("#scan-where").textContent = me?.system ? `${tr("比較する星系: {0}（{1} の現在地）", me.system.name, me.character_name)}` : tr("比較する星系: 不明（現在地を取得できないとき）");
}

const currentSystemName = () => $("#scan-system")?.value.trim()
  || locations.find((c) => c.character_id === charId)?.system?.name || tr("不明");

// ---------- 穴の判別 ----------

function whSummary(t) {
  if (t.target_class == null) {
    return `<div class="wh-card"><div class="wh-title"><b>${esc(t.code)}</b> ${classBadge(tr("行き先はさまざま"), "wormhole")}</div>
      <p>${esc(t.note || "")}</p></div>`;
  }
  const size = t.max_jump_mass <= 5e6 ? tr("フリゲート・駆逐艦まで") : t.max_jump_mass <= 62e6 ? tr("巡洋艦・巡洋戦艦まで")
    : t.max_jump_mass <= 410e6 ? tr("戦艦まで（キャピタル不可）") : tr("キャピタル艦も可（艦による）");
  return `<div class="wh-card">
    <div class="wh-title"><b>${esc(t.code)}</b> → ${classBadge(t.target_label, targetKind(t.target_class))}</div>
    <dl class="wh-stats">
      <div><dt>${tr("寿命")}</dt><dd>${esc(fmtHours(t.lifetime_hours))}</dd></div>
      <div><dt>${tr("総質量")}</dt><dd title="${esc(massTitle(t.total_mass))}">${fmtMass(t.total_mass)} <small class="muted">${tr("（±10%）")}</small></dd></div>
      <div><dt>${tr("1 回に通れる質量")}</dt><dd title="${esc(massTitle(t.max_jump_mass))}">${fmtMass(t.max_jump_mass)} <small class="muted">${size}</small></dd></div>
      ${t.mass_regen ? `<div><dt>${tr("質量の回復")}</dt><dd>${tr("{0} / 日", fmtMass(t.mass_regen))}</dd></div>` : ""}
    </dl></div>`;
}

function setCode(raw) {
  const code = String(raw || "").trim().toUpperCase().replace(/^WORMHOLE\s+/, "");
  currentCode = byCode.has(code) ? code : "";
  const t = byCode.get(currentCode);
  $("#wh-result").innerHTML = t ? whSummary(t)
    : code ? `<p class="warn-text">${tr("「{0}」という穴は見つかりません。", esc(code))}</p>` : "";
  renderPass();
  renderRoll();
}

let tableFilter = "all";
const FILTERS = [["all", tr("すべて")], ["j", tr("J 空間")], ["k", tr("K 空間")], ["other", tr("Thera・Pochven・ドリフター")]];

function renderTable() {
  $("#wh-filter").innerHTML = FILTERS.map(([k, label]) =>
    `<button class="btn small${k === tableFilter ? " primary" : ""}" type="button" data-filter="${k}">${label}</button>`).join("");
  const match = (t) => {
    const c = t.target_class;
    if (tableFilter === "j") return c >= 1 && c <= 6;
    if (tableFilter === "k") return c >= 7 && c <= 9;
    if (tableFilter === "other") return c != null && (c < 1 || c > 9);
    return true;
  };
  const rows = types.filter(match).sort((a, b) => (a.target_class ?? 99) - (b.target_class ?? 99) || a.code.localeCompare(b.code));
  $("#wh-table").innerHTML = `<thead><tr><th>${tr("コード")}</th><th>${tr("行き先")}</th><th class="r">${tr("寿命")}</th><th class="r">${tr("総質量")}</th><th class="r">${tr("1 回の質量")}</th></tr></thead>
    <tbody>${rows.map((t) => `<tr><td><a href="#" data-code="${esc(t.code)}">${esc(t.code)}</a></td>
      <td>${t.target_label ? classBadge(t.target_label, targetKind(t.target_class)) : `<span class="muted">${tr("さまざま")}</span>`}</td>
      <td class="r">${t.lifetime_hours != null ? `${fmtNum(t.lifetime_hours)} h` : "-"}</td>
      <td class="r">${fmtMass(t.total_mass)}</td><td class="r">${fmtMass(t.max_jump_mass)}</td></tr>`).join("")}</tbody>`;
}

// ---------- 通れる艦 ----------

function passBadge(s, t) {
  if (s.hot <= t.max_jump_mass) return `<span class="badge ok">${tr("✓ 通れる")}</span>`;
  if (s.cold <= t.max_jump_mass) return `<span class="badge queued">${tr("▲ 推進を止めれば通れる")}</span>`;
  return `<span class="badge missing">${tr("✕ 重すぎる")}</span>`;
}

function renderPass() {
  const t = byCode.get(currentCode);
  const box = $("#pass-body");
  if (!t) { box.innerHTML = `<p class="muted">${tr("穴のコードを入れると判定します。")}</p>`; return; }
  if (t.max_jump_mass == null) { box.innerHTML = `<p class="muted">${tr("K162 は反対側の穴の種類で決まるため、判定できません。反対側の穴のコードを入れてください。")}</p>`; return; }
  if (!ships) { box.innerHTML = `<p class="muted">${tr("艦を読み込み中…")}</p>`; return; }
  if (!ships.length) { box.innerHTML = `<p class="muted">${tr("判定できる艦・フィットがありません。")}</p>`; return; }
  box.innerHTML = `<div class="table-scroll"><table class="orders"><thead><tr><th>${tr("艦・フィット")}</th><th>${tr("種類")}</th>
    <th class="r">cold</th><th class="r">hot</th><th>${tr("判定")}</th></tr></thead><tbody>
    ${ships.map((s) => `<tr><td><b>${esc(s.label)}</b>${s.label !== nm(s, "ship_ja", "ship_en") ? `<br><small class="muted">${esc(nm(s, "ship_ja", "ship_en"))}</small>` : ""}</td>
      <td><small>${esc(s.source)}${s.location ? `<br><span class="muted">${esc(s.location)}</span>` : ""}</small></td>
      <td class="r" title="${esc(massTitle(s.cold))}">${fmtMass(s.cold)}</td>
      <td class="r" title="${esc(massTitle(s.hot))}">${s.prop ? fmtMass(s.hot) : `<span class="muted">${tr("推進なし")}</span>`}</td>
      <td>${passBadge(s, t)}</td></tr>`).join("")}</tbody></table></div>`;
}

async function loadShips() {
  ships = null;
  renderPass();
  try {
    ({ ships } = await request("GET", `/api/wormhole/ships?character_id=${charId}`));
  } catch (e) {
    ships = [];
    toast(e.message, "error");
  }
  renderPass();
  renderRoll();
}

// ---------- 穴の潰し ----------

let roll = loadJson(ROLL_KEY, null); // {code, entries: [{kind: "jump", label, mass} | {kind: "state", state}]}
const saveRoll = () => saveJson(ROLL_KEY, roll);

// 残りの質量の幅 [lo, hi]。見た目の状態を記録するたびに幅を絞る
function remainingRange(t, entries) {
  const total = t.total_mass;
  let lo = total * (1 - MASS_SPREAD), hi = total * (1 + MASS_SPREAD);
  let conflict = false;
  for (const e of entries) {
    if (e.kind === "jump") { lo -= e.mass; hi -= e.mass; continue; }
    const st = STATES[e.state];
    const sLo = st.lo * total * (1 - MASS_SPREAD), sHi = st.hi * total * (1 + MASS_SPREAD);
    const nLo = Math.max(lo, sLo), nHi = Math.min(hi, sHi);
    if (nLo > nHi) { conflict = true; lo = sLo; hi = sHi; } else { lo = nLo; hi = nHi; }
  }
  return { lo: Math.max(lo, 0), hi: Math.max(hi, 0), conflict };
}

function shipOptions() {
  return (ships || []).map((s, i) => `<option value="${i}">${tr("{0}（cold {1}{2}）", esc(s.label), fmtMass(s.cold), s.prop ? ` / hot ${fmtMass(s.hot)}` : "")}</option>`).join("");
}

function forecast(t, range, mass) {
  if (mass > t.max_jump_mass) return `<span class="warn-text">${tr("この質量ではこの穴を通れません。")}</span>`;
  const safe = Math.floor(range.lo / mass);
  const risky = range.hi >= mass ? Math.floor(range.hi / mass) : 0;
  if (range.lo < mass && range.hi >= mass) return `<span class="warn-text">${tr("⚠ 次に跳ぶと潰れる可能性があります（取り残しに注意）。")}</span>`;
  if (range.hi < mass) return `<span class="warn-text">${tr("次に跳ぶと潰れます。")}</span>`;
  return `${tr("あと <b>{0} 回</b> は潰れずに跳べます{1}。", safe, (risky > safe ? `${tr("（{0}〜{1} 回目で潰れる可能性）", safe + 1, risky + 1)}` : ""))}`;
}

function renderRoll() {
  const box = $("#roll-body");
  const t = byCode.get(roll?.code || currentCode);
  if (!t) { box.innerHTML = `<p class="muted">${tr("穴のコードを入れると計算できます。")}</p>`; return; }
  if (t.total_mass == null) { box.innerHTML = `<p class="muted">${tr("K162 は総質量が分からないため、反対側の穴のコードで計算してください。")}</p>`; return; }
  if (!roll) {
    box.innerHTML = `<p>${tr("穴 <b>{0}</b>（総質量 {1}、1 回 {2}）の潰しを記録します。", esc(t.code), fmtMass(t.total_mass), fmtMass(t.max_jump_mass))}</p>
      <button class="btn primary" type="button" data-roll="start">${tr("この穴で記録を始める")}</button>`;
    return;
  }
  const range = remainingRange(t, roll.entries);
  const other = currentCode && currentCode !== roll.code
    ? `<div class="alert info"><span>${tr("入力中の穴（{0}）とは別の穴を記録しています。", esc(currentCode))}</span>
        <button class="btn small" type="button" data-roll="restart">${tr("{0} で記録し直す", esc(currentCode))}</button></div>` : "";
  const log = roll.entries.map((e, i) => `<li>${e.kind === "jump"
    ? `🚀 ${esc(e.label)} <span class="muted">${fmtMass(e.mass)}</span>`
    : `${tr("👁 見た目の状態: <b>{0}</b>", esc(STATES[e.state].label))}`}
    <button class="icon-btn" type="button" title="${tr("この記録を消す")}" data-roll="remove" data-index="${i}">×</button></li>`).join("");
  const pct = (v) => fmtPct((v / t.total_mass) * 100, 0);
  const sel = Number(loadJson("wormhole:roll-ship", 0));
  const s = sel === -1 ? null : ships?.[sel] || ships?.[0];
  box.innerHTML = `${other}
    <div class="wh-title"><b>${esc(t.code)}</b> → ${t.target_label ? classBadge(t.target_label, targetKind(t.target_class)) : ""}
      <span class="muted">${tr("総質量 {0}（±10%）・1 回 {1}", fmtMass(t.total_mass), fmtMass(t.max_jump_mass))}</span></div>
    <div class="wh-remaining"><span class="muted">${tr("残りの質量（目安）")}</span>
      <b>${fmtMass(range.lo)} 〜 ${fmtMass(range.hi)}</b> <small class="muted">${tr("（元の {0}〜{1}）", pct(range.lo), pct(range.hi))}</small>
      <div class="wh-bar"><span style="left:${Math.min(100, (range.lo / (t.total_mass * 1.1)) * 100)}%;width:${Math.max(1, ((range.hi - range.lo) / (t.total_mass * 1.1)) * 100)}%"></span></div>
      ${range.conflict ? `<small class="warn-text">${tr("記録した質量と見た目の状態が合わないため、見た目の状態を優先しました。")}</small>` : ""}</div>
    <div class="wh-roll-form">
      <label><span>${tr("艦")}</span><select id="roll-ship">${shipOptions()}<option value="custom">${tr("質量を入力…")}</option></select></label>
      <label id="roll-custom-wrap" hidden><span>${tr("質量（M kg）")}</span><input id="roll-custom" type="number" min="0" step="0.1"></label>
      <label><span>${tr("状態")}</span><select id="roll-mode"><option value="hot">${tr("hot（推進 ON）")}</option><option value="cold">${tr("cold（推進 OFF）")}</option></select></label>
      <button class="btn primary" type="button" data-roll="jump">${tr("通過を記録")}</button>
    </div>
    <p class="small-note" id="roll-forecast"></p>
    <div class="wh-roll-state"><span class="muted">${tr("ゲーム内の穴の見た目:")}</span>
      ${Object.entries(STATES).map(([k, st]) => `<button class="btn small" type="button" data-roll="state" data-state="${k}">${esc(st.label)}</button>`).join("")}</div>
    ${log ? `<ol class="wh-log">${log}</ol>` : `<p class="muted">${tr("まだ記録がありません。穴を通るたびに「通過を記録」してください（往復なら 2 回）。")}</p>`}
    <div class="fit-actions"><button class="btn small danger" type="button" data-roll="reset">${tr("記録をすべて消す")}</button></div>`;
  if (s) $("#roll-ship").value = String(ships.indexOf(s));
  else $("#roll-ship").value = "custom";
  syncRollForm(t, range);
}

function selectedJump() {
  const shipSel = $("#roll-ship").value;
  const hot = $("#roll-mode").value === "hot";
  if (shipSel === "custom") {
    const m = Number($("#roll-custom").value) * 1e6;
    return m > 0 ? { label: `${tr("質量を入力 {0}", fmtMass(m))}`, mass: m } : null;
  }
  const s = ships[Number(shipSel)];
  return s ? { label: `${tr("{0}（{1}）", s.label, hot && s.prop ? "hot" : "cold")}`, mass: hot ? s.hot : s.cold } : null;
}

function syncRollForm(t, range) {
  $("#roll-custom-wrap").hidden = $("#roll-ship").value !== "custom";
  const j = selectedJump();
  $("#roll-forecast").innerHTML = j ? `${tr("この艦（{0}）で: {1}", fmtMass(j.mass), forecast(t, range, j.mass))}` : "";
}

$("#roll-body").addEventListener("change", (ev) => {
  if (ev.target.id === "roll-ship") saveJson("wormhole:roll-ship", ev.target.value === "custom" ? -1 : Number(ev.target.value));
  const t = byCode.get(roll?.code);
  if (t) syncRollForm(t, remainingRange(t, roll.entries));
});
$("#roll-body").addEventListener("input", (ev) => {
  if (ev.target.id !== "roll-custom") return;
  const t = byCode.get(roll?.code);
  if (t) syncRollForm(t, remainingRange(t, roll.entries));
});

$("#roll-body").addEventListener("click", (ev) => {
  const el = ev.target.closest("[data-roll]");
  if (!el) return;
  switch (el.dataset.roll) {
    case "start":
    case "restart":
      if (el.dataset.roll === "restart" && !confirm(tr("今の記録を消して、新しい穴で記録し直しますか？"))) return;
      roll = { code: currentCode, entries: [] };
      break;
    case "jump": {
      const j = selectedJump();
      if (!j) { toast(tr("艦を選ぶか、質量を入力してください。"), "error"); return; }
      const t = byCode.get(roll.code);
      if (j.mass > t.max_jump_mass) { toast(tr("この質量ではこの穴を通れません。"), "error"); return; }
      roll.entries.push({ kind: "jump", ...j });
      break;
    }
    case "state":
      roll.entries.push({ kind: "state", state: el.dataset.state });
      break;
    case "remove":
      roll.entries.splice(Number(el.dataset.index), 1);
      break;
    case "reset":
      if (!confirm(tr("穴の潰しの記録をすべて消しますか？"))) return;
      roll = null;
      break;
  }
  saveRoll();
  renderRoll();
});

// ---------- スキャン結果の整理 ----------

const KINDS = [
  ["wormhole", tr("🌀 ワームホール"), /wormhole|ワームホール/i],
  ["data", tr("💾 データ"), /data site|データ/i],
  ["relic", tr("🏺 レリック"), /relic site|遺物|レリック/i],
  ["gas", tr("☁ ガス"), /gas site|ガス/i],
  ["ore", tr("⛏ 鉱石"), /ore site|鉱石|鉱床/i],
  ["combat", tr("⚔ 戦闘"), /combat site|戦闘|コンバット/i],
];
const KIND_ORDER = [...KINDS.map(([k]) => k), "anomaly", "unknown"];
const KIND_LABEL = { ...Object.fromEntries(KINDS.map(([k, l]) => [k, l])), anomaly: tr("✦ アノマリ"), unknown: tr("❔ 未判別（スキャン不足）") };

function parseScan(text) {
  const sigs = [];
  for (const line of text.split(/\r?\n/)) {
    const cols = line.split("\t").map((c) => c.trim());
    const id = cols.find((c) => /^[A-Z]{3}-\d{3}$/.test(c));
    if (!id) continue;
    const signal = cols.find((c) => /^[\d.,]+\s*%$/.test(c));
    const distance = cols.find((c) => /^[\d.,]+\s*(AU|km|m)$/i.test(c));
    const rest = cols.filter((c) => c !== id && c !== signal && c !== distance); // 空の列（未判別の種類）も位置を保つ
    const [group = "", type = "", ...names] = rest;
    const kind = KINDS.find(([, , re]) => re.test(type) || (!type && re.test(names.join(" "))))?.[0]
      || (/anomaly|アノマリ/i.test(group) ? "anomaly" : "unknown");
    sigs.push({ id, group, type, name: names.join(" "), signal: signal || "", distance: distance || "", kind });
  }
  return sigs;
}

function codeCell(system, sig) {
  const codes = loadJson(SIG_CODE_KEY, {});
  const code = codes[`${system}:${sig.id}`] || "";
  const t = byCode.get(code);
  return `<input class="sig-code" list="wh-codes" data-sig="${esc(sig.id)}" value="${esc(code)}" placeholder="${tr("コード")}" size="6" spellcheck="false">
    <span class="sig-dest">${t ? (t.target_label ? classBadge(t.target_label, targetKind(t.target_class)) : `<span class="muted">K162</span>`) : ""}</span>`;
}

function renderScan(sigs, previous, system) {
  const prevIds = new Set(previous.map((s) => s.id));
  const nowIds = new Set(sigs.map((s) => s.id));
  const gone = previous.filter((s) => !nowIds.has(s.id));
  const groups = KIND_ORDER.map((k) => [k, sigs.filter((s) => s.kind === k)]).filter(([, list]) => list.length);
  const counts = groups.map(([k, list]) => `<span class="badge queued">${esc(KIND_LABEL[k])} ${list.length}</span>`).join(" ");
  const table = (k, list) => `<h3>${esc(KIND_LABEL[k])} <span class="muted">${list.length}</span></h3>
    <div class="table-scroll"><table class="orders"><thead><tr><th>ID</th><th>${tr("名前")}</th><th class="r">${tr("強度")}</th><th class="r">${tr("距離")}</th>${k === "wormhole" ? tr("<th>コード → 行き先</th>") : ""}</tr></thead>
    <tbody>${list.map((s) => `<tr><td><b>${esc(s.id)}</b>${previous.length && !prevIds.has(s.id) ? ` <span class="badge ok">NEW</span>` : ""}</td>
      <td>${esc(s.name || s.type || s.group)}</td><td class="r">${esc(s.signal)}</td><td class="r">${esc(s.distance)}</td>
      ${k === "wormhole" ? `<td class="sig-code-cell">${codeCell(system, s)}</td>` : ""}</tr>`).join("")}</tbody></table></div>`;
  $("#scan-result").innerHTML = `<p>${tr("{0} 件（{1}）: {2}", sigs.length, esc(system), counts)}</p>
    ${gone.length ? `<div class="alert info"><span>${tr("前回から消えたシグネチャ: {0}", gone.map((s) => `${tr("<b>{0}</b>（{1}）", esc(s.id), esc(KIND_LABEL[s.kind]))}`).join(LIST_SEP))}</span></div>` : ""}
    ${groups.map(([k, list]) => table(k, list)).join("")}`;
}

$("#scan-run").addEventListener("click", () => {
  const sigs = parseScan($("#scan-input").value);
  if (!sigs.length) { toast(tr("シグネチャが見つかりません。プローブスキャナーの一覧をそのまま貼り付けてください。"), "error"); return; }
  const system = currentSystemName();
  const saved = loadJson(SCAN_KEY, {});
  renderScan(sigs, saved[system] || [], system);
  recordScan(system, sigs);
  saved[system] = sigs;
  saveJson(SCAN_KEY, saved);
});

// スキャン結果をサーバーに記録する（シグネチャ・星系のページで一覧）
async function recordScan(system, sigs) {
  if (!system || system === tr("不明")) {
    toast(tr("星系が分からないため記録しませんでした。「スキャンした星系」を入力してください。"), "error");
    return;
  }
  try {
    const me = locations.find((c) => c.character_id === charId);
    const d = await request("POST", "/api/sigs/record", { system, sigs, character_name: me?.character_name || "" });
    const diff = d.previous ? d.snapshot.total - d.previous.total : null;
    toast(`${tr("{0} のシグネチャ {1} 件を記録しました{2}。", d.system.name, d.snapshot.total, (diff != null ? `${tr("（前回から {0}{1}）", diff >= 0 ? "+" : "", diff)}` : ""))}`, "ok");
  } catch (e) {
    toast(e.message, "error");
  }
}

$("#scan-clear").addEventListener("click", () => {
  const saved = loadJson(SCAN_KEY, {});
  delete saved[currentSystemName()];
  saveJson(SCAN_KEY, saved);
  toast(tr("この星系の前回の記録を消しました。"), "ok");
});

$("#scan-result").addEventListener("change", (ev) => {
  const input = ev.target.closest(".sig-code");
  if (!input) return;
  const code = input.value.trim().toUpperCase();
  const codes = loadJson(SIG_CODE_KEY, {});
  codes[`${currentSystemName()}:${input.dataset.sig}`] = code;
  saveJson(SIG_CODE_KEY, codes);
  const t = byCode.get(code);
  input.value = code;
  input.nextElementSibling.innerHTML = t ? (t.target_label ? classBadge(t.target_label, targetKind(t.target_class)) : `<span class="muted">K162</span>`)
    : code ? `<span class="warn-text">${tr("不明")}</span>` : "";
  if (t) { $("#wh-code").value = code; setCode(code); }
});

// ---------- 初期化 ----------

$("#wh-code").addEventListener("input", (ev) => setCode(ev.target.value));
$("#wh-filter").addEventListener("click", (ev) => {
  const b = ev.target.closest("[data-filter]");
  if (!b) return;
  tableFilter = b.dataset.filter;
  renderTable();
});
$("#wh-table").addEventListener("click", (ev) => {
  const a = ev.target.closest("[data-code]");
  if (!a) return;
  ev.preventDefault();
  $("#wh-code").value = a.dataset.code;
  setCode(a.dataset.code);
  $("#wh-code").scrollIntoView({ behavior: "smooth", block: "center" });
});
$("#loc-refresh").addEventListener("click", loadLocations);
$("#wh-char").addEventListener("change", () => {
  charId = Number($("#wh-char").value);
  saveJson(WH_CHAR_KEY, charId);
  renderLocations();
  loadShips();
});

(async () => {
  try {
    ({ types } = await request("GET", "/api/wormhole/types"));
    types.forEach((t) => byCode.set(t.code, t));
    $("#wh-codes").innerHTML = types.map((t) => `<option value="${esc(t.code)}">${esc(t.target_label || "K162")}</option>`).join("");
    renderTable();
    setCode(roll?.code || "");
    if (roll?.code) $("#wh-code").value = roll.code;
  } catch (e) {
    $("#wh-result").innerHTML = `<div class="warn">${esc(e.message)}</div>`;
  }
  try {
    const { characters } = await request("GET", "/api/characters");
    const ready = characters.filter((c) => !c.missing);
    if (ready.length) {
      const saved = loadJson(WH_CHAR_KEY, null);
      charId = ready.some((c) => c.character_id === saved) ? saved : ready[0].character_id;
      $("#wh-char").innerHTML = ready.map((c) =>
        `<option value="${c.character_id}" ${c.character_id === charId ? "selected" : ""}>${esc(c.character_name)}</option>`).join("");
      loadShips();
    }
  } catch (e) {
    toast(e.message, "error");
  }
  loadLocations();
})();
