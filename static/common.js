"use strict";
// 全ページ共通のユーティリティ（書式・通信・通知）

const ROMAN = ["0", "I", "II", "III", "IV", "V"];

const $ = (sel) => document.querySelector(sel);

function esc(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function fmtMinutes(minutes) {
  if (minutes == null) return tr("不明");
  const m = Math.ceil(minutes);
  const days = Math.floor(m / 1440);
  const hours = Math.floor((m % 1440) / 60);
  if (days) return `${tr("{0}日 {1}時間", days, hours)}`;
  if (hours) return `${tr("{0}時間 {1}分", hours, m % 60)}`;
  return `${tr("{0}分", m % 60)}`;
}

function fmtLocal(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function fmtNum(n) {
  return Number(n || 0).toLocaleString(LOCALE);
}

function fmtIsk(n) {
  if (n == null) return "-";
  const abs = Math.abs(n);
  if (abs >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  if (abs >= 1e4) return `${(n / 1e3).toFixed(1)}K`;
  return Number(n).toLocaleString(LOCALE, { maximumFractionDigits: 2 });
}

const fullIsk = (n) => `${Number(n).toLocaleString(LOCALE, { maximumFractionDigits: 2 })} ISK`;

const fmtPct = (n, digits = 2) => `${Number(n).toLocaleString(LOCALE, { maximumFractionDigits: digits })}%`;

// サーバーへのリクエスト（変更系は X-Requested-With が必須）
async function request(method, url, body) {
  const res = await fetch(url, {
    method,
    headers: { "X-Requested-With": "skill-checker", ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  // クラウドでパスワードを設定しているとき、サインインが切れたらサインインの画面へ
  if (res.status === 401 && url.startsWith("/api/")) location.href = `/signin?next=${encodeURIComponent(location.pathname + location.search)}`;
  if (!res.ok) throw new Error(data.error || `${tr("通信エラー ({0})", res.status)}`);
  return data;
}

function toast(message, kind = "") {
  const box = $("#toasts");
  if (!box) return;
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = message;
  box.append(el);
  setTimeout(() => el.remove(), kind === "error" ? 10000 : 4000);
}

// マーケットの場所（スキルチェッカーの購入費とマーケットページで共有）
const MARKET_KEY = "skill-checker:market";
const DEFAULT_MARKET = { id: 60003760, name: "Jita IV - Moon 4 - Caldari Navy Assembly Plant", short: "Jita 4-4" };

function loadMarketLocation() {
  try {
    const saved = JSON.parse(localStorage.getItem(MARKET_KEY));
    return saved?.id ? saved : DEFAULT_MARKET;
  } catch {
    return DEFAULT_MARKET;
  }
}

function saveMarketLocation(loc) {
  try { localStorage.setItem(MARKET_KEY, JSON.stringify(loc)); } catch { /* 保存できなくても今回は使う */ }
}

// localStorage の読み書き（使えない環境でも動くように）
function loadJson(key, fallback) {
  try {
    const v = JSON.parse(localStorage.getItem(key));
    return v ?? fallback;
  } catch {
    return fallback;
  }
}

function saveJson(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* 保存できなくても動作は続ける */ }
}

// ---------- ブースト（スキルチェッカーで設定した値を、おすすめページの訓練時間にも使う） ----------
const BOOST_STORAGE_KEY = "skill-checker:boost";
const BOOST_ATTR_KEYS = ["perception", "memory", "willpower", "intelligence", "charisma"];

function boostQuery() {
  const b = loadJson(BOOST_STORAGE_KEY, {});
  if (!BOOST_ATTR_KEYS.some((k) => Number(b[k]) > 0)) return "";
  return `boost=${BOOST_ATTR_KEYS.map((k) => Number(b[k]) || 0).join(",")}`;
}

function withBoostQuery(url) {
  const q = boostQuery();
  return q ? `${url}${url.includes("?") ? "&" : "?"}${q}` : url;
}

// ---------- スキルプランのダイアログ（おすすめページ用） ----------
async function openPlanDialog({ types = [], skills = [], charId, title }) {
  let dialog = document.getElementById("common-plan-dialog");
  if (!dialog) {
    dialog = document.createElement("dialog");
    dialog.id = "common-plan-dialog";
    dialog.className = "plan-dialog";
    dialog.innerHTML = `<div class="dialog-body" id="common-plan-body"></div>`;
    document.body.append(dialog);
    dialog.addEventListener("click", async (ev) => {
      if (ev.target === dialog || ev.target.closest("[data-plan-close]")) dialog.close();
      if (ev.target.closest("[data-plan-copy]")) {
        await navigator.clipboard.writeText(dialog.dataset.text || "");
        toast(tr("スキルプランをコピーしました。"), "ok");
      }
    });
  }
  const body = document.getElementById("common-plan-body");
  body.innerHTML = `<span class="muted">${tr("スキルプランを作成しています…")}</span>`;
  dialog.showModal();
  let plan;
  try {
    plan = await request("POST", withBoostQuery("/api/plan"), { type_ids: types, skills, character_id: charId });
  } catch (e) {
    body.innerHTML = `<div class="warn">${esc(e.message)}</div><div class="plan-actions"><button class="btn" type="button" data-plan-close>${tr("閉じる")}</button></div>`;
    return;
  }
  const last = [...plan.steps].reverse().find((s) => s.finish_at);
  const rows = plan.steps.map((s, i) => `<tr class="${s.queued ? "queued" : ""}"><td class="r muted">${i + 1}</td>
    <td>${esc(s.name)} ${ROMAN[s.level]}</td><td class="r num">${fmtNum(s.sp)}</td><td class="r">${esc(fmtMinutes(s.minutes))}</td>
    <td class="r">${s.queued ? tr("キュー済 · ") : ""}${esc(fmtLocal(s.finish_at))}</td></tr>`).join("");
  body.innerHTML = `
    <div class="plan-head"><div><h3>${esc(title)}</h3><span class="muted">${tr("{0} のスキルプラン", esc(plan.character_name))}</span></div>
      <button class="icon-btn" type="button" title="${tr("閉じる")}" data-plan-close>×</button></div>
    ${plan.steps.length ? `
    <div class="plan-summary"><span>${tr("手順 <b>{0}</b>", plan.steps.length)}</span><span>${tr("合計 <b>{0}</b>", esc(fmtMinutes(plan.total_minutes)))}</span>
      <span>${tr("必要 SP <b>{0}</b>{1}", fmtNum(plan.total_sp), (plan.unqueued_sp !== plan.total_sp ? `${tr("（キュー外 {0}）", fmtNum(plan.unqueued_sp))}` : ""))}</span>
      ${last ? `<span>${tr("完了見込み <b>{0}</b>", esc(fmtLocal(last.finish_at)))}</span>` : ""}</div>
    ${spCostBox(charId, plan.unqueued_sp)}
    <div class="table-scroll" style="max-height:50vh;overflow-y:auto"><table class="plan"><thead><tr><th class="r">#</th><th>${tr("スキル")}</th><th class="r">SP</th>
      <th class="r">${tr("訓練時間")}</th><th class="r">${tr("完了見込み")}</th></tr></thead><tbody>${rows}</tbody></table></div>
    <div class="plan-actions"><button class="btn primary" type="button" data-plan-copy>${tr("📋 コピー（キュー済みを除く）")}</button>
      <small>${tr("「英語スキル名 レベル」を 1 行ずつ並べた形式です。")}</small></div>` : `<p>${tr("必要なスキルはすべて習得済みです。")}</p>`}`;
  dialog.dataset.text = plan.text;
}

// ---------- スキルポイント（スキルキュー・スキルプランで共有） ----------

// スキルキューの 1 行で、まだ入っていない SP（訓練中なら時間から今の進み具合を見積もる）
function queueRemainingSp(q, now = Date.now()) {
  const end = q.level_end_sp;
  const start = q.training_start_sp ?? q.level_start_sp;
  if (end == null || start == null) return null;
  const s = Date.parse(q.start_date);
  const f = Date.parse(q.finish_date);
  if (f && now >= f) return 0;
  if (s && f && now > s && f > s) return Math.max(0, Math.round((end - start) * (f - now) / (f - s)));
  return Math.max(0, end - start);
}

// 開くと「未割り当て SP とスキルインジェクターで入れると」の見積もりを読み込む欄
function spCostBox(charId, sp) {
  if (!charId || !sp) return "";
  return `<details class="mini-details sp-cost" data-char="${charId}" data-sp="${Math.round(sp)}">
    <summary>${tr("💉 スキルインジェクターで入れると")}</summary><div class="sp-cost-body muted">${tr("読み込み中…")}</div></details>`;
}

function spCostHtml(d) {
  const isk = (v) => (v == null ? tr("価格不明") : `${tr("約 {0} ISK", fmtIsk(v))}`);
  const lines = [`${tr("必要 <b>{0}</b> SP", fmtNum(d.sp))}`];
  if (d.unallocated) lines.push(`${tr("未割り当て SP {0} を使うと、残り <b>{1}</b> SP", fmtNum(d.unallocated), fmtNum(d.need))}`);
  if (!d.need) return `<div>${lines.join(" · ")}</div><div class="ok-text">${tr("✓ 未割り当て SP だけで足ります。")}</div>`;
  const mixed = d.mixed.small
    ? `<li>${tr("ラージ {0} 個 ＋ スモール {1} 個: <b>{2}</b>", fmtNum(d.mixed.large), fmtNum(d.mixed.small), isk(d.mixed.isk))}</li>` : "";
  return `<div>${lines.join(" · ")}</div>
    <ul class="sp-cost-list"><li>${tr("ラージ スキルインジェクター {0} 個: <b>{1}</b>", fmtNum(d.large_only.large), isk(d.large_only.isk))}</li>${mixed}</ul>
    <small class="muted">${tr("総 SP {0} の今は、ラージ 1 個で {1} SP・スモール 1 個で {2} SP 入ります（総 SP が増えると減る分も計算済み）。 価格は Jita の最安の売り値（ラージ {3}・スモール {4}）。", fmtNum(d.total_sp), fmtNum(d.yield_large), fmtNum(d.yield_small), d.price_large ? fmtIsk(d.price_large) : "-", d.price_small ? fmtIsk(d.price_small) : "-")}</small>`;
}

// <details> の toggle はバブリングしないので、キャプチャで拾う
document.addEventListener("toggle", async (ev) => {
  const box = ev.target;
  if (!box.matches?.("details.sp-cost") || !box.open || box.dataset.loaded) return;
  box.dataset.loaded = "1";
  const body = box.querySelector(".sp-cost-body");
  try {
    const d = await request("GET", `/api/sp-cost?character_id=${box.dataset.char}&sp=${box.dataset.sp}`);
    body.classList.remove("muted");
    body.innerHTML = spCostHtml(d);
  } catch (e) {
    body.innerHTML = `<span class="warn-text">${esc(e.message)}</span>`;
    delete box.dataset.loaded;
  }
}, true);

// ---------- ルート（移動・ハブ間の転売で共有） ----------

// ローセク・ヌルセクを通るか（安全優先のルートでも通ることがある）
function routeSafetyHtml(d) {
  const lows = d.systems.filter((s) => s.kind === "lowsec").map((s) => `${s.name} ${(s.security ?? 0).toFixed(1)}`);
  const warn = [];
  if (d.lowsec) warn.push(`${tr("ローセク {0} 星系{1}", d.lowsec, (lows.length <= 5 ? `${tr("（{0}）", lows.join(LIST_SEP))}` : ""))}`);
  if (d.nullsec) warn.push(`${tr("ヌルセク {0} 星系", d.nullsec)}`);
  let compare = "";
  if (d.secure_jumps != null) {  // ゲームの「安全優先」とくらべる
    const diff = d.secure_jumps - d.jumps;
    compare = diff > 0 ? ` <span class="badge ok">${tr("安全優先（{0} ジャンプ）より {1} ジャンプ短い", d.secure_jumps, diff)}</span>`
      : diff < 0 ? ` <span class="badge queued">${tr("安全優先（{0} ジャンプ）より {1} ジャンプ長い", d.secure_jumps, -diff)}</span>`
      : ` <span class="muted">${tr("安全優先と同じジャンプ数")}</span>`;
  }
  if (!warn.length) return `<span class="badge ok">${tr("✓ ハイセクのみ")}</span>${compare}`;
  const note = d.flag === "secure" ? tr("安全優先のルートでも、") : "";
  return `<span class="badge missing">${tr("⚠ {0}{1}を通ります", note, esc(warn.join(DOT_SEP)))}</span>${compare}`;
}

// ルートの種類（移動・ハブ間の転売のフォームで共有）
function routeFlagOptions(selected = "highsec") {
  const flags = [["highsec", tr("ローセクを制限した最短")], ["secure", tr("安全優先（ゲームと同じ）")], ["shortest", tr("最短")], ["insecure", tr("危険な星系を優先")]];
  return flags.map(([v, l]) => `<option value="${v}" ${v === selected ? "selected" : ""}>${l}</option>`).join("");
}

function minSecOptions(selected = 0.5) {
  return [0.5, 0.6, 0.7, 0.8, 0.9].map((v) => `<option value="${v}" ${v === Number(selected) ? "selected" : ""}>${tr("{0} 以上{1}", v.toFixed(1), v === 0.5 ? tr("（ハイセクすべて）") : "")}</option>`).join("");
}

function maxLowOptions(selected = 0) {
  return [0, 1, 2, 3].map((v) => `<option value="${v}" ${v === Number(selected) ? "selected" : ""}>${v ? `${tr("{0} か所まで", v)}` : tr("通らない")}</option>`).join("");
}

// ゲームのオートパイロットが、このルートどおりに進むよう経由地を入れるボタン
function routeGameButton(d) {
  if (d.flag !== "highsec") return "";
  return `<button class="btn" type="button" data-route-game="${d.systems.map((s) => s.id).join(",")}" title="${tr("ゲームのルートの設定が「安全優先」のとき、このルートから外れるところだけ経由地を入れます")}">${tr("🧭 このルートどおりにゲームに設定")}</button>`;
}

document.addEventListener("click", async (ev) => {
  const b = ev.target.closest("[data-route-game]");
  if (!b) return;
  const character_id = gameCharId();
  if (!character_id) { toast(tr("操作するキャラクターを選んでください。"), "error"); return; }
  b.disabled = true;
  try {
    const d = await request("POST", "/api/ui/route", { character_id, systems: b.dataset.routeGame.split(",").map(Number) });
    toast(`${tr("経由地 {0} か所（{1}）を設定しました（ゲームにログイン中のときだけ反映されます）", d.waypoints.length, d.waypoints.join(" → "))}`, "ok");
  } catch (e) {
    toast(e.message, "error");
  } finally {
    b.disabled = false;
  }
});

// オートパイロットで移動したときの時間の見積もり
function autopilotHtml(a) {
  if (!a) return "";
  if (a.error) return `<div class="autopilot muted">${tr("🚀 オートパイロットの時間: {0}", esc(a.error))}</div>`;
  const m = (sec) => fmtMinutes(sec / 60);
  const where = [a.from_station ? "" : tr("出発は恒星の近くから"), a.to_station ? tr("到着後のドックまで") : tr("到着はゲートを出たところまで")].filter(Boolean).join(DOT_SEP);
  return `<div class="autopilot"><div>${tr("🚀 オートパイロット（{0}）で 約 <b>{1}</b>", esc(nm(a.ship)), esc(m(a.seconds)))}</div>
    <small class="muted">${tr("整列 {0} · ワープ {1} · ゲートに近づく {2} · ジャンプ {3}", esc(m(a.align)), esc(m(a.warp)), esc(m(a.approach)), esc(m(a.jump)))}</small>
    <small class="muted">${tr("ワープ速度 {0} AU/s・整列 {1} 秒・最高速度 {2} m/s（装備なし・スキル込み、艦のボーナスは含まない）。 オートパイロットはゲートの 15 km 手前に出るので、手動でゲートに直接ワープするより遅くなります。{3}。{4}", a.ship.warp.toFixed(2), a.ship.align.toFixed(1), fmtNum(Math.round(a.ship.velocity)), esc(where), (a.missing_gates ? ` ${tr("ゲートの位置が分からない星系が {0} あります。", a.missing_gates)}` : ""))}</small></div>`;
}

// キャラクターの選択（おすすめページで共有）
const REC_CHAR_KEY = "recommend:character";

// ---------- キャラクターの絞り込み（スキルチェッカーの「表示」と共有） ----------
const CHAR_FILTER_KEY = "skill-checker:filter";

function loadCharFilter() {
  return loadJson(CHAR_FILTER_KEY, { mode: "all" }) || { mode: "all" };
}

// 絞り込みで選ばれているキャラクターの ID（Set）
function filteredIds(characters, groups, filter = loadCharFilter()) {
  const all = characters.map((c) => c.character_id);
  if (filter.mode === "group") {
    const g = (groups || []).find((x) => x.id === filter.id);
    return new Set(g ? g.character_ids : all);
  }
  if (filter.mode === "custom") return new Set(filter.ids || []);
  return new Set(all);
}

// 絞り込みのチップ（すべて・グループ）。変更すると保存して onChange(ids) を呼ぶ
function renderCharFilter(el, characters, groups, onChange) {
  const filter = loadCharFilter();
  const ids = filteredIds(characters, groups, filter);
  const chip = (label, pressed, attrs) => `<button class="fchip" type="button" aria-pressed="${pressed}" ${attrs}>${label}</button>`;
  const chips = [chip(tr("すべて"), filter.mode === "all", `data-cf="all"`),
    ...(groups || []).map((g) => chip(`${esc(g.name)} <small>${g.character_ids.length}</small>`, filter.mode === "group" && filter.id === g.id, `data-cf="group" data-id="${esc(g.id)}"`))];
  if (filter.mode === "custom") chips.push(chip(`${tr("選んだキャラクター <small>{0}</small>", ids.size)}`, true, `data-cf="custom"`));
  const names = characters.filter((c) => ids.has(c.character_id)).map((c) => c.character_name);
  el.innerHTML = `<div class="filter-row"><span class="filter-label">${tr("キャラクター")}</span><div class="fchips">${chips.join("")}</div></div>
    <small class="muted">${tr("{0} · <a href=\"/skills\">スキルチェッカー</a>でグループを作れます", names.length ? esc(names.join(LIST_SEP)) : tr("キャラクターがいません"))}</small>`;
  el.onclick = (ev) => {
    const b = ev.target.closest("[data-cf]");
    if (!b || b.dataset.cf === "custom") return;
    saveJson(CHAR_FILTER_KEY, b.dataset.cf === "all" ? { mode: "all" } : { mode: "group", id: b.dataset.id });
    renderCharFilter(el, characters, groups, onChange);
    onChange(filteredIds(characters, groups));
  };
  return ids;
}

const idsQuery = (ids) => `ids=${[...ids].join(",")}`;

// キャラクターごとの取得エラー（再ログインが必要など）の説明
function charErrors(rows) {
  const scope = rows.filter((r) => r.needs_scope).map((r) => r.character_name);
  const other = rows.filter((r) => r.error || r.forbidden).map((r) => `${r.character_name}: ${r.error || r.forbidden}`);
  return (scope.length ? `<div class="alert info"><span>${tr("{0} は <a href=\"/login\">再ログイン</a> が必要です（新しい機能の権限の許可）。", esc(scope.join(LIST_SEP)))}</span></div>` : "")
    + (other.length ? `<div class="warn">${other.map(esc).join("<br>")}</div>` : "");
}

// ---------- ゲームの操作（目的地の設定・マーケットを開く）に使うキャラクター ----------
const GAME_CHAR_KEY = "game:character";

function gameCharSelect(characters) {
  const saved = loadJson(GAME_CHAR_KEY, null);
  const chosen = characters.some((c) => c.character_id === saved) ? saved : characters[0]?.character_id;
  return `<label class="game-char">🎮 <select data-game-char>${characters.map((c) =>
    `<option value="${c.character_id}" ${c.character_id === chosen ? "selected" : ""}>${esc(c.character_name)}</option>`).join("")}</select></label>`;
}

document.addEventListener("change", (ev) => {
  if (ev.target.matches("[data-game-char]")) {
    saveJson(GAME_CHAR_KEY, Number(ev.target.value));
    document.querySelectorAll("[data-game-char]").forEach((s) => { s.value = ev.target.value; });
  }
});

function gameCharId() {
  return Number(document.querySelector("[data-game-char]")?.value || loadJson(GAME_CHAR_KEY, 0));
}

async function gameAction(url, body, okMessage) {
  const character_id = gameCharId();
  if (!character_id) { toast(tr("操作するキャラクターを選んでください。"), "error"); return; }
  try {
    await request("POST", url, { ...body, character_id });
    toast(okMessage + tr("（ゲームにログイン中のときだけ反映されます）"), "ok");
  } catch (e) {
    toast(e.message, "error");
  }
}

// ---------- グラフ（SVG） ----------
// points: [{x: ラベル, y: 値}]。kind: "line" | "bar"
function svgChart(points, { height = 160, kind = "line", fmt = fmtIsk, color = "var(--bar)" } = {}) {
  if (!points.length) return `<p class="muted">${tr("データがありません。")}</p>`;
  const w = 600, h = height, pad = 4;
  const ys = points.map((p) => p.y);
  const min = kind === "bar" ? Math.min(0, ...ys) : Math.min(...ys);
  const max = Math.max(...ys, min + 1e-9);
  const x = (i) => pad + (points.length === 1 ? (w - 2 * pad) / 2 : (i * (w - 2 * pad)) / (points.length - 1));
  const y = (v) => h - pad - ((v - min) / (max - min || 1)) * (h - 2 * pad);
  let body;
  if (kind === "bar") {
    const bw = Math.max(1, (w - 2 * pad) / points.length - 2);
    body = points.map((p, i) => {
      const x0 = pad + i * ((w - 2 * pad) / points.length) + 1;
      const top = Math.min(y(p.y), y(0)), bh = Math.abs(y(p.y) - y(0));
      return `<rect x="${x0}" y="${top}" width="${bw}" height="${Math.max(bh, 0.5)}" fill="${p.y < 0 ? "var(--miss)" : color}"><title>${esc(p.x)}: ${esc(fmt(p.y))}</title></rect>`;
    }).join("");
  } else {
    const d = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.y).toFixed(1)}`).join("");
    body = `<path d="${d}" fill="none" stroke="${color}" stroke-width="2" vector-effect="non-scaling-stroke"/>`
      + points.map((p, i) => `<circle cx="${x(i)}" cy="${y(p.y)}" r="6" fill="transparent"><title>${esc(p.x)}: ${esc(fmt(p.y))}</title></circle>`).join("");
  }
  return `<div class="chart"><div class="chart-axis"><span>${esc(fmt(max))}</span><span>${esc(fmt(min))}</span></div>
    <svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img">${body}</svg>
    <div class="chart-x"><span>${esc(points[0].x)}</span><span>${esc(points[points.length - 1].x)}</span></div></div>`;
}

// 残り時間（例: 3日 4時間 / 完了）
function timeLeft(iso) {
  if (!iso) return "-";
  const ms = new Date(iso) - Date.now();
  if (ms <= 0) return tr("完了");
  return fmtMinutes(ms / 60000);
}

// ---------- トレードスキルが一番高いキャラクターが「買い注文で買う」場合の仲介手数料 ----------
// 売り注文から即買いするときは手数料がかからない（誰が買っても同じ）。買い注文を出すときだけ仲介手数料がかかり、
// Broker Relations とスタンディング（NPC ステーション）で下がる。手数料の設定はマーケットのページと共有する。
const traderCache = new Map(); // 場所 ID → Promise<{name, broker, ...}>

function bestTrader(locationId = 60003760) {
  if (!traderCache.has(locationId)) {
    traderCache.set(locationId, (async () => {
      const { characters } = await request("GET", "/api/characters");
      const ready = characters.filter((c) => !c.missing && c.trade_skills);
      if (!ready.length) return null;
      const best = ready.reduce((a, b) => {
        const ka = [a.trade_skills.broker_relations, a.trade_skills.accounting];
        const kb = [b.trade_skills.broker_relations, b.trade_skills.accounting];
        return kb[0] > ka[0] || (kb[0] === ka[0] && kb[1] > ka[1]) ? b : a;
      });
      const fees = { baseBroker: 3.0, brokerPerLevel: 0.3, structureBroker: "", ...loadJson("market:fees", {}) };
      const isStructure = locationId >= 1e12;
      let broker = Math.max(fees.baseBroker - fees.brokerPerLevel * best.trade_skills.broker_relations, 0);
      let reduction = 0;
      if (isStructure && fees.structureBroker !== "" && fees.structureBroker != null) {
        broker = Number(fees.structureBroker);
      } else if (!isStructure) {
        try {
          const st = await request("GET", `/api/market/standings?character_id=${best.character_id}&locations=${locationId}`);
          reduction = st.locations?.[locationId]?.reduction || 0;
        } catch { /* スタンディングが取れなければスキルだけで計算する */ }
        broker = Math.max(broker - reduction, 0);
      }
      return { id: best.character_id, name: best.character_name, broker, reduction,
        broker_relations: best.trade_skills.broker_relations, structure: isStructure };
    })().catch(() => null));
  }
  return traderCache.get(locationId);
}

function traderLabel(t) {
  return `${tr("{0}・Broker Relations {1}{2}・仲介手数料 {3}", esc(t.name), ROMAN[t.broker_relations], (t.reduction ? `${tr("・スタンディング −{0}", fmtPct(t.reduction, 2))}` : ""), fmtPct(t.broker, 2))}`;
}

// ---------- スクランブル強度を上げたフィット（ワープコアスタビライザー版）の表示（おすすめページで共有） ----------
const WCS_KEY = "fits:wcs";
const wcsEnabled = () => Boolean(loadJson(WCS_KEY, false));
const wcsQuery = () => (wcsEnabled() ? "&wcs=1" : "");

function bindWcsToggle(onChange) {
  const box = document.getElementById("wcs-toggle");
  if (!box) return;
  box.checked = wcsEnabled();
  box.addEventListener("change", () => { saveJson(WCS_KEY, box.checked); onChange?.(); });
}

// ---------- ナビのメニュー ----------
document.addEventListener("click", (ev) => {
  document.querySelectorAll("details.nav-group[open]").forEach((d) => { if (!d.contains(ev.target)) d.open = false; });
});
document.addEventListener("toggle", (ev) => {
  if (ev.target.matches?.("details.nav-group") && ev.target.open) {
    document.querySelectorAll("details.nav-group[open]").forEach((d) => { if (d !== ev.target) d.open = false; });
  }
}, true);
