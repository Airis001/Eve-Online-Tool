"use strict";
// フィットの作成: 艦・モジュール・ドローン・カーゴを選んで、その場で計算する

const DRAFT_KEY = "fitbuilder:draft";
const IMPORT_KEY = "fitbuilder:eft"; // 他のページの「✏️ 編集」から渡される EFT
const FB_CHAR_KEY = "fitbuilder:character";
const T1_FLAG_KEY = "fitbuilder:t1"; // 他のページの「T1 で試す」から開いたとき
let undoStack = []; // T1 に替える前のフィット（元に戻す用）

let fit = loadJson(DRAFT_KEY, null) || { ship: null, name: "", modules: [], drones: [], cargo: [] };
let result = null;
let evalTimer = null;
let characters = [];

const saveDraft = () => saveJson(DRAFT_KEY, fit);

// ---------- 検索 ----------

function searchBox(input, list, filter, onPick) {
  let timer = null;
  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const q = input.value.trim();
      if (!q) { list.hidden = true; return; }
      try {
        const d = await request("GET", `/api/search?checks=0&q=${encodeURIComponent(q)}`);
        const rows = d.results.filter(filter);
        list.innerHTML = rows.length ? rows.map((r) => `<li data-id="${r.id}" data-ja="${esc(nm(r))}"><span class="names"><b>${esc(nm(r))}</b>
          <small>${nmSub(r, " · ")}${esc(r.category)} / ${esc(r.group)}</small></span></li>`).join("") : `<li class="empty">${tr("見つかりません")}</li>`;
        list.hidden = false;
      } catch (e) {
        toast(e.message, "error");
      }
    }, 200);
  });
  list.addEventListener("click", (ev) => {
    const li = ev.target.closest("li[data-id]");
    if (!li) return;
    list.hidden = true;
    input.value = "";
    onPick(Number(li.dataset.id), nm(li.dataset));
  });
}

searchBox($("#fb-ship-search"), $("#fb-ship-results"), (r) => r.category === tr("艦船"), (id, ja) => {
  fit.ship = { type_id: id, ja };
  if (!fit.name) fit.name = "";
  changed();
});

searchBox($("#fb-item-search"), $("#fb-item-results"), (r) => r.category !== tr("艦船"), async (id) => {
  if (!fit.ship) { toast(tr("先に艦を選んでください。"), "error"); return; }
  try {
    const info = await request("GET", `/api/fitbuilder/item?type_id=${id}`);
    if (info.kind === "module") fit.modules.push(id);
    else if (info.kind === "drone") addTo(fit.drones, id, 1);
    else addTo(fit.cargo, id, info.kind === "charge" ? 100 : 1);
    changed();
  } catch (e) {
    toast(e.message, "error");
  }
});

document.addEventListener("click", (ev) => {
  if (!ev.target.closest(".search-wrap")) document.querySelectorAll(".results").forEach((l) => { l.hidden = true; });
});

function addTo(list, id, qty) {
  const row = list.find(([t]) => t === id);
  if (row) row[1] += qty; else list.push([id, qty]);
}

// ---------- 計算 ----------

function changed() {
  saveDraft();
  clearTimeout(evalTimer);
  evalTimer = setTimeout(evaluate, 150);
}

async function evaluate() {
  if (!fit.ship) { renderEmpty(); return; }
  try {
    result = await request("POST", "/api/fitbuilder/evaluate", {
      ship_type_id: fit.ship.type_id, modules: fit.modules, drones: fit.drones, cargo: fit.cargo,
      name: fit.name, character_id: Number($("#fb-char").value) || null,
    });
  } catch (e) {
    toast(e.message, "error");
    return;
  }
  renderFit();
  renderStats();
}

function renderEmpty() {
  $("#fb-fit").innerHTML = `<div class="card empty-card">${tr("左の「艦」で艦を選んでください。")}</div>`;
  $("#fb-stats").innerHTML = "";
}

// 同じ装備の仲間（T1・メタ・T2・勢力など）の選択。✓ は今のスキルで使えるもの
function variantSelect(item, attr) {
  if (!item.variants?.length) return "";
  const opts = item.variants.map((v) => `<option value="${v.type_id}" ${v.current ? "selected" : ""}>${v.usable ? "✓" : "✕"} ${esc(v.label)} ${esc(nm(v))}</option>`).join("");
  return `<select class="fb-variant" ${attr} title="${tr("同じ装備の仲間に替える（✓ は今のスキルで使える）")}">${opts}</select>`;
}

const lackBadge = (item) => (item.usable === false ? ` <span class="badge missing" title="${tr("選んだキャラクターのスキルが足りません")}">${tr("スキル不足")}</span>` : "");

function slotBlock(slot) {
  const d = result;
  const list = d.slots[slot] || [];
  const total = d.usage.total[slot] || 0;
  if (!total && !list.length) return "";
  const over = list.length > total;
  const hard = slot === "high" ? ` <small class="muted">${tr("タレット {0}/{1}・ランチャー {2}/{3}", d.usage.turrets, d.usage.turret_total, d.usage.launchers, d.usage.launcher_total)}</small>` : "";
  const rows = list.map((m) => `<li class="${m.usable === false ? "fb-lack" : ""}"><span>${esc(nm(m))}${lackBadge(m)}${m.charge ? ` <small class="muted">+ ${esc(m.charge)}</small>`
    : m.needs_charge ? ` <small class="warn-text">${tr("弾なし（カーゴに弾を入れると装填）")}</small>` : ""}</span>
    <span class="fb-row-actions">${variantSelect(m, `data-variant-module="${m.index}"`)}
    <button class="icon-btn" type="button" title="${tr("外す")}" data-remove="${m.index}">×</button></span></li>`).join("");
  const empty = Array.from({ length: Math.max(0, total - list.length) }, () => `<li class="fb-empty">${tr("［空き］")}</li>`).join("");
  return `<div class="card fb-slot"><h3>${esc(d.slot_labels[slot])} <small class="${over ? "warn-text" : "muted"}">${list.length} / ${total}</small>${hard}</h3>
    <ul class="fb-list">${rows}${empty}</ul></div>`;
}

function bayBlock(title, rows, kind, extra) {
  return `<div class="card fb-slot"><h3>${title} ${extra}</h3><ul class="fb-list">${rows.length ? rows.map((r) => `<li class="${r.usable === false ? "fb-lack" : ""}"><span>${esc(nm(r))}${lackBadge(r)}</span>
    <span class="fb-qty"><input type="number" min="1" value="${r.qty}" data-qty="${kind}:${r.type_id}"> <small class="muted">${fmtNum(Math.round(r.volume * r.qty * 10) / 10)} m³</small>
    ${variantSelect(r, `data-variant-bay="${kind}:${r.type_id}"`)}
    <button class="icon-btn" type="button" title="${tr("外す")}" data-remove-bay="${kind}:${r.type_id}">×</button></span></li>`).join("")
    : `<li class="fb-empty">${tr("なし")}</li>`}</ul></div>`;
}

function renderFit() {
  const d = result;
  $("#fb-name").value = fit.name;
  $("#fb-fit").innerHTML = `<div class="fb-ship"><h2>${esc(nm(d.ship))} <small class="muted">${nmSub(d.ship)}</small></h2></div>
    ${["high", "med", "low", "rig", "subsystem"].map(slotBlock).join("")}
    ${bayBlock(tr("🛸 ドローンベイ"), d.drones, "drone", `<small class="muted">${tr("{0} / {1} m³・帯域 {2} Mbit/s", fmtNum(d.drone_bay.used), fmtNum(d.drone_bay.total), fmtNum(d.drone_bay.bandwidth))}</small>`)}
    ${bayBlock(tr("📦 カーゴ"), d.cargo, "cargo", `<small class="muted">${fmtNum(Math.round(d.cargo_volume.used * 10) / 10)} / ${fmtNum(Math.round(d.cargo_volume.total))} m³</small>`)}`;
}

function bar(label, r) {
  const pct = r.total ? Math.min(100, (r.used / r.total) * 100) : 0;
  return `<div class="fb-bar"><div class="fb-bar-head"><span>${label}</span><span class="${r.ok ? "" : "warn-text"}">${fmtNum(Math.round(r.used * 10) / 10)} / ${fmtNum(Math.round(r.total * 10) / 10)}</span></div>
    <div class="mini-bar"><span style="width:${pct}%;${r.ok ? "" : "background:var(--miss)"}"></span></div></div>`;
}

function renderStats() {
  const d = result;
  const dps = d.dps;
  const holds = Object.entries(d.holds).filter(([, v]) => v.total).map(([k, v]) => `<div><span class="muted">${esc(HOLD_LABEL[k] || k)}</span> <b>${fmtNum(Math.round(v.total))} m³</b></div>`).join("");
  const ws = d.warp_strength;
  const strength = ws.base + ws.wcs;
  const skills = d.skills.usable ? `<span class="badge ok">${tr("✓ 今すぐ使えます")}</span>`
    : `<span class="badge missing">${tr("訓練 {0}", esc(fmtMinutes(d.skills.minutes)))}</span> <small class="muted">${tr("{0} 手順", d.skills.steps)}</small>`;
  const cost = `<div class="rec-cost" data-bom="${d.bom.map(([t, q, k]) => `${t}:${q}:${k}`).join(",")}" data-has-bay="${d.bom.some(([, , k]) => k === "bay") ? 1 : ""}"></div>`;
  $("#fb-stats").innerHTML = `
    <div class="card"><h3>${tr("判定 <small class=\"muted\">{0} のスキル</small>", esc(d.character_name))}</h3>${skills}
      ${d.errors.length ? `<ul class="fb-errors">${d.errors.map((e) => `<li>⚠ ${esc(e)}</li>`).join("")}</ul>` : `<p class="ok-text small-note">${tr("✓ 装着の問題はありません")}</p>`}
      ${d.approximate?.length ? `<small class="muted">${tr("※ PG / CPU は参考値（{0}）", esc(d.approximate.join(LIST_SEP)))}</small>` : ""}</div>
    <div class="card">${bar(tr("パワーグリッド"), d.resources.power)}${bar("CPU", d.resources.cpu)}${bar(tr("キャリブレーション"), d.resources.calibration)}
      ${d.suggestion?.skills?.length ? `<small class="muted">${tr("足りるスキル: {0}", d.suggestion.skills.map((s) => `${esc(s.name)} ${ROMAN[s.to]}`).join(LIST_SEP))}</small>` : ""}</div>
    <div class="card"><h3>${tr("性能 <small class=\"muted\">目安</small>")}</h3>
      <div class="rec-stat"><span class="rec-big">${fmtNum(Math.round(dps.total))}</span> <span class="muted">DPS</span>
        <small class="muted">${[[tr("タレット"), dps.turret], [tr("ミサイル"), dps.missile], [tr("ドローン"), dps.drone]].filter(([, v]) => v).map(([k, v]) => `${k} ${fmtNum(Math.round(v))}`).join(DOT_SEP)}</small></div>
      ${dps.mining?.total ? `<div>${tr("⛏ 採掘 <b>{0}</b> m³/秒 <small class=\"muted\">（1 時間 {1} m³）</small>", dps.mining.total.toLocaleString(LOCALE, { maximumFractionDigits: 2 }), fmtNum(dps.mining.per_hour))}</div>` : ""}
      ${dps.mining_m3_min ? `<div>${tr("⛏ ドローン採掘 <b>{0}</b> m³/秒 <small class=\"muted\">（1 分 {1} m³）</small>", ((dps.mining_m3_min / 60).toLocaleString(LOCALE, { maximumFractionDigits: 2 })), fmtNum(Math.round(dps.mining_m3_min)))}</div>` : ""}
      <div class="fb-holds">${holds}</div>
      <div>${tr("⏱ ワープまで <b>{0} 秒</b>{1}", d.align.normal.toFixed(1), (d.align.trick != null ? (d.align.effective ? `${tr("（MWD の小技で約 {0} 秒）", d.align.trick.toFixed(0))}` : tr("（MWD の小技の効果なし）")) : ""))}</div>
      <div>${tr("🛡 ワープコアの強度 <b>{0}</b>{1}", ws.base, (ws.wcs ? ` ${tr("→ スタビライザー起動中 <b>{0}</b>", strength)}` : ""))}</div>
      ${dps.notes?.length ? `<small class="muted">${esc(dps.notes.join(LIST_SEP))}</small>` : ""}</div>
    <div class="card"><h3>${tr("購入費")}</h3>${cost}</div>`;
  hydrateJitaCosts($("#fb-stats"));
}

// ---------- 操作 ----------

// ---------- T1 に替える ----------

function pushUndo() {
  undoStack.push(JSON.parse(JSON.stringify(fit)));
  $("#fb-undo").hidden = false;
}

// 一覧（ドローン・カーゴ）の type_id を T1 に替える（同じものがあればまとめる）
function swapBay(list, from, to) {
  const row = list.find(([t]) => t === from);
  if (!row) return;
  const same = list.find(([t]) => t === to);
  if (same) {
    same[1] += row[1];
    list.splice(list.indexOf(row), 1);
  } else {
    row[0] = to;
  }
}

// スキルが足りない装備の替え先。mode: "t1"（T1）/ "meta"（使えるメタ装備のうち一番良いもの。無ければ T1）
function replacementFor(item, mode) {
  const t1 = item.variants?.find((v) => v.group === 1 && !v.level)?.type_id ?? item.t1;
  if (mode === "meta") {
    const usable = (item.variants || []).filter((v) => v.group === 1 && v.usable).sort((a, b) => b.level - a.level);
    if (usable.length) return usable[0].type_id;
  }
  return t1;
}

function swapLacking(mode) {
  if (!result) { toast(tr("艦を選んでください。"), "error"); return; }
  const modules = Object.values(result.slots).flat().filter((m) => m.usable === false)
    .map((m) => [m, replacementFor(m, mode)]).filter(([m, to]) => to && to !== m.type_id);
  const bay = [...result.drones.map((r) => ["drone", r]), ...result.cargo.map((r) => ["cargo", r])]
    .filter(([, r]) => r.usable === false).map(([k, r]) => [k, r, replacementFor(r, mode)]).filter(([, r, to]) => to && to !== r.type_id);
  const lacking = Object.values(result.slots).flat().filter((m) => m.usable === false).length
    + result.drones.filter((r) => r.usable === false).length + result.cargo.filter((r) => r.usable === false).length;
  if (!modules.length && !bay.length) {
    toast(lacking ? tr("スキルが足りない装備に、替えられる T1・メタ装備がありません。") : tr("スキルが足りない装備はありません。"), "ok");
    return;
  }
  pushUndo();
  modules.forEach(([m, to]) => { fit.modules[m.index] = to; });
  bay.forEach(([kind, r, to]) => swapBay(kind === "drone" ? fit.drones : fit.cargo, r.type_id, to));
  const tag = mode === "meta" ? tr("（メタ）") : tr("（T1）");
  if (fit.name && !fit.name.includes(tag)) fit.name = `${fit.name}${tag}`;
  toast(`${tr("スキルが足りない {0} 種類を{1}に替えました。「元に戻す」で戻せます。", modules.length + bay.length, mode === "meta" ? tr("メタ装備") : " T1 ")}`, "ok");
  changed();
}

$("#fb-t1").addEventListener("click", () => swapLacking("t1"));
$("#fb-meta").addEventListener("click", () => swapLacking("meta"));
$("#fb-undo").addEventListener("click", () => {
  if (!undoStack.length) return;
  fit = undoStack.pop();
  $("#fb-undo").hidden = !undoStack.length;
  changed();
});

$("#fb-fit").addEventListener("click", (ev) => {
  const rm = ev.target.closest("[data-remove]");
  if (rm) {
    fit.modules.splice(Number(rm.dataset.remove), 1);
    changed();
    return;
  }
  const rb = ev.target.closest("[data-remove-bay]");
  if (rb) {
    const [kind, id] = rb.dataset.removeBay.split(":");
    const list = kind === "drone" ? fit.drones : fit.cargo;
    list.splice(list.findIndex(([t]) => t === Number(id)), 1);
    changed();
  }
});

$("#fb-fit").addEventListener("change", (ev) => {
  const vm = ev.target.closest("[data-variant-module]");
  if (vm) {
    pushUndo();
    fit.modules[Number(vm.dataset.variantModule)] = Number(vm.value);
    changed();
    return;
  }
  const vb = ev.target.closest("[data-variant-bay]");
  if (vb) {
    const [kind, from] = vb.dataset.variantBay.split(":");
    pushUndo();
    swapBay(kind === "drone" ? fit.drones : fit.cargo, Number(from), Number(vb.value));
    changed();
    return;
  }
  const q = ev.target.closest("[data-qty]");
  if (!q) return;
  const [kind, id] = q.dataset.qty.split(":");
  const row = (kind === "drone" ? fit.drones : fit.cargo).find(([t]) => t === Number(id));
  if (row) row[1] = Math.max(1, Number(q.value) || 1);
  changed();
});

$("#fb-name").addEventListener("input", () => { fit.name = $("#fb-name").value; changed(); });
$("#fb-char").addEventListener("change", () => { saveJson(FB_CHAR_KEY, Number($("#fb-char").value)); evaluate(); });

$("#fb-copy").addEventListener("click", async () => {
  if (!result) { toast(tr("艦を選んでください。"), "error"); return; }
  await navigator.clipboard.writeText(result.eft);
  toast(tr("EFT をコピーしました。ゲームのフィッティング画面で「クリップボードからインポート」してください。"), "ok");
});

$("#fb-save").addEventListener("click", async () => {
  if (!result) { toast(tr("艦を選んでください。"), "error"); return; }
  try {
    await request("POST", "/api/saved-fits", { eft: result.eft, name: fit.name || result.name });
    toast(tr("保存しました。スキルチェッカー・おすすめフィットの「保存したフィット」に出ます。"), "ok");
  } catch (e) {
    toast(e.message, "error");
  }
});

$("#fb-plan").addEventListener("click", () => {
  if (!result) { toast(tr("艦を選んでください。"), "error"); return; }
  openPlanDialog({ types: result.type_ids, skills: result.plan_skills, charId: Number($("#fb-char").value), title: result.name });
});

$("#fb-clear").addEventListener("click", () => {
  if (!confirm(tr("フィットを空にしますか？"))) return;
  undoStack = [];
  $("#fb-undo").hidden = true;
  fit = { ship: null, name: "", modules: [], drones: [], cargo: [] };
  result = null;
  saveDraft();
  $("#fb-name").value = "";
  renderEmpty();
});

async function importEft(text) {
  try {
    const d = await request("POST", "/api/fitbuilder/import", { eft: text });
    fit = { ship: { type_id: d.ship_type_id, ja: "" }, name: d.name, modules: d.modules, drones: d.drones, cargo: d.cargo };
    if (d.unresolved.length) toast(`${tr("見つからない名前があります: {0}", d.unresolved.join(LIST_SEP))}`, "error");
    changed();
  } catch (e) {
    toast(e.message, "error");
  }
}

$("#fb-import").addEventListener("click", () => importEft($("#fb-eft").value));

(async () => {
  try {
    const d = await request("GET", "/api/characters");
    characters = d.characters.filter((c) => !c.missing);
    const saved = loadJson(FB_CHAR_KEY, null) ?? loadJson(REC_CHAR_KEY, null);
    $("#fb-char").innerHTML = characters.map((c) => `<option value="${c.character_id}" ${c.character_id === saved ? "selected" : ""}>${esc(c.character_name)}</option>`).join("")
      + `<option value="">${tr("全スキル V")}</option>`;
  } catch (e) {
    toast(e.message, "error");
  }
  const incoming = loadJson(IMPORT_KEY, null);
  const wantT1 = loadJson(T1_FLAG_KEY, false);
  if (incoming) {
    try { localStorage.removeItem(IMPORT_KEY); localStorage.removeItem(T1_FLAG_KEY); } catch { /* 無視 */ }
    await importEft(incoming);
    if (wantT1) {  // 「スキル不足を T1 で試す」から開いたとき
      clearTimeout(evalTimer);
      await evaluate();
      swapLacking(wantT1 === "meta" ? "meta" : "t1");
    }
  } else {
    evaluate();
  }
})();
