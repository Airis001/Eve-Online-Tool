"use strict";
// フィットのカード（おすすめフィット・おすすめ艦船のページで共通）

const SOURCE_LABEL = { template: tr("定番"), app: tr("保存したフィット"), game: tr("ゲーム内のフィット"), auto: tr("自動で組んだフィット（試作）") };
const SOURCE_BADGE = { template: "queued", app: "ok", game: "ok", auto: "missing" };
const HOLD_LABEL = {
  cargo: tr("カーゴ"), mining_hold: tr("採掘カーゴ"), drone_bay: tr("ドローンベイ"), pi_hold: tr("PI 資材カーゴ"),
  command_center_hold: tr("指令センターカーゴ"), mineral_hold: tr("鉱物カーゴ"), ice_hold: tr("氷カーゴ"), gas_hold: tr("ガスカーゴ"),
  ammo_hold: tr("弾薬カーゴ"), ship_maintenance_bay: tr("艦船整備ベイ"),
};
const SPECIAL_HOLDS = ["pi_hold", "command_center_hold", "mineral_hold", "ice_hold", "gas_hold", "ammo_hold", "ship_maintenance_bay", "mining_hold"];
const COMBAT = new Set(["drone", "missile", "turret", "bomber", "brawler", "kiter"]);
const TACKLE_LABEL = { point: tr("ディスラプター"), scram: tr("スクランブラー"), web: tr("ウェブ") };

// PvP: 速さ・ワープ妨害の射程
function pvpLine(e) {
  const p = e.pvp;
  if (!p) return "";
  const sp = p.speed;
  const speed = sp ? `🏃 ${fmtNum(Math.round(sp.prop || sp.base))} m/s${sp.prop ? `${tr("（{0}）", sp.prop_kind)}` : ""}` : "";
  const tackle = p.tackle.map((t) => `${TACKLE_LABEL[t.kind]}${t.count > 1 ? ` ×${t.count}` : ""} ${fmtNum(t.range / 1000)}km`).join(DOT_SEP);
  return `<small class="muted">${[speed, tackle && `🎯 ${tackle}`].filter(Boolean).join(" · ")}</small>`;
}

let fitCardCharId = null;   // カードのボタン（スキルプラン）で使うキャラクター。各ページが設定する
const fitsByKey = new Map();

function statLine(e) {
  if (e.role === "tackle") {
    const sp = e.pvp?.speed || {};
    return `<div class="rec-stat"><span class="rec-big">${fmtNum(Math.round(sp.prop || sp.base || 0))}</span> <span class="muted">m/s${sp.prop ? `${tr("（{0} 起動中）", sp.prop_kind)}` : ""}</span>
      <small class="muted">${(e.pvp?.tackle || []).map((t) => `${TACKLE_LABEL[t.kind]} ${fmtNum(t.range / 1000)}km`).join(DOT_SEP)}${e.dps?.total ? ` · DPS ${fmtNum(Math.round(e.dps.total))}` : ""}</small></div>`;
  }
  if (e.role === "logistics") {
    const r = e.pvp?.reps || {};
    const parts = [r.armor && `${tr("装甲 {0}", fmtNum(Math.round(r.armor)))}`, r.shield && `${tr("シールド {0}", fmtNum(Math.round(r.shield)))}`].filter(Boolean);
    return `<div class="rec-stat"><span class="rec-big">${fmtNum(Math.round((r.armor || 0) + (r.shield || 0)))}</span> <span class="muted">${tr("HP/秒（遠隔回復・艦ボーナス前）")}</span>
      <small class="muted">${parts.join(DOT_SEP)}${r.range ? ` ${tr("· 射程 {0}km", fmtNum(r.range / 1000))}` : ""}</small></div>${pvpLine({ pvp: { ...e.pvp, tackle: [] } })}`;
  }
  if (COMBAT.has(e.role) && (e.role === "brawler" || e.role === "kiter")) {
    const d = e.dps;
    return `<div class="rec-stat"><span class="rec-big">${fmtNum(Math.round(d.total))}</span> <span class="muted">${tr("DPS（目安）")}</span></div>${pvpLine(e)}`;
  }
  if (COMBAT.has(e.role)) {
    const d = e.dps;
    const parts = [];
    if (d.turret) parts.push(`${tr("タレット {0}", fmtNum(Math.round(d.turret)))}`);
    if (d.missile) parts.push(`${tr("ミサイル {0}", fmtNum(Math.round(d.missile)))}`);
    if (d.drone) parts.push(`${tr("ドローン {0}", fmtNum(Math.round(d.drone)))}`);
    return `<div class="rec-stat"><span class="rec-big">${fmtNum(Math.round(d.total))}</span> <span class="muted">${tr("DPS（目安）")}</span>
      ${parts.length ? `<small class="muted">${parts.join(DOT_SEP)}</small>` : ""}</div>`;
  }
  if (e.role === "drone_mining") {
    const perSec = e.dps.mining_m3_min / 60;
    return `<div class="rec-stat"><span class="rec-big">${perSec.toLocaleString(LOCALE, { maximumFractionDigits: 2 })}</span> <span class="muted">${tr("m³/秒（採掘量の目安）")}</span>
      <small class="muted">${tr("1 分 {0} m³ · 1 時間 {1} m³", fmtNum(Math.round(e.dps.mining_m3_min)), fmtNum(Math.round(e.dps.mining_m3_min * 60)))}</small></div>`;
  }
  if (e.role === "exploration") {
    const x = e.dps.exploration;
    return `<div class="rec-stat"><span><span class="muted">${tr("ハッキングの強さ")}</span> <b>${fmtNum(x.virus_strength)}</b></span>
      <span><span class="muted">${tr("プローブの強さ")}</span> <b>+${fmtNum(x.probe_bonus)}%</b></span></div>`;
  }
  if (e.role === "salvage") {
    const x = e.dps.salvage;
    return `<div class="rec-stat"><span><span class="muted">${tr("サルベージャー")}</span> <b>${x.salvagers}</b></span>
      <span><span class="muted">${tr("トラクタービーム")}</span> <b>${x.tractors}</b></span>
      <span><span class="muted">${tr("作業時間")}</span> <b>${tr("{0} 秒", fmtNum(x.cycle))}</b></span></div>`;
  }
  const keys = e.role === "hauler" ? ["cargo"] : e.role === "special_hauler" ? SPECIAL_HOLDS : ["mining_hold", "cargo"];
  const holds = `<div class="rec-stat">${keys.filter((k) => e.holds[k]).map((k) =>
    `<span><span class="muted">${HOLD_LABEL[k]}</span> <b>${fmtNum(Math.round(e.holds[k].total))} m³</b></span>`).join(" ")}</div>`;
  return (e.role?.startsWith("mining") ? miningLine(e) : "") + holds;
}

// 採掘モジュールの 1 秒あたりの採掘量と、採掘カーゴが満杯になるまでの時間
const MINING_KIND = { ore: tr("鉱石"), ice: tr("氷"), gas: tr("ガス") };
function miningLine(e) {
  const m = e.dps?.mining;
  if (!m || !m.total) return "";
  const kinds = Object.keys(MINING_KIND).filter((k) => m[k] > 0);
  const hold = e.holds?.mining_hold?.total || e.holds?.ice_hold?.total || e.holds?.gas_hold?.total || 0;
  const full = hold ? ` ${tr("· 採掘カーゴが満杯まで {0}", esc(fmtMinutes(hold / m.total / 60)))}` : "";
  return `<div class="rec-stat"><span class="rec-big">${m.total.toLocaleString(LOCALE, { maximumFractionDigits: 2 })}</span> <span class="muted">${tr("m³/秒（{0}・目安）", kinds.map((k) => MINING_KIND[k]).join(DOT_SEP))}</span>
    <small class="muted">${tr("1 時間 {0} m³{1}", fmtNum(m.per_hour), full)}</small></div>`;
}

function upgradeBlock(e) {
  const u = e.upgrade;
  if (!u) return "";
  const steps = u.steps.map((s) => `<li><span>${esc(s.name)} ${ROMAN[s.level]}</span>
    <span class="muted">+${fmtNum(s.dps_gain)} DPS · ${esc(fmtMinutes(s.minutes))}</span></li>`).join("");
  return `<details class="rec-upgrade"><summary>${tr("⚡ 10 日以内の訓練で DPS {0} → <b>{1}</b>", fmtNum(Math.round(u.dps_before)), fmtNum(Math.round(u.dps_after)))}
    <span class="muted">${tr("（{0}）", esc(fmtMinutes(u.minutes)))}</span></summary>
    <ol>${steps}</ol>
    <button class="btn small" type="button" data-action="plan-upgrade" data-key="${esc(e.key)}">${tr("📋 このスキルのプラン")}</button></details>`;
}

// ---------- 購入費（Jita 4-4 の最安値） ----------
const JITA_ID = 60003760;
const jitaPrices = new Map(); // type_id → 最安の売り値（売り注文が無ければ null）
const jitaBuyPrices = new Map(); // type_id → 最高の買い値（買い注文が無ければ null）

// 部品表を「type_id:個数:種類」の並びで持たせ、あとで価格を埋める
function costLine(e) {
  if (!e.bom?.length) return "";
  const items = e.bom.map(([t, q, k]) => `${t}:${q}:${k}`).join(",");
  const hasBay = e.bom.some(([, , k]) => k === "bay");
  return `<div class="rec-cost" data-bom="${items}" data-has-bay="${hasBay ? 1 : ""}">💰 <span class="muted">${tr("Jita 4-4 の購入費を調べています…")}</span></div>`;
}

async function hydrateJitaCosts(root = document) {
  const els = [...root.querySelectorAll(".rec-cost[data-bom]")];
  if (!els.length) return;
  const parse = (el) => el.dataset.bom.split(",").map((p) => { const [t, q, k] = p.split(":"); return [Number(t), Number(q), k]; });
  const missing = [...new Set(els.flatMap((el) => parse(el).map(([t]) => t)))].filter((t) => !jitaPrices.has(t));
  try {
    for (let i = 0; i < missing.length; i += 100) {
      const chunk = missing.slice(i, i + 100);
      const data = await request("GET", `/api/market/prices?location=${JITA_ID}&type_ids=${chunk.join(",")}`);
      for (const t of chunk) {
        jitaPrices.set(t, data.prices[t]?.sell?.price ?? null);
        jitaBuyPrices.set(t, data.prices[t]?.buy?.price ?? null);
      }
    }
  } catch (err) {
    els.forEach((el) => { el.innerHTML = `💰 <span class="muted">${tr("購入費を取得できませんでした（{0}）", esc(err.message))}</span>`; });
    return;
  }
  const trader = await bestTrader(JITA_ID);
  for (const el of els) {
    let main = 0, all = 0, noStock = 0, orderMain = 0, orderAll = 0, noOrder = 0;
    for (const [t, q, k] of parse(el)) {
      const buy = jitaBuyPrices.get(t);
      if (buy != null && trader) {
        const cost = buy * (1 + trader.broker / 100) * q;
        orderAll += cost;
        if (k !== "bay") orderMain += cost;
      } else noOrder++;
      const price = jitaPrices.get(t);
      if (price == null) { noStock++; continue; }
      all += price * q;
      if (k !== "bay") main += price * q;
    }
    const bay = el.dataset.hasBay ? ` <span class="muted">${tr("（ドローン・カーゴ込み {0} ISK）", fmtIsk(all))}</span>` : "";
    const stock = noStock ? ` <span class="warn-text">${tr("Jita に売り注文の無い品目 {0} 件を除く", noStock)}</span>` : "";
    const order = trader ? `<br><span class="muted">${tr("📉 {0} が買い注文で買う場合（仲介手数料 {1}）: <b title=\"{2}\">{3} ISK</b>{4} {5}", esc(trader.name), fmtPct(trader.broker, 2), esc(fullIsk(orderMain)), fmtIsk(orderMain), (el.dataset.hasBay ? `${tr("（ドローン・カーゴ込み {0}）", fmtIsk(orderAll))}` : ""), (noOrder ? `<span class="warn-text">${tr("買い注文の無い品目 {0} 件を除く", noOrder)}</span>` : ""))}</span>` : "";
    el.innerHTML = `${tr("💰 Jita 4-4: 艦＋装備 <b title=\"{0}\">{1} ISK</b>{2}{3}{4}", esc(fullIsk(main)), fmtIsk(main), bay, stock, order)}`;
  }
}

// soon: まだ使えない（訓練時間とスキルプランを出す）。showRole: 役割も表示する（艦ごとの一覧用）
function fitCard(e, soon, showRole = false) {
  fitsByKey.set(e.key, e);
  const badges = [`<span class="badge ${SOURCE_BADGE[e.source] || "ok"}">${SOURCE_LABEL[e.source] || e.source}</span>`];
  if (showRole && e.role_label) badges.unshift(`<span class="badge queued">${esc(e.role_label)}</span>`);
  if (e.upgrade_of_now) badges.push(`<span class="badge ok">${tr("今のフィットの強化版")}</span>`);
  if (e.wcs) badges.push(`<span class="badge queued">${tr("🛡 WCS 版")}</span>`);
  const approx = e.approximate?.length ? `<small class="muted">${tr("※ PG / CPU は参考値（{0}）", esc(e.approximate.join(LIST_SEP)))}</small>` : "";
  let time = "";
  if (e.impossible) time = `<div class="warn-text small-note">${tr("スキルをすべて V にしても PG / CPU・キャリブレーションが足りません")}</div>`;
  else if (soon) time = `<div class="rec-time">${tr("⏳ 訓練 <b>{0}</b> で使えます", esc(fmtMinutes(e.minutes)))}</div>`;
  else time = `<div class="rec-time ok-text">${tr("✓ 今すぐ使えます")}</div>`;
  const notes = e.dps?.notes?.length && COMBAT.has(e.role) ? `<small class="muted">${esc(e.dps.notes.join(LIST_SEP))}</small>` : "";
  const al = e.align;
  const ws = e.warp_strength;
  const strength = ws ? ws.base + ws.wcs : 0;
  const escape = (n) => (n > 0 ? `${tr("妨害 {0} 点まで逃げられる（ディスラプター 1 点・スクランブラー 2 点）", n)}` : tr("ディスラプター 1 つで止められる"));
  const wsLine = ws && (ws.base > 0 || ws.wcs > 0) ? `<small class="muted">${tr("🛡 ワープコアの強度 {0}{1}: {2}", ws.base, (ws.wcs
    ? ` ${tr("→ スタビライザー起動中 <b>{0}</b>（起動中の 10 秒だけ。再起動まで 150 秒）", strength)}` : ""), escape(strength))}</small>` : "";
  const wcsNote = e.wcs ? `<small class="muted">${tr("🔧 ワープコアスタビライザー版{0}。 装着中はロック距離・スキャン分解能・ドローン帯域が −50%", (e.wcs.removed ? `${tr("（{0} と入れ替え）", esc(e.wcs.removed))}` : tr("（空きスロットに追加）")))}</small>` : "";
  const alignLine = al && al.normal ? `<small class="muted">${tr("⏱ ワープまで {0} 秒{1}", al.normal.toFixed(1), (al.trick != null
    ? (al.effective ? ` · <span class="ok-text">${tr("MWD の小技で約 {0} 秒", al.trick.toFixed(0))}</span>` : tr(" · MWD の小技の効果なし")) : ""))}</small>` : "";
  const swapped = e.prop_swapped ? `<small class="muted">${tr("🔁 MWD の小技でワープが速くならない（{0} 秒 → 小技でも {1} 秒）ので、 {2} を {3} に替えています", e.prop_swapped.normal.toFixed(1), e.prop_swapped.trick.toFixed(0), esc(e.prop_swapped.from), esc(e.prop_swapped.to))}</small>` : "";
  return `<div class="rec-card">
    <div class="rec-head"><div><b>${esc(e.name)}</b><small class="muted">${esc(nm(e, "ship_ja", "ship_en"))}${e.ship_en && e.ship_en !== nm(e, "ship_ja", "ship_en") ? ` · ${esc(e.ship_en)}` : ""}</small></div>
      <div class="rec-badges">${badges.join("")}</div></div>
    ${statLine(e)}${showRole || soon ? time : ""}${costLine(e)}${alignLine}${wsLine}${wcsNote}${swapped}${notes}${approx}
    <div class="fit-actions">
      <button class="btn small" type="button" data-action="copy-fit" data-key="${esc(e.key)}">${tr("📋 EFT をコピー")}</button>
      <button class="btn small" type="button" data-action="edit-fit" data-key="${esc(e.key)}">${tr("✏️ 編集")}</button>
      <button class="btn small" type="button" data-action="compare-fit" data-key="${esc(e.key)}" title="${tr("フィットの比較に追加（最大 3 個）")}">${tr("⚖ 比較")}</button>
      ${e.variant === "t1" ? "" : `<button class="btn small" type="button" data-action="try-t1" data-key="${esc(e.key)}" title="${tr("このキャラクターのスキルが足りない装備を T1 に替えて、フィットの作成ページで開く")}">${tr("🔽 スキル不足を T1 で試す")}</button>`}
      ${soon && !e.impossible ? `<button class="btn small primary" type="button" data-action="plan-fit" data-key="${esc(e.key)}">${tr("📋 スキルプラン")}</button>` : ""}
    </div>
    ${soon ? "" : upgradeBlock(e)}
  </div>`;
}

document.addEventListener("click", async (ev) => {
  const el = ev.target.closest("[data-action='copy-fit'], [data-action='plan-fit'], [data-action='plan-upgrade'], [data-action='edit-fit'], [data-action='try-t1'], [data-action='compare-fit']");
  if (!el) return;
  const e = fitsByKey.get(el.dataset.key);
  if (!e) return;
  try {
    switch (el.dataset.action) {
      case "copy-fit":
        await navigator.clipboard.writeText(e.eft);
        toast(`${tr("「{0}」をコピーしました。ゲームのフィッティング画面で「クリップボードからインポート」してください。", e.name)}`, "ok");
        break;
      case "compare-fit": {
        const list = [...(loadJson("compare:efts", []) || []).filter((x) => x && x.trim() && x !== e.eft), e.eft].slice(-3);
        saveJson("compare:efts", list);
        toast(`${tr("比較に追加しました（{0} / 3）。", list.length)}`, "ok");
        const a = document.createElement("a");
        a.href = "/compare";
        a.textContent = tr("比較を開く →");
        document.querySelector("#toasts .toast:last-child")?.append(" ", a);
        break;
      }
      case "edit-fit":
      case "try-t1":
        saveJson("fitbuilder:eft", e.eft);
        saveJson("fitbuilder:t1", el.dataset.action === "try-t1");
        if (fitCardCharId) saveJson("fitbuilder:character", fitCardCharId);  // 同じキャラクターのスキルで判定する
        location.href = "/fitting";
        break;
      case "plan-fit":
        await openPlanDialog({ types: e.type_ids, skills: e.plan_skills, charId: fitCardCharId, title: e.name });
        break;
      case "plan-upgrade":
        await openPlanDialog({ types: [], skills: e.upgrade.skills, charId: fitCardCharId, title: `${tr("{0} の DPS 強化", e.name)}` });
        break;
    }
  } catch (err) {
    toast(err.message, "error");
  }
});
