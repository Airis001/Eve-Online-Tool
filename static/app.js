"use strict";

// 共通の関数（esc・fmt*・request・toast・$ など）は common.js にある
const STALE_MINUTES = 30; // これより古いデータは、ページを開いたときに自動で更新する

let state = { characters: [], targets: [], category_order: [], catalog: {} };
let selectedChar = null;
let previewTypeId = null;
let searchTimer = null;
let searchSeq = 0;
let activeIndex = -1;

// ---------- ブースト（属性値の加算） ----------
// サーバーへのリクエストに ?boost=知覚,記憶,意志,知性,魅力 を付け、訓練時間をブースト後の属性値で計算させる
const ATTRS = [["perception", tr("知覚")], ["memory", tr("記憶")], ["willpower", tr("意志")], ["intelligence", tr("知性")], ["charisma", tr("魅力")]];
const BOOST_KEY = "skill-checker:boost";
const MAX_BOOST = 50;

function loadBoost() {
  try {
    const saved = JSON.parse(localStorage.getItem(BOOST_KEY)) || {};
    return Object.fromEntries(ATTRS.map(([k]) => [k, Math.max(0, Math.min(MAX_BOOST, Number(saved[k]) || 0))]));
  } catch {
    return Object.fromEntries(ATTRS.map(([k]) => [k, 0]));
  }
}

let boost = loadBoost();
const boostActive = () => ATTRS.some(([k]) => boost[k] > 0);

function withBoost(url) {
  if (!boostActive()) return url;
  return `${url}${url.includes("?") ? "&" : "?"}boost=${ATTRS.map(([k]) => boost[k]).join(",")}`;
}

function boostLabel(b = boost) {
  return ATTRS.filter(([k]) => b[k] > 0).map(([k, jp]) => `${jp}+${b[k]}`).join(" ");
}

// ---------- マーケット（価格） ----------
// 価格を出したい所には data-price="type_id"（単価）や data-price-total="type_id:個数,..."（合計）を置いておき、
// 見えている（閉じた <details> の中でない）ものだけをまとめて取得して埋める。
let marketLoc = loadMarketLocation();
const priceCache = new Map(); // "場所:type_id" → {sell, buy}
const marketShort = () => marketLoc.short || marketLoc.name;

async function fetchPrices(typeIds) {
  const missing = [...new Set(typeIds)].filter((t) => !priceCache.has(`${marketLoc.id}:${t}`));
  for (let i = 0; i < missing.length; i += 100) {
    const chunk = missing.slice(i, i + 100);
    const data = await api("GET", `/api/market/prices?location=${marketLoc.id}&name=${encodeURIComponent(marketLoc.name)}&type_ids=${chunk.join(",")}`);
    for (const [t, p] of Object.entries(data.prices)) priceCache.set(`${marketLoc.id}:${t}`, p);
  }
}

const priceOf = (typeId) => priceCache.get(`${marketLoc.id}:${typeId}`);
const parseItems = (text) => text.split(",").filter(Boolean).map((p) => p.split(":").map(Number));

function visiblePriceElements(root) {
  return [...root.querySelectorAll("[data-price],[data-price-total],[data-buyorder-total],.trader-note")].filter((el) => !el.closest("details:not([open])"));
}

let hydrating = Promise.resolve();

async function hydratePrices(root = document) {
  const els = visiblePriceElements(root);
  if (!els.length) return;
  const itemsOf = (el) => (el.dataset.price ? [Number(el.dataset.price)]
    : parseItems(el.dataset.priceTotal || el.dataset.buyorderTotal || "").map(([t]) => t));
  const typeIds = els.flatMap(itemsOf);
  els.forEach((el) => { if (!priceOf(el.dataset.price) && el.dataset.price) el.textContent = "…"; });
  hydrating = hydrating.then(() => fetchPrices(typeIds)).catch((e) => {
    els.forEach((el) => { el.textContent = tr("取得できません"); el.title = e.message; });
    throw e;
  });
  try { await hydrating; } catch (e) { toast(e.message, "error"); hydrating = Promise.resolve(); return; }

  const trader = els.some((el) => el.dataset.buyorderTotal != null || el.classList.contains("trader-note"))
    ? await bestTrader(marketLoc.id) : null;
  for (const el of els) {
    if (el.classList.contains("trader-note")) {
      el.innerHTML = trader ? `${tr("（{0}）", traderLabel(trader))}` : tr("（キャラクターのデータがありません）");
      continue;
    }
    if (el.dataset.buyorderTotal != null) {
      // 買い注文を出して買う場合: 最高の買い値 ×（1 + 仲介手数料）
      let total = 0;
      const missing = [];
      for (const [t, qty] of parseItems(el.dataset.buyorderTotal)) {
        const buy = priceOf(t)?.buy;
        if (buy && trader) total += buy.price * (1 + trader.broker / 100) * qty; else missing.push(t);
      }
      el.textContent = trader ? `${fmtIsk(total)} ISK${missing.length ? `${tr("（買い注文なし {0} 品目を除く）", missing.length)}` : ""}` : "-";
      el.title = trader ? `${tr("{0}（{1} が買い注文を出して買う場合。約定するまで時間がかかります）", fullIsk(total), trader.name)}` : "";
      el.classList.toggle("no-stock", missing.length > 0);
      continue;
    }
    if (el.dataset.price) {
      const sell = priceOf(el.dataset.price)?.sell;
      el.textContent = sell ? `${fmtIsk(sell.price)} ISK` : tr("在庫なし");
      el.title = sell ? `${tr("{0} の最安値 {1}（この価格で {2} 個）", marketShort(), fullIsk(sell.price), fmtNum(sell.volume))}` : `${tr("{0} に売り注文がありません", marketShort())}`;
      el.classList.toggle("no-stock", !sell);
    } else {
      let total = 0;
      const missing = [];
      for (const [t, qty] of parseItems(el.dataset.priceTotal)) {
        const sell = priceOf(t)?.sell;
        if (sell) total += sell.price * qty; else missing.push(t);
      }
      el.textContent = `${fmtIsk(total)} ISK${missing.length ? `${tr("（在庫なし {0} 品目を除く）", missing.length)}` : ""}`;
      el.title = fullIsk(total);
      el.classList.toggle("no-stock", missing.length > 0);
    }
  }
}

// <details> を開いたら、中の価格を取得する
document.addEventListener("toggle", (ev) => { if (ev.target.open) hydratePrices(ev.target); }, true);

async function setMarketLocation(loc) {
  marketLoc = loc;
  saveMarketLocation(loc);
  document.querySelectorAll(".market-name").forEach((el) => { el.textContent = marketShort(); });
  await hydratePrices();
}

const BOOST_PRESETS = [0, 1, 2, 3, 4, 5, 6, 8, 10, 12];

function openBoostDialog() {
  const body = $("#boost-body");
  const inputs = ATTRS.map(([k, jp]) => `<label class="boost-field"><span>${jp}</span>
    <span class="boost-input">+<input type="number" min="0" max="${MAX_BOOST}" step="1" data-attr="${k}" value="${boost[k]}"></span></label>`).join("");
  const presets = BOOST_PRESETS.map((v) =>
    `<button class="fchip" type="button" data-action="boost-preset" data-value="${v}">${v ? `${tr("すべて +{0}", v)}` : tr("すべて 0")}</button>`).join("");
  body.innerHTML = `
    <div class="plan-head"><div><h3>${tr("🧠 ブースト")}</h3>
      <span class="muted">${tr("各属性に足す値を入力すると、訓練時間をブースト後の属性値で計算し直します。")}</span></div>
      <button class="icon-btn" type="button" title="${tr("閉じる")}" data-action="close-boost">×</button></div>
    <div class="boost-fields">${inputs}</div>
    <div class="fchips boost-presets">${presets}</div>
    <div id="boost-preview"></div>
    <div class="plan-actions">
      <button class="btn primary" type="button" data-action="boost-apply">${tr("適用する")}</button>
      <button class="btn" type="button" data-action="boost-clear">${tr("ブーストを解除")}</button>
      <small>${tr("ブースターやインプラントの効果を試算するためのもので、ゲーム内の状態は変わりません。")}</small>
    </div>`;
  renderBoostPreview();
  $("#boost-dialog").showModal();
}

function boostInputs() {
  return Object.fromEntries([...document.querySelectorAll("#boost-body input[data-attr]")]
    .map((i) => [i.dataset.attr, Math.max(0, Math.min(MAX_BOOST, Math.floor(Number(i.value) || 0)))]));
}

// 表示中のキャラクターごとに「今の値 → ブースト後」を一覧にする
function renderBoostPreview() {
  const draft = boostInputs();
  const chars = readyChars().filter((c) => c.base_attributes || c.attributes);
  if (!chars.length) { $("#boost-preview").innerHTML = ""; return; }
  const head = ATTRS.map(([, jp]) => `<th class="r">${jp}</th>`).join("");
  const rows = chars.map((c) => {
    const base = c.base_attributes || c.attributes; // 適用中はサーバーが元の値を base_attributes に入れている
    return `<tr><td>${esc(c.character_name)}</td>${ATTRS.map(([k]) => {
      const v = base[k] ?? 0;
      return `<td class="r num">${draft[k] ? `${v} → <b>${v + draft[k]}</b>` : v}</td>`;
    }).join("")}</tr>`;
  }).join("");
  $("#boost-preview").innerHTML = `<div class="table-scroll boost-table"><table class="plan"><thead><tr><th>${tr("キャラクター")}</th>${head}</tr></thead>
    <tbody>${rows}</tbody></table></div>`;
}

async function setBoost(next) {
  boost = next;
  try { localStorage.setItem(BOOST_KEY, JSON.stringify(boost)); } catch { /* 保存できなくても今回は適用する */ }
  await reloadAll();
  toast(boostActive() ? `${tr("ブースト（{0}）で計算し直しました。", boostLabel())}` : tr("ブーストを解除しました。"), "ok");
}

// ブースト付きでサーバーに問い合わせる
const api = (method, url, body) => request(method, withBoost(url), body);

// ---------- 表示するキャラクターの絞り込み ----------
// filter: { mode: "all" } | { mode: "group", id } | { mode: "custom", ids: [...] }
const FILTER_KEY = "skill-checker:filter";

function loadFilter() {
  try {
    return JSON.parse(localStorage.getItem(FILTER_KEY)) || { mode: "all" };
  } catch {
    return { mode: "all" };
  }
}

function saveFilter() {
  try { localStorage.setItem(FILTER_KEY, JSON.stringify(filter)); } catch { /* 保存できなくても動作は続ける */ }
}

let filter = loadFilter();

function activeGroup() {
  return filter.mode === "group" ? (state.groups || []).find((g) => g.id === filter.id) : null;
}

function visibleIds() {
  const all = state.characters.map((c) => c.character_id);
  if (filter.mode === "group") {
    const group = activeGroup();
    return new Set(group ? group.character_ids : all); // 削除済みグループなら全員
  }
  if (filter.mode === "custom") return new Set(filter.ids);
  return new Set(all);
}

function visibleChars() {
  const ids = visibleIds();
  return state.characters.filter((c) => ids.has(c.character_id));
}

function readyChars() {
  return visibleChars().filter((c) => !c.missing);
}

function setFilter(next) {
  filter = next;
  saveFilter();
  renderAll();
}

function renderFilterBar() {
  const bar = $("#filter-bar");
  if (state.characters.length < 2) { bar.hidden = true; return; }
  bar.hidden = false;
  const ids = visibleIds();
  const groups = state.groups || [];
  const group = activeGroup();
  const chip = (label, action, pressed, id = "") =>
    `<button class="fchip" type="button" data-action="${action}" data-id="${esc(id)}" aria-pressed="${pressed}">${label}</button>`;

  const groupChips = [chip(tr("すべて"), "filter-all", filter.mode === "all")]
    .concat(groups.map((g) => chip(`${esc(g.name)} <small>${g.character_ids.filter((i) => state.characters.some((c) => c.character_id === i)).length}</small>`,
      "filter-group", group?.id === g.id, g.id)));
  const charChecks = state.characters.map((c) =>
    `<label class="fcheck"><input type="checkbox" data-action="filter-toggle" data-id="${c.character_id}" ${ids.has(c.character_id) ? "checked" : ""}>${esc(c.character_name)}</label>`).join("");

  let tools = `<button class="link" type="button" data-action="group-new">${tr("＋ 今の選択をグループとして保存")}</button>`;
  if (group) {
    tools = `<button class="link" type="button" data-action="group-rename">${tr("名前を変更")}</button>
      <button class="link" type="button" data-action="group-delete">${tr("「{0}」を削除", esc(group.name))}</button>` + tools;
  }
  bar.innerHTML = `<div class="filter-row"><span class="filter-label">${tr("表示")}</span><div class="fchips">${groupChips.join("")}</div></div>
    <div class="filter-row"><span class="filter-label">${tr("キャラクター")}</span><div class="fchecks">${charChecks}</div></div>
    <div class="filter-tools">${tools}</div>`;
}

async function saveGroup(body) {
  const group = await api("POST", "/api/groups", body);
  const others = (state.groups || []).filter((g) => g.id !== group.id);
  state.groups = [...others, group];
  return group;
}

// ---------- 判定結果の表示 ----------

function badge(result) {
  if (result.status === "ok") return `<span class="badge ok">${tr("✓ 使用可")}</span>`;
  if (result.status === "queued") return `<span class="badge queued">⏳ ${esc(fmtLocal(result.ready_at))}</span>`;
  return `<span class="badge missing">${tr("✗ あと {0}", esc(fmtMinutes(result.total_minutes)))}</span>`;
}

const SELF_TRAIN_LIMIT_MINUTES = 24 * 60; // 「自力で訓練」とみなす訓練時間の上限（1 日未満）

const SELF_TRAIN_MAX_LEVEL = 3; // 行全体が 1 日以上でも、このレベルまでの 1 日未満のレベルは自力で訓練する

const isShort = (minutes) => minutes != null && minutes < SELF_TRAIN_LIMIT_MINUTES;
const sumSp = (list) => list.reduce((s, m) => s + (m.sp_needed || 0), 0);

// 不足スキル 1 行を「自力で訓練するレベル」と「残りのレベル」に分ける
//  - 行全体（今のレベル → 必要レベル）が 1 日未満なら全レベル自力
//  - そうでなくても、レベル I〜III のうち 1 レベルあたり 1 日未満のものは自力
function splitSelfTrain(m) {
  const levels = m.levels || [];
  if (isShort(m.minutes)) return { self: levels, rest: [] };
  const selfLevel = (l) => l.level <= SELF_TRAIN_MAX_LEVEL && isShort(l.minutes);
  return { self: levels.filter(selfLevel), rest: levels.filter((l) => !selfLevel(l)) };
}

const levelSp = (levels) => levels.reduce((s, l) => s + l.sp, 0);
const levelMinutes = (levels) => levels.reduce((s, l) => s + (l.minutes || 0), 0);

function levelRange(levels) {
  if (!levels.length) return "";
  const first = ROMAN[levels[0].level];
  const last = ROMAN[levels[levels.length - 1].level];
  return first === last ? first : `${first}〜${last}`;
}

// 1 日未満のスキル（とレベル I〜III）を自力で訓練した場合の集計（ボタンで表示を切り替える）
function selfTrainSummary(result) {
  const parts = result.missing.map(splitSelfTrain);
  const self = parts.flatMap((p) => p.self);
  const rest = parts.flatMap((p) => p.rest);
  const selfSkills = parts.filter((p) => p.self.length).length;
  const restSkills = parts.filter((p) => p.rest.length).length;
  const body = self.length
    ? `<div>${tr("自力で訓練（{0} スキル）: <b class=\"num\">{1} SP</b> · {2}", selfSkills, fmtNum(levelSp(self)), esc(fmtMinutes(levelMinutes(self))))}</div>
       <div class="muted">${tr("残り（{0} スキル）:", restSkills)} <span class="num">${fmtNum(levelSp(rest))} SP</span>${rest.length ? ` · ${esc(fmtMinutes(levelMinutes(rest)))}` : ""}</div>
       ${rest.length ? injectorBlock(levelSp(rest), result, tr("残りをインジェクターで補うなら")) : ""}
       <div class="muted small-note">${tr("1 日未満のスキルと、1 日以上かかるスキルのうち 1 レベルあたり 1 日未満のレベル I〜III を自力で訓練する計算です。")}</div>`
    : `<div class="muted">${tr("自力で訓練できる（1 日未満の）スキル・レベルはありません。")}</div>`;
  return `<div class="self-train">
    <button class="btn small" type="button" data-action="self-train" aria-pressed="false">${tr("⏱ 1日未満（I〜III 含む）を自力で訓練")}</button>
    <div class="self-summary" hidden>${body}</div></div>`;
}

function missingList(result) {
  const rows = result.missing.map((m) => {
    let note = m.queued ? `<span class="q">${tr("キュー済")}</span> ` : "";
    if (!m.injected) note += `<span class="muted">${tr("未注入")}</span> <span class="book-price" data-price="${m.skill_id}"></span> `;
    const { self, rest } = splitSelfTrain(m);
    const cls = !self.length ? "" : rest.length ? "partial" : "short";
    // 一部のレベルだけ自力の場合、自力表示のときにその内訳を出す
    const partNote = cls === "partial"
      ? `<div class="self-note">${tr("{0} を自力: {1} SP · {2}", levelRange(self), fmtNum(levelSp(self)), esc(fmtMinutes(levelMinutes(self))))}<br>${tr("残り {0}: {1} SP", levelRange(rest), fmtNum(levelSp(rest)))}</div>` : "";
    return `<tr class="${cls}"><td>${esc(m.name)}${partNote}</td><td class="lv">${note}${ROMAN[m.have]} → ${ROMAN[m.need]}</td>
      <td class="r num">${fmtNum(m.sp_needed)}</td><td class="r">${esc(fmtMinutes(m.minutes))}</td></tr>`;
  }).join("");
  return `<div class="req-wrap"><table class="req"><thead><tr><th>${tr("スキル")}</th><th>${tr("レベル")}</th><th class="r">${tr("必要 SP")}</th><th class="r">${tr("訓練時間")}</th></tr></thead>
    <tbody>${rows}</tbody>
    <tfoot><tr><td colspan="2">${tr("合計")}</td><td class="r num">${fmtNum(sumSp(result.missing))}</td><td class="r">${esc(fmtMinutes(result.total_minutes))}</td></tr>
    <tr class="unallocated"><td colspan="2">${tr("未割り当て SP")}</td><td class="r num">${fmtNum(result.unallocated_sp || 0)}</td><td></td></tr></tfoot></table>
    ${injectorBlock(sumSp(result.missing), result, tr("⚡ すぐ使えるようにするには"))}${bookCost(result)}${selfTrainSummary(result)}</div>`;
}

// ---------- 大型スキルインジェクター ----------
const LARGE_INJECTOR_TYPE_ID = 40520;

// 大型スキルインジェクター 1 個で得られる SP（使うキャラクターの総 SP で決まる）
function injectorYield(totalSp) {
  if (totalSp < 5_000_000) return 500_000;
  if (totalSp < 50_000_000) return 400_000;
  if (totalSp < 80_000_000) return 300_000;
  return 150_000;
}

// needSp を得るのに必要な個数。使うたびに総 SP が増えるので 1 個ずつ区分を判定し直す
function injectorsNeeded(needSp, totalSp) {
  let count = 0;
  let gained = 0;
  while (gained < needSp) {
    gained += injectorYield(totalSp + gained);
    count++;
  }
  return { count, gained };
}

// 未割り当て SP と、足りない分を大型スキルインジェクターで補う場合の個数・購入費
function injectorBlock(needSp, result, label) {
  const unallocated = result.unallocated_sp || 0;
  const rest = Math.max(needSp - unallocated, 0);
  const totalSp = (result.character_sp || 0) + unallocated;
  if (!rest) {
    return `<div class="injector ok">${tr("{0}: 未割り当て SP {1} で足ります（インジェクター不要）", label, fmtNum(unallocated))}</div>`;
  }
  const { count } = injectorsNeeded(rest, totalSp);
  return `<div class="injector">${tr("{0}: 大型スキルインジェクター <b>{1} 個</b>", label, count)}
    <span class="muted">${tr("（{0} SP 分・1 個 {1} SP）", fmtNum(rest), fmtNum(injectorYield(totalSp)))}</span>
    · <span class="market-name">${esc(marketShort())}</span>: <span data-price-total="${LARGE_INJECTOR_TYPE_ID}:${count}"></span></div>`;
}

// 未注入のスキルブックの購入費（マーケットの場所の最安値）
function bookCost(result) {
  const books = result.missing.filter((m) => !m.injected);
  if (!books.length) return "";
  return `<div class="book-cost">${tr("📖 未注入のスキルブック {0} 冊（", books.length)}<span class="market-name">${esc(marketShort())}</span>${tr("）: <b data-price-total=\"{0}\"></b>", books.map((m) => `${m.skill_id}:1`).join(","))}</div>`;
}

// plan: { types: [type_id...], char: character_id, title } を渡すと「スキルプラン」ボタンを付ける
// plan.skills: [[skill_id, level], ...] を渡すと、そのスキルをそのレベルまで上げる手順も含める
function planButton(plan, label = tr("📋 スキルプラン")) {
  if (!plan) return "";
  const skills = (plan.skills || []).map(([s, lv]) => `${s}:${lv}`).join(",");
  return `<div class="plan-link"><button class="btn small" type="button" data-action="plan"
    data-types="${(plan.types || []).join(",")}" data-skills="${skills}" data-char="${plan.char}" data-title="${esc(plan.title)}">${label}</button></div>`;
}

const parseIds = (text) => (text ? text.split(",").map(Number) : []);
const parseSkills = (text) => (text ? text.split(",").map((p) => p.split(":").map(Number)) : []);

function blockerList(result) {
  if (!result.blockers?.length) return "";
  return `<div class="sub-label">${tr("使えないアイテム")}</div><ul class="blockers">${result.blockers.map((b) =>
    `<li><span>${esc(nm(b))}</span><span class="lv">${b.status === "queued" ? `<span class="q">${tr("キュー済")}</span>` : esc(fmtMinutes(b.total_minutes))}</span></li>`).join("")}</ul>
    <div class="sub-label">${tr("不足スキル")}</div>`;
}

function resultCell(result, open = false, plan = null) {
  if (!result) return `<span class="muted">-</span>`;
  if (result.status === "ok") return badge(result);
  return `<details class="cell"${open ? " open" : ""}><summary>${badge(result)}</summary>${blockerList(result)}${missingList(result)}${planButton(plan)}</details>`;
}

// ---------- 全体 ----------

function renderSummary() {
  const chars = readyChars();
  const total = chars.reduce((s, c) => s + (c.total_sp || 0), 0);
  const shown = visibleChars().length;
  const count = shown === state.characters.length
    ? `${tr("{0} キャラクター", shown)}` : `${tr("{0} / {1} キャラクターを表示中", shown, state.characters.length)}`;
  $("#summary").textContent = state.characters.length
    ? `${tr("{0} · 合計 {1} SP", count, fmtNum(total))}`
    : tr("キャラクターが登録されていません。「＋ キャラクター追加」から EVE にログインしてください。");
}

function renderCatalogBanner() {
  const cat = state.catalog || {};
  const el = $("#catalog-banner");
  if (cat.status === "building") {
    const pct = cat.total ? Math.floor((cat.done / cat.total) * 100) : 0;
    el.className = "banner";
    el.innerHTML = `${tr("アイテムの名前一覧を作成しています… {0} / {1}", fmtNum(cat.done), fmtNum(cat.total || 0))}
      <div class="progress"><span style="width:${pct}%"></span></div>`;
    el.hidden = false;
  } else if (cat.status === "error") {
    el.className = "banner error";
    el.innerHTML = `${tr("名前一覧の作成に失敗しました: {0}", esc(cat.error))} <button class="link" type="button" data-action="rebuild">${tr("再試行")}</button>`;
    el.hidden = false;
  } else {
    el.hidden = true;
  }
}

function renderChecklist() {
  const box = $("#checklist");
  const chars = readyChars();
  if (state.characters.length && !chars.length) {
    box.innerHTML = `<div class="card empty-card">${tr("表示するキャラクターが選ばれていません。上の「表示」で選んでください。")}</div>`;
    return;
  }
  if (!state.targets.length) {
    box.innerHTML = `<div class="card empty-card">${tr("上の検索で艦・装備を選び、「チェックリストに追加」するとここに表示されます。")}</div>`;
    return;
  }
  const cats = [...new Set(state.targets.map((t) => t.category))]; // リストに登場した順

  let html = `<div class="table-scroll"><table class="matrix"><thead><tr><th>${tr("艦・装備")}</th>`;
  html += chars.map((c) => `<th>${esc(c.character_name)}</th>`).join("");
  html += `<th class="rm"></th></tr></thead><tbody>`;
  for (const cat of cats) {
    html += `<tr class="cat"><td colspan="${chars.length + 2}">${esc(cat)}</td></tr>`;
    for (const t of state.targets.filter((x) => x.category === cat)) {
      const sub = t.en && t.en !== t.label ? `<small>${nmSub(t)}</small>` : "";
      html += `<tr><td class="item">${esc(t.label)}${sub}</td>`;
      html += chars.map((c) => `<td>${resultCell(t.checks[c.character_id], false,
        { types: [t.type_id], char: c.character_id, title: t.label })}</td>`).join("");
      html += `<td class="rm"><button class="icon-btn" type="button" title="${tr("リストから外す")}" data-action="remove-target" data-id="${t.type_id}">×</button></td></tr>`;
    }
  }
  box.innerHTML = html + `</tbody></table></div>`;
}

// ---------- キャラクター ----------

function renderCharacters() {
  const tabs = $("#char-tabs");
  const panel = $("#char-panel");
  if (!state.characters.length) {
    tabs.innerHTML = "";
    panel.innerHTML = `<div class="card empty-card">${tr("キャラクターがいません。<a href=\"/login\">キャラクターを追加</a>してください。")}</div>`;
    return;
  }
  const chars = visibleChars();
  if (!chars.length) {
    tabs.innerHTML = "";
    panel.innerHTML = `<div class="card empty-card">${tr("表示するキャラクターが選ばれていません。")}</div>`;
    return;
  }
  if (!chars.some((c) => c.character_id === selectedChar)) {
    selectedChar = chars[0].character_id;
  }
  tabs.innerHTML = chars.map((c) =>
    `<button class="tab" role="tab" type="button" data-action="select-char" data-id="${c.character_id}"
      aria-selected="${c.character_id === selectedChar}">${esc(c.character_name)}</button>`).join("");
  panel.innerHTML = characterPanel(chars.find((c) => c.character_id === selectedChar));
}

function characterPanel(c) {
  const head = `<div class="char-head"><span class="muted">${c.missing ? tr("まだデータを取得していません") : `${tr("取得日時: {0}", esc(fmtLocal(c.fetched_at)))}`}</span>
    <span class="actions">
      <button class="btn small" type="button" data-action="refresh-one" data-id="${c.character_id}">${tr("↻ 更新")}</button>
      <button class="btn small danger" type="button" data-action="remove-char" data-id="${c.character_id}" data-name="${esc(c.character_name)}">${tr("削除")}</button>
    </span></div>`;
  if (c.missing) return head;

  const skills = c.skills || [];
  const queue = c.skill_queue || [];
  const lv5 = skills.filter((s) => s.trained_level === 5).length;
  const queueEnd = queue.length ? fmtLocal(queue[queue.length - 1].finish_date) : tr("空");
  const stats = [[tr("総 SP"), fmtNum(c.total_sp)], [tr("未割り当て SP"), fmtNum(c.unallocated_sp)],
    [tr("習得スキル"), skills.length], ["Lv V", lv5], [tr("キュー完了"), queueEnd]];

  const groupSp = {};
  for (const s of skills) groupSp[s.group] = (groupSp[s.group] || 0) + s.skillpoints;
  const groups = Object.entries(groupSp).sort((a, b) => b[1] - a[1]);
  const top = Math.max(1, ...groups.map((g) => g[1]));
  const bars = groups.map(([g, sp]) =>
    `<span class="name" title="${esc(g)}">${esc(g)}</span><span class="track"><span class="fill" style="width:${(sp / top * 100).toFixed(1)}%"></span></span><span class="num">${fmtNum(sp)}</span>`).join("");

  const a = c.attributes;
  const attrs = a ? `<div class="attrs">${ATTRS.map(([k, jp]) => {
    const plus = c.boost?.[k] ? ` <span class="boosted">(+${c.boost[k]})</span>` : "";
    return `<span>${jp} <b>${a[k] ?? "-"}</b>${plus}</span>`;
  }).join("")}</div>` : "";

  const queueSp = queue.map((q) => queueRemainingSp(q));
  const queueSpTotal = queueSp.reduce((a, v) => a + (v || 0), 0);
  const queueHtml = queue.length
    ? queue.map((q, i) => `<li><span>${esc(q.name)} ${ROMAN[q.finished_level]}</span>
        <span class="q-right"><span class="num">${queueSp[i] != null ? `${fmtNum(queueSp[i])} SP` : "-"}</span><span class="muted num">${esc(fmtLocal(q.finish_date))}</span></span></li>`).join("")
    : `<li class="muted">${tr("（空）")}</li>`;
  const queueSummary = queue.length
    ? `<div class="queue-sp">${tr("残り合計 <b>{0}</b> SP", fmtNum(queueSpTotal))}</div>${spCostBox(c.character_id, queueSpTotal)}` : "";

  const rows = skills.map((s) => `<tr><td>${esc(s.name)}</td><td class="muted">${esc(s.group)}</td>
    <td><span class="pips">${[0, 1, 2, 3, 4].map((i) => `<i class="${i < s.trained_level ? "on" : ""}"></i>`).join("")}</span></td>
    <td class="r num">${fmtNum(s.skillpoints)}</td></tr>`).join("");

  return head
    + (queue.length ? "" : `<div class="warn">${tr("スキルキューが空です。スキルを訓練していません。")}</div>`)
    + `<div class="stats">${stats.map(([l, v]) => `<div class="stat"><div class="label">${l}</div><div class="value num">${esc(v)}</div></div>`).join("")}</div>`
    + `<div class="cols" style="margin-bottom:12px">${statusCard(c)}${shipsCard(c)}</div>`
    + `<div class="cols"><div class="card"><h3>${tr("グループ別 SP")}</h3><div class="bars">${bars}</div>${attrs}</div>`
    + `<div class="card"><h3>${tr("スキルキュー（完了予定）")}</h3>${queueSummary}<ol class="queue">${queueHtml}</ol></div></div>`
    + `<details class="all card"><summary>${tr("全スキル一覧（{0}）", skills.length)}</summary>
       <input class="skill-search" type="search" placeholder="${tr("スキル名・グループで絞り込み")}">
       <div class="table-scroll" style="border:0"><table class="skills"><thead><tr><th>${tr("スキル")}</th><th>${tr("グループ")}</th><th>${tr("レベル")}</th><th class="r">SP</th></tr></thead>
       <tbody>${rows}</tbody></table></div></details>`;
}

const RELOGIN_NOTE = `<span class="muted">${tr("この情報を表示するには <a href=\"/login\">再ログイン</a> が必要です。")}</span>`;

function statusCard(c) {
  const ship = c.current_ship
    ? `<div class="now">${tr("搭乗中: <b>{0}</b>{1}", esc(nm(c.current_ship)), c.current_ship.name ? ` <span class="muted">「${esc(c.current_ship.name)}」</span>` : "")}</div>`
    : `<div class="now">${tr("搭乗中: {0}", c.missing_scopes?.includes("esi-location.read_ship_type.v1") ? RELOGIN_NOTE : "-")}</div>`;
  let implants;
  if (c.implants == null) implants = RELOGIN_NOTE;
  else if (!c.implants.length) implants = `<span class="muted">${tr("なし")}</span>`;
  else implants = `<div class="chips">${c.implants.map((i) => `<span class="chip" title="${esc(i.en)}">${esc(nm(i))}</span>`).join("")}</div>`;
  return `<div class="card"><h3>${tr("現在の状態")}</h3>${ship}<div class="sub-label">${tr("インプラント")}</div>${implants}</div>`;
}

function shipsCard(c) {
  let body;
  if (c.ships_pending) body = `<span class="muted">${tr("艦・装備の名前一覧の作成後に表示されます。")}</span>`;
  else if (c.ships == null) body = RELOGIN_NOTE;
  else if (!c.ships.length) body = `<span class="muted">${tr("ハンガーに艦がありません。")}</span>`;
  else {
    const flyable = c.ships.filter((s) => s.status === "ok").length;
    body = `<div class="sub-label" style="margin-top:0">${tr("{0} 隻中 {1} 隻に搭乗可能", c.ships.length, flyable)}</div>
      <ul class="ship-list">${c.ships.map((s) => `<li><span><span title="${esc(s.en)}">${esc(nm(s))}</span>
        <span class="where">${esc(s.location)}</span></span>${badge(s)}</li>`).join("")}</ul>`;
  }
  return `<div class="card"><h3>${tr("所持艦")}</h3>${body}</div>`;
}

// ---------- 警告（キュー切れ・再ログイン） ----------

function renderAlerts() {
  const alerts = [];
  const soon = Date.now() + 24 * 60 * 60 * 1000;
  for (const c of readyChars()) {
    const queue = c.skill_queue || [];
    const end = queue.length ? queue[queue.length - 1].finish_date : null;
    if (!queue.length) {
      alerts.push(`<div class="alert"><span>${tr("⚠ <b>{0}</b> のスキルキューが空です", esc(c.character_name))}</span></div>`);
    } else if (end && new Date(end).getTime() < soon) {
      alerts.push(`<div class="alert"><span>${tr("⚠ <b>{0}</b> のスキルキューが {1} に終わります（24 時間以内）", esc(c.character_name), esc(fmtLocal(end)))}</span></div>`);
    }
  }
  if (boostActive()) {
    alerts.unshift(`<div class="alert boost"><span>${tr("🧠 ブースト適用中（{0}）: 訓練時間はブースト後の属性値で計算しています。", esc(boostLabel()))}</span>
      <span class="actions"><button class="link" type="button" data-action="open-boost">${tr("変更")}</button>
      <button class="link" type="button" data-action="boost-clear">${tr("解除")}</button></span></div>`);
  }
  const relogin = visibleChars().filter((c) => c.missing_scopes?.length);
  if (relogin.length) {
    alerts.push(`<div class="alert info"><span>${tr("フィッティング・所持艦・インプラント・搭乗中の艦を表示するには、 {0} の再ログインが必要です（新しい権限を許可するため）。", relogin.map((c) => `<b>${esc(c.character_name)}</b>`).join(LIST_SEP))}</span>
      <a href="/login">${tr("再ログインする →")}</a></div>`);
  }
  $("#alerts").innerHTML = alerts.join("");
}

// ---------- フィッティング ----------

// コピー・削除ボタンから参照するため、表示中のフィットを key で引けるようにしておく
const fitByKey = new Map();

function fitSource(f) {
  if (f.source === "app") return `<small class="owners">${tr("このアプリに保存")}</small>`;
  if (f.owners) return `<small class="owners">${tr("ゲーム内に保存: {0}", f.owners.map(esc).join(LIST_SEP))}</small>`;
  return "";
}

const BOM_KIND = { ship: tr("艦"), module: tr("モジュール"), bay: tr("ドローン・カーゴ") };

// フィット一式の購入費（マーケットの場所の最安値。開いたときに価格を取得する）
function fitCost(f) {
  if (!f.bom?.length) return "";
  const items = (kinds) => f.bom.filter((b) => kinds.includes(b.kind)).map((b) => `${b.type_id}:${b.qty}`).join(",");
  const hasBay = f.bom.some((b) => b.kind === "bay");
  const rows = f.bom.map((b) => `<tr><td>${esc(nm(b))}</td><td class="muted">${BOM_KIND[b.kind]}</td><td class="r num">${fmtNum(b.qty)}</td>
    <td class="r" data-price="${b.type_id}"></td><td class="r" data-price-total="${b.type_id}:${b.qty}"></td>
    <td class="r muted" data-buyorder-total="${b.type_id}:${b.qty}"></td></tr>`).join("");
  return `<details class="fit-cost"><summary>${tr("💰 購入費（")}<span class="market-name">${esc(marketShort())}</span>${tr("）")}</summary>
    <div class="cost-sum">${tr("艦＋モジュール: <b data-price-total=\"{0}\"></b>", items(["ship", "module"]))}</div>
    ${hasBay ? `<div class="cost-sum muted">${tr("ドローン・カーゴ込み:")} <span data-price-total="${items(["ship", "module", "bay"])}"></span></div>` : ""}
    <div class="cost-sum">${tr("トレードスキルが一番高いキャラクターが買い注文で買う場合: <b data-buyorder-total=\"{0}\"></b> {1} <small class=\"muted trader-note\"></small>", items(["ship", "module"]), (hasBay ? `<span class="muted">${tr("（ドローン・カーゴ込み")} <span data-buyorder-total="${items(["ship", "module", "bay"])}"></span>${tr("）")}</span>` : ""))}</div>
    <p class="muted small-note">${tr("売り注文から即買いするときは手数料がかからないので、誰が買っても同じ金額です。買い注文を出すと安く買えますが、仲介手数料がかかり、約定するまで時間がかかります。")}</p>
    <div class="table-scroll cost-scroll"><table class="cost-table"><thead><tr><th>${tr("品目")}</th><th>${tr("種類")}</th><th class="r">${tr("数")}</th><th class="r">${tr("単価")}</th><th class="r">${tr("小計")}</th><th class="r">${tr("買い注文で買う場合")}</th></tr></thead>
    <tbody>${rows}</tbody></table></div></details>`;
}

function fitActions(f) {
  let html = `<button class="btn small" type="button" data-action="copy-fit" data-key="${esc(f.key)}"
    title="${tr("EFT 形式でコピー（ゲームのフィッティング画面でインポートできます）")}">${tr("📋 コピー")}</button>
    <button class="btn small" type="button" data-action="edit-fit" data-key="${esc(f.key)}" title="${tr("フィットの作成ページで開く")}">${tr("✏️ 編集")}</button>
    <button class="btn small" type="button" data-action="try-t1" data-key="${esc(f.key)}" title="${tr("フィットの作成ページで選んだキャラクターのスキルが足りない装備を T1 に替えて開く")}">${tr("🔽 スキル不足を T1 で試す")}</button>`;
  if (f.source === "app") {
    html += `<button class="btn small danger" type="button" data-action="delete-fit" data-key="${esc(f.key)}">${tr("削除")}</button>`;
  } else if (f.key === "eft") {
    html += `<button class="btn small primary" type="button" data-action="save-fit" data-key="eft">${tr("💾 保存")}</button>`;
  }
  return `<div class="fit-actions">${html}</div>`;
}

const fmtRes = (n) => Number(n || 0).toLocaleString(LOCALE, { maximumFractionDigits: 1 });

const suggestedSkills = (check) => (check?.resources?.suggestion?.skills || []).map((s) => [s.skill_id, s.to]);

// CPU・PG が足りないとき、どのスキルをどのレベルまで上げれば足りるか
function suggestionBlock(r, plan) {
  const notes = [];
  const sg = r.suggestion;
  if (sg?.impossible) {
    notes.push(`<div class="res-suggest ng">${tr("関係するスキルをすべて V にしても CPU / PG が足りません。モジュールの見直しが必要です。")}</div>`);
  } else if (sg?.skills?.length) {
    const list = sg.skills.map((s) => `<li><span>${esc(s.name)}</span><span class="num">${ROMAN[s.from]} → <b>${ROMAN[s.to]}</b></span></li>`).join("");
    notes.push(`<div class="res-suggest"><div>${tr("CPU / PG を足りさせるには（訓練 {0}）:", esc(fmtMinutes(sg.minutes)))}</div>
      <ul>${list}</ul>${plan ? planButton({ ...plan, types: [], skills: sg.skills.map((s) => [s.skill_id, s.to]) }, tr("📋 このスキルのプラン")) : ""}</div>`);
  }
  if (!r.calibration.ok) {
    notes.push(`<div class="res-suggest ng">${tr("キャリブレーションはスキルでは増えません。リグの見直しが必要です。")}</div>`);
  }
  return notes.join("");
}

// PG / CPU / キャリブレーションの「使用量 / 上限」
function resourceBlock(check, plan = null) {
  if (!check) return "";
  if (check.resources_error) return `<div class="res-block"><div class="res-note">${tr("PG / CPU を計算できませんでした: {0}", esc(check.resources_error))}</div></div>`;
  const r = check.resources;
  if (!r) return "";
  const row = (label, x) => `<div class="res ${x.ok ? "ok" : "ng"}"><span class="res-label">${label}</span>
    <span class="num">${fmtRes(x.used)} / ${fmtRes(x.total)}</span><span class="res-mark">${x.ok ? "✓" : tr("✗ 不足")}</span></div>`;
  const approx = r.approximate.length
    ? `<div class="res-note" title="${esc(r.approximate.join(LIST_SEP))}">${tr("※ 参考値（{0}は未反映）", esc(r.approximate.join(LIST_SEP)))}</div>` : "";
  return `<div class="res-block">${row("PG", r.power)}${row("CPU", r.cpu)}${row(tr("キャリブレーション"), r.calibration)}${holdRows(r.holds)}${approx}${suggestionBlock(r, plan)}</div>`;
}

const HOLD_LABELS = [["cargo", tr("カーゴ")], ["mining_hold", tr("採掘カーゴ")], ["drone_bay", tr("ドローンベイ")]];

// 容量（艦・モジュール・リグ・艦のスキルボーナス込み）
function holdRows(holds) {
  if (!holds) return "";
  return HOLD_LABELS.filter(([k]) => holds[k]).map(([k, label]) => {
    const h = holds[k];
    const diff = h.total - h.base;
    const note = Math.abs(diff) >= 0.05 ? ` <span class="hold-diff">(${diff > 0 ? "+" : ""}${fmtRes(diff)})</span>` : "";
    return `<div class="res hold" title="${tr("艦の基本値 {0} m³", fmtRes(h.base))}"><span class="res-label">${label}</span>
      <span class="num">${fmtRes(h.total)} m³${note}</span><span></span></div>`;
  }).join("");
}

function fitMatrix(fits, chars) {
  let html = `<div class="table-scroll"><table class="matrix"><thead><tr><th>${tr("フィット")}</th>`;
  html += chars.map((c) => `<th>${esc(c.character_name)}</th>`).join("") + `</tr></thead><tbody>`;
  for (const f of fits) {
    fitByKey.set(f.key, f);
    html += `<tr><td class="item">${esc(f.name)}<small>${esc(nm(f, "ship_ja", "ship_en"))}</small>${fitSource(f)}${fitActions(f)}${fitCost(f)}</td>`;
    html += chars.map((c) => {
      const check = f.checks[c.character_id];
      const title = `${tr("{0}（{1}）", f.name, nm(f, "ship_ja", "ship_en"))}`;
      // フィット全体のプランには、CPU・PG を足りさせるスキルも含める
      const plan = { types: f.type_ids, skills: suggestedSkills(check), char: c.character_id, title };
      return `<td>${resultCell(check, false, plan)}${resourceBlock(check, { char: c.character_id, title: `${tr("{0} の CPU / PG", title)}` })}</td>`;
    }).join("");
    html += `</tr>`;
  }
  return html + `</tbody></table></div>`;
}

let fittingsData = null;
let eftData = null;

async function loadFittings() {
  try {
    fittingsData = await api("GET", "/api/fittings");
  } catch (e) {
    fittingsData = null;
    $("#fittings").innerHTML = `<div class="warn">${esc(e.message)}</div>`;
    return;
  }
  renderFittings();
}

function renderFittings() {
  if (!fittingsData) return;
  const chars = readyChars();
  const names = new Set(chars.map((c) => c.character_name));
  // フィットは誰が保存したものでも表示し、判定の列だけを表示中のキャラクターに絞る
  const fits = fittingsData.fittings;
  const noScope = fittingsData.without_scope.filter((n) => names.has(n));
  let html = "";
  if (fits.length && chars.length) html = fitMatrix(fits, chars);
  else if (!noScope.length) html = `<div class="card empty-card">${tr("保存されたフィットはありません。上の欄に EFT 形式を貼り付けて判定すると、このアプリに保存できます。")}</div>`;
  if (noScope.length) {
    html += `<p class="muted">${tr("{0} の保存済みフィットは、再ログインすると表示されます。", noScope.map(esc).join(LIST_SEP))}</p>`;
  }
  $("#fittings").innerHTML = html;
  hydratePrices($("#fittings"));
}

function renderEft() {
  if (!eftData) return;
  const box = $("#eft-result");
  const warn = eftData.unresolved.length
    ? `<div class="warn">${tr("見つからなかったアイテム: {0}", eftData.unresolved.map(esc).join(LIST_SEP))}</div>` : "";
  box.innerHTML = warn + fitMatrix([eftData], readyChars());
  box.querySelectorAll("details.cell").forEach((d) => { d.open = true; });
  hydratePrices(box);
}

async function checkEft() {
  const text = $("#eft-input").value;
  const box = $("#eft-result");
  if (!text.trim()) return;
  box.innerHTML = `<span class="muted">${tr("判定しています…")}</span>`;
  try {
    eftData = await api("POST", "/api/fit/check", { eft: text });
    renderEft();
  } catch (e) {
    eftData = null;
    box.innerHTML = `<div class="warn">${esc(e.message)}</div>`;
  }
}

// ---------- スキルプラン ----------

async function openPlan(types, charId, title, skills = []) {
  const dialog = $("#plan-dialog");
  const body = $("#plan-body");
  body.innerHTML = `<span class="muted">${tr("スキルプランを作成しています…")}</span>`;
  dialog.showModal();
  let plan;
  try {
    plan = await api("POST", "/api/plan", { type_ids: types, skills, character_id: charId });
  } catch (e) {
    body.innerHTML = `<div class="warn">${esc(e.message)}</div><div class="plan-actions"><button class="btn" type="button" data-action="close-plan">${tr("閉じる")}</button></div>`;
    return;
  }
  const last = [...plan.steps].reverse().find((s) => s.finish_at);
  const queuedCount = plan.steps.filter((s) => s.queued).length;
  const rows = plan.steps.map((s, i) => `<tr class="${s.queued ? "queued" : ""}">
      <td class="r muted">${i + 1}</td><td>${esc(s.name)} ${ROMAN[s.level]}</td>
      <td class="r num">${fmtNum(s.sp)}</td><td class="r">${esc(fmtMinutes(s.minutes))}</td>
      <td class="r">${s.queued ? tr("キュー済 · ") : ""}${esc(fmtLocal(s.finish_at))}</td></tr>`).join("");
  body.innerHTML = `
    <div class="plan-head"><div><h3>${esc(title)}</h3><span class="muted">${tr("{0} のスキルプラン", esc(plan.character_name))}</span></div>
      <button class="icon-btn" type="button" title="${tr("閉じる")}" data-action="close-plan">×</button></div>
    ${plan.steps.length ? `
    <div class="plan-summary">
      <span>${tr("手順 <b>{0}</b>{1}", plan.steps.length, (queuedCount ? `${tr("（うちキュー済 {0}）", queuedCount)}` : ""))}</span>
      <span>${tr("合計 <b>{0}</b>", esc(fmtMinutes(plan.total_minutes)))}</span>
      <span>${tr("キュー外 <b>{0}</b>", esc(fmtMinutes(plan.unqueued_minutes)))}</span>
      <span>${tr("必要 SP <b>{0}</b>{1}", fmtNum(plan.total_sp), (plan.unqueued_sp !== plan.total_sp ? `${tr("（キュー外 {0}）", fmtNum(plan.unqueued_sp))}` : ""))}</span>
      ${last ? `<span>${tr("完了見込み <b>{0}</b>", esc(fmtLocal(last.finish_at)))}</span>` : ""}
    </div>
    ${spCostBox(charId, plan.unqueued_sp)}
    <div class="table-scroll" style="max-height:50vh;overflow-y:auto">
      <table class="plan"><thead><tr><th class="r">#</th><th>${tr("スキル")}</th><th class="r">SP</th><th class="r">${tr("訓練時間")}</th><th class="r">${tr("完了見込み")}</th></tr></thead>
      <tbody>${rows}</tbody></table></div>
    <div class="plan-actions">
      <button class="btn primary" type="button" data-action="copy-plan">${tr("📋 コピー（キュー済みを除く）")}</button>
      <small>${tr("「英語スキル名 レベル」を 1 行ずつ並べた形式です。完了見込みは、今のスキルキューが終わってから順に訓練した場合です。")}</small>
    </div>` : `<p>${tr("必要なスキルはすべて習得済みです。")}</p>`}`;
  body.dataset.text = plan.text;
}

// ---------- 検索とプレビュー ----------

function statusDots(checks) {
  return readyChars().map((c) => {
    const r = checks?.[c.character_id];
    if (!r) return "";
    const icon = { ok: "✓", queued: "⏳", missing: "✗" }[r.status];
    const initial = esc([...c.character_name][0] || "?");
    return `<span class="dot ${r.status}" title="${esc(c.character_name)}">${initial} ${icon}</span>`;
  }).join("");
}

async function runSearch() {
  const q = $("#search").value.trim();
  const list = $("#search-results");
  if (!q) { list.hidden = true; return; }
  const seq = ++searchSeq;
  let data;
  try {
    data = await api("GET", `/api/search?q=${encodeURIComponent(q)}`);
  } catch (e) {
    toast(e.message, "error");
    return;
  }
  if (seq !== searchSeq) return; // 古い検索結果は捨てる
  state.catalog = data.catalog;
  renderCatalogBanner();
  activeIndex = -1;
  if (!data.catalog.searchable) {
    list.innerHTML = `<li class="empty">${tr("名前一覧を作成中です。完了すると検索できます。")}</li>`;
  } else if (!data.results.length) {
    list.innerHTML = `<li class="empty">${tr("「{0}」に一致する艦・装備はありません", esc(q))}</li>`;
  } else {
    list.innerHTML = data.results.map((r) =>
      `<li role="option" data-id="${r.id}"><span class="names"><b>${esc(nm(r))}</b><small>${nmSub(r, " · ")}${esc(r.category)} / ${esc(r.group)}</small></span>
       <span class="dots">${statusDots(r.checks)}</span></li>`).join("");
  }
  list.hidden = false;
}

function moveActive(delta) {
  const items = [...$("#search-results").querySelectorAll("li[data-id]")];
  if (!items.length) return;
  activeIndex = (activeIndex + delta + items.length) % items.length;
  items.forEach((li, i) => li.setAttribute("aria-selected", i === activeIndex));
  items[activeIndex].scrollIntoView({ block: "nearest" });
}

async function showPreview(typeId) {
  previewTypeId = typeId;
  $("#search-results").hidden = true;
  const box = $("#preview");
  box.hidden = false;
  box.innerHTML = `<span class="muted">${tr("必要スキルを確認しています…")}</span>`;
  try {
    renderPreview(await api("GET", `/api/check/${typeId}`));
  } catch (e) {
    box.innerHTML = `<div class="warn">${esc(e.message)}</div>`;
  }
}

let previewData = null;

function renderPreview(data = previewData) {
  if (!data) return;
  previewData = data;
  const added = state.targets.some((t) => t.type_id === data.type_id);
  const chars = readyChars();
  const sub = data.en !== nm(data) ? `<small>${nmSub(data, " · ")}</small>` : "";
  $("#preview").innerHTML = `
    <div class="preview-head">
      <div><h3>${esc(nm(data))}</h3>${sub}<small>${esc(data.category)}</small></div>
      <span class="actions">
        ${added ? `<span class="badge ok">${tr("チェックリストに追加済み")}</span>`
                : `<button class="btn primary small" type="button" data-action="add-target" data-id="${data.type_id}">${tr("＋ チェックリストに追加")}</button>`}
        <a class="btn small" href="/market?type_id=${data.type_id}">${tr("🛒 マーケットで見る")}</a>
        <button class="icon-btn" type="button" title="${tr("閉じる")}" data-action="close-preview">×</button>
      </span>
    </div>
    ${chars.length ? `<div class="preview-grid">${chars.map((c) =>
      `<div class="preview-char"><div class="who">${esc(c.character_name)}</div>${resultCell(data.checks[c.character_id], true,
        { types: [data.type_id], char: c.character_id, title: nm(data) })}</div>`).join("")}</div>`
      : `<p class="muted">${tr("キャラクターのデータがありません。")}</p>`}`;
  hydratePrices($("#preview"));
}

// ---------- 購入費の計算に使うマーケットの場所 ----------

let marketLocations = null;

async function loadMarketLocations() {
  try {
    marketLocations = await api("GET", "/api/market/locations");
  } catch (e) {
    toast(e.message, "error");
    return;
  }
  renderMarketLocationSelect();
}

function renderMarketLocationSelect() {
  const sel = $("#market-location");
  const opt = (loc, label) => `<option value="${loc.id}" ${loc.id === marketLoc.id ? "selected" : ""}>${esc(label)}</option>`;
  const hubs = marketLocations.hubs.map((h) => opt(h, `${h.short} — ${h.name}`)).join("");
  const owned = marketLocations.owned.map((o) =>
    opt(o, `${tr("{0}{1}（艦 {2} 隻）", o.kind === "structure" ? "🏰 " : "", o.name, o.count)}`)).join("");
  const known = [...marketLocations.hubs, ...marketLocations.owned].some((l) => l.id === marketLoc.id);
  const custom = known ? "" : `<optgroup label="${tr("指定した場所")}">${opt(marketLoc, marketLoc.name)}</optgroup>`;
  sel.innerHTML = `<optgroup label="${tr("主要な取引拠点")}">${hubs}</optgroup>
    ${owned ? `<optgroup label="${tr("艦が置いてある場所")}">${owned}</optgroup>` : ""}${custom}
    <option value="name">${tr("名前で指定（NPC ステーション）…")}</option>`;
  $("#market-structure-note").hidden = marketLocations.structure_markets;
}

async function onMarketLocationChange() {
  const sel = $("#market-location");
  if (sel.value === "name") {
    const name = prompt(tr("NPC ステーションの名前（完全一致。例: Jita IV - Moon 4 - Caldari Navy Assembly Plant）"));
    if (!name?.trim()) { renderMarketLocationSelect(); return; }
    try {
      const loc = await api("GET", `/api/market/resolve?name=${encodeURIComponent(name.trim())}`);
      await setMarketLocation({ id: loc.id, name: loc.name });
    } catch (e) {
      toast(e.message, "error");
    }
    renderMarketLocationSelect();
    return;
  }
  const id = Number(sel.value);
  const loc = [...marketLocations.hubs, ...marketLocations.owned].find((l) => l.id === id);
  await setMarketLocation({ id, name: loc.name, short: loc.short });
}

// ---------- 読み込み・更新 ----------

// ブーストの変更など、計算条件が変わったときにサーバーから取り直す
async function reloadAll() {
  await loadState(); // フィット一覧もここで取り直す
  if (previewTypeId && !$("#preview").hidden) await showPreview(previewTypeId);
  if (eftData) await checkEft();
}

function renderAll() {
  renderFilterBar();
  renderSummary();
  renderAlerts();
  renderChecklist();
  renderCharacters();
  renderFittings();
  renderEft();
  if (!$("#preview").hidden) renderPreview();
  hydratePrices();
}

async function loadState() {
  state = await api("GET", "/api/state");
  renderAll();
  renderCatalogBanner();
  loadFittings();
  if (state.catalog.status === "building") setTimeout(pollCatalog, 2000);
}

async function pollCatalog() {
  const data = await api("GET", "/api/search?q=").catch(() => null);
  if (!data) return;
  state.catalog = data.catalog;
  renderCatalogBanner();
  if (data.catalog.status === "building") {
    setTimeout(pollCatalog, 2000);
  } else if (data.catalog.status === "ready") {
    toast(tr("艦・装備の名前一覧を作成しました。検索できます。"), "ok");
    if ($("#search").value.trim()) runSearch();
  }
}

async function refresh(characterId) {
  const btn = $("#refresh-btn");
  btn.disabled = true;
  btn.textContent = tr("更新中…");
  try {
    const res = await api("POST", "/api/refresh", characterId ? { character_id: characterId } : {});
    res.errors.forEach((e) => toast(e, "error"));
    if (!res.errors.length) toast(tr("最新のデータに更新しました。"), "ok");
    await loadState();
    if (previewTypeId) showPreview(previewTypeId);
  } catch (e) {
    toast(e.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = tr("↻ 最新に更新");
  }
}

function needsRefresh() {
  const limit = Date.now() - STALE_MINUTES * 60 * 1000;
  return state.characters.some((c) => c.missing || !c.fetched_at || new Date(c.fetched_at).getTime() < limit);
}

// ---------- イベント ----------

document.addEventListener("click", async (ev) => {
  const li = ev.target.closest("#search-results li[data-id]");
  if (li) { showPreview(Number(li.dataset.id)); return; }
  if (!ev.target.closest(".search-wrap")) $("#search-results").hidden = true;

  const el = ev.target.closest("[data-action]");
  if (!el) return;
  const id = Number(el.dataset.id);
  try {
    switch (el.dataset.action) {
      case "add-target":
        await api("POST", "/api/targets", { type_id: id });
        await loadState();
        showPreview(id);
        break;
      case "remove-target":
        await api("DELETE", `/api/targets/${id}`);
        await loadState();
        break;
      case "close-preview":
        $("#preview").hidden = true;
        previewTypeId = null;
        previewData = null;
        break;
      case "select-char":
        selectedChar = id;
        renderCharacters();
        break;
      case "refresh-one":
        await refresh(id);
        break;
      case "remove-char":
        if (!confirm(`${tr("{0} の登録を削除しますか？（もう一度追加すれば元に戻せます）", el.dataset.name)}`)) return;
        await api("DELETE", `/api/characters/${id}`);
        await loadState();
        break;
      case "rebuild":
        await api("POST", "/api/catalog/rebuild");
        await loadState();
        break;
      case "filter-all":
        setFilter({ mode: "all" });
        break;
      case "filter-group":
        setFilter({ mode: "group", id: el.dataset.id });
        break;
      case "group-new": {
        const ids = [...visibleIds()];
        if (!ids.length) { toast(tr("キャラクターを 1 人以上選んでください。"), "error"); break; }
        const name = prompt(tr("グループ名（例: 戦闘、産業、探索）"));
        if (!name?.trim()) break;
        const group = await saveGroup({ name: name.trim(), character_ids: ids });
        setFilter({ mode: "group", id: group.id });
        toast(`${tr("グループ「{0}」を保存しました。", group.name)}`, "ok");
        break;
      }
      case "group-rename": {
        const group = activeGroup();
        const name = prompt(tr("新しいグループ名"), group.name);
        if (!name?.trim() || name.trim() === group.name) break;
        await saveGroup({ id: group.id, name: name.trim(), character_ids: group.character_ids });
        renderAll();
        break;
      }
      case "group-delete": {
        const group = activeGroup();
        if (!confirm(`${tr("グループ「{0}」を削除しますか？（キャラクターは削除されません）", group.name)}`)) break;
        await api("DELETE", `/api/groups/${encodeURIComponent(group.id)}`);
        state.groups = state.groups.filter((g) => g.id !== group.id);
        setFilter({ mode: "all" });
        break;
      }
      case "boost-preset": {
        const v = Number(el.dataset.value);
        document.querySelectorAll("#boost-body input[data-attr]").forEach((i) => { i.value = v; });
        renderBoostPreview();
        break;
      }
      case "boost-apply":
        $("#boost-dialog").close();
        await setBoost(boostInputs());
        break;
      case "boost-clear":
        $("#boost-dialog").close();
        await setBoost(Object.fromEntries(ATTRS.map(([k]) => [k, 0])));
        break;
      case "close-boost":
        $("#boost-dialog").close();
        break;
      case "open-boost":
        openBoostDialog();
        break;
      case "self-train": {
        const wrap = el.closest(".req-wrap");
        const on = !wrap.classList.contains("self-mode");
        wrap.classList.toggle("self-mode", on);
        wrap.querySelector(".self-summary").hidden = !on;
        el.setAttribute("aria-pressed", on);
        break;
      }
      case "edit-fit":
      case "try-t1": {
        saveJson("fitbuilder:eft", fitByKey.get(el.dataset.key).eft);
        saveJson("fitbuilder:t1", el.dataset.action === "try-t1");
        location.href = "/fitting";
        break;
      }
      case "copy-fit": {
        const fit = fitByKey.get(el.dataset.key);
        await navigator.clipboard.writeText(fit.eft);
        toast(`${tr("「{0}」をコピーしました。ゲームのフィッティング画面で「クリップボードからインポート」してください。", fit.name)}`, "ok");
        break;
      }
      case "save-fit": {
        const fit = fitByKey.get(el.dataset.key);
        const name = prompt(tr("保存するフィット名"), fit.name);
        if (name === null) break;
        await api("POST", "/api/saved-fits", { eft: fit.eft, name: name.trim() || fit.name });
        toast(`${tr("「{0}」を保存しました。", name.trim() || fit.name)}`, "ok");
        await loadFittings();
        break;
      }
      case "delete-fit": {
        const fit = fitByKey.get(el.dataset.key);
        if (!confirm(`${tr("保存したフィット「{0}」を削除しますか？", fit.name)}`)) break;
        await api("DELETE", `/api/saved-fits/${encodeURIComponent(fit.id)}`);
        await loadFittings();
        break;
      }
      case "plan":
        await openPlan(parseIds(el.dataset.types), Number(el.dataset.char), el.dataset.title, parseSkills(el.dataset.skills));
        break;
      case "close-plan":
        $("#plan-dialog").close();
        break;
      case "copy-plan":
        await navigator.clipboard.writeText($("#plan-body").dataset.text || "");
        toast(tr("スキルプランをコピーしました。"), "ok");
        break;
    }
  } catch (e) {
    toast(e.message, "error");
  }
});

$("#refresh-btn").addEventListener("click", () => refresh());
$("#eft-check-btn").addEventListener("click", checkEft);
$("#market-location").addEventListener("change", onMarketLocationChange);
$("#boost-btn").addEventListener("click", openBoostDialog);
$("#boost-dialog").addEventListener("input", (ev) => { if (ev.target.matches("input[data-attr]")) renderBoostPreview(); });
$("#boost-dialog").addEventListener("click", (ev) => { if (ev.target.id === "boost-dialog") ev.target.close(); });
// ダイアログの外側（背景）をクリックしたら閉じる
$("#plan-dialog").addEventListener("click", (ev) => { if (ev.target.id === "plan-dialog") ev.target.close(); });
$("#rebuild-btn").addEventListener("click", async () => {
  if (!confirm(tr("艦・装備の名前一覧を作り直しますか？（数分かかります）"))) return;
  await api("POST", "/api/catalog/rebuild").catch((e) => toast(e.message, "error"));
  await loadState();
});

$("#search").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(runSearch, 200);
});
$("#search").addEventListener("focus", () => { if ($("#search").value.trim()) runSearch(); });
$("#search").addEventListener("keydown", (ev) => {
  const list = $("#search-results");
  if (ev.key === "ArrowDown") { ev.preventDefault(); moveActive(1); }
  else if (ev.key === "ArrowUp") { ev.preventDefault(); moveActive(-1); }
  else if (ev.key === "Escape") { list.hidden = true; }
  else if (ev.key === "Enter") {
    const items = list.querySelectorAll("li[data-id]");
    const target = items[activeIndex >= 0 ? activeIndex : 0];
    if (target && !list.hidden) { ev.preventDefault(); showPreview(Number(target.dataset.id)); }
  }
});

// キャラクターのチェックボックス: グループ中に変更したら、その選択を元にした一時的な絞り込みになる
document.addEventListener("change", async (ev) => {
  if (!ev.target.matches('input[data-action="filter-toggle"]')) return;
  const ids = visibleIds();
  const id = Number(ev.target.dataset.id);
  if (ev.target.checked) ids.add(id); else ids.delete(id);
  const group = activeGroup();
  // グループ表示中にメンバーを変えたら、グループ自体を更新するか確認する
  if (group && ids.size && confirm(`${tr("グループ「{0}」のメンバーを変更して保存しますか？ （キャンセルすると、保存せずに今だけ絞り込みます）", group.name)}`)) {
    try {
      await saveGroup({ id: group.id, name: group.name, character_ids: [...ids] });
      renderAll();
      return;
    } catch (e) {
      toast(e.message, "error");
    }
  }
  setFilter(ids.size === state.characters.length ? { mode: "all" } : { mode: "custom", ids: [...ids] });
});

// 全スキル一覧の絞り込み（パネルは再描画されるのでイベント委譲）
document.addEventListener("input", (ev) => {
  if (!ev.target.matches(".skill-search")) return;
  const q = ev.target.value.trim().toLowerCase();
  ev.target.closest("details").querySelectorAll("tbody tr").forEach((r) => {
    r.hidden = q && !r.textContent.toLowerCase().includes(q);
  });
});

// ---------- 起動 ----------

(async () => {
  const params = new URLSearchParams(location.search);
  if (params.get("added")) toast(`${tr("{0} を追加しました。", params.get("added"))}`, "ok");
  if (params.get("error")) toast(params.get("error"), "error");
  if (params.has("added") || params.has("error")) history.replaceState(null, "", "/");

  try {
    await loadState();
    loadMarketLocations();
    if (needsRefresh()) await refresh();
  } catch (e) {
    toast(e.message, "error");
  }
})();
