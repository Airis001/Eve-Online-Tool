"use strict";
// 生産: ジョブ・製造コスト・採掘の記録

let characters = [];
let groups = [];
let ids = new Set();
let jobs = [];
let costType = null;
let searchTimer = null;
const notified = new Set(loadJson("industry:notified", []));

// ---------- ジョブ ----------

function jobRow(j) {
  const done = j.status === "ready" || (j.status === "active" && new Date(j.end_date) <= Date.now());
  const left = j.status === "active" && !done ? timeLeft(j.end_date) : "";
  const badge = done ? `<span class="badge ok">${tr("✓ 完了")}</span>` : j.status === "active" ? `<span class="badge queued">${esc(left)}</span>`
    : `<span class="badge missing">${esc(j.status_label)}</span>`;
  const pct = j.status === "active" ? Math.min(100, Math.max(0, ((Date.now() - new Date(j.start_date)) / (new Date(j.end_date) - new Date(j.start_date))) * 100)) : 100;
  return `<tr class="${j.status === "delivered" ? "muted-row" : ""}"><td>${badge}<div class="mini-bar"><span style="width:${pct}%"></span></div></td>
    <td><b>${esc(j.activity)}</b><br><small class="muted">${esc(j.character_name)}</small></td>
    <td>${esc(j.product || j.blueprint)}${j.runs > 1 ? ` <span class="muted">×${fmtNum(j.runs)}</span>` : ""}<br><small class="muted">${esc(j.blueprint)}</small></td>
    <td><small>${esc(j.facility || "-")}</small></td><td class="num"><small>${esc(fmtLocal(j.end_date))}</small></td></tr>`;
}

function renderJobs(errRows) {
  const box = $("#jobs");
  const active = jobs.filter((j) => j.status !== "delivered" && j.status !== "cancelled" && j.status !== "reverted");
  const ready = active.filter((j) => j.status === "ready" || new Date(j.end_date) <= Date.now()).length;
  box.innerHTML = `${errRows ?? ""}<p>${tr("{0} 件（完了 <b>{1}</b> 件）", active.length, ready)}</p>
    <div class="table-scroll"><table class="orders"><thead><tr><th>${tr("状態")}</th><th>${tr("作業")}</th><th>${tr("品目")}</th><th>${tr("場所")}</th><th>${tr("終了")}</th></tr></thead>
    <tbody>${jobs.length ? jobs.map(jobRow).join("") : `<tr><td colspan="5" class="muted">${tr("ジョブはありません")}</td></tr>`}</tbody></table></div>`;
}

function checkFinished() {
  for (const j of jobs) {
    if (j.status !== "active" || new Date(j.end_date) > Date.now() || notified.has(j.job_id)) continue;
    notified.add(j.job_id);
    const msg = `${tr("{0}: {1}「{2}」が完了しました", j.character_name, j.activity, j.product || j.blueprint)}`;
    toast(msg, "ok");
    if ("Notification" in window && Notification.permission === "granted") new Notification(tr("EVE ツール"), { body: msg });
  }
  saveJson("industry:notified", [...notified].slice(-500));
}

async function loadJobs(force = false) {
  try {
    const d = await request("GET", `/api/industry/jobs?${idsQuery(ids)}${force ? "&force=1" : ""}`);
    jobs = d.jobs;
    // 読み込んだ時点ですでに終わっているものは通知しない
    jobs.filter((j) => new Date(j.end_date) <= Date.now()).forEach((j) => notified.add(j.job_id));
    renderJobs(charErrors(d.characters));
  } catch (e) {
    $("#jobs").innerHTML = `<div class="warn">${esc(e.message)}</div>`;
  }
}

$("#notify-btn").addEventListener("click", async () => {
  if (!("Notification" in window)) { toast(tr("このブラウザは通知に対応していません。"), "error"); return; }
  const p = await Notification.requestPermission();
  toast(p === "granted" ? tr("このページを開いている間、ジョブの完了を通知します。") : tr("通知が許可されませんでした。"), p === "granted" ? "ok" : "error");
});

setInterval(() => { if (jobs.length) { checkFinished(); renderJobs(); } }, 30000);

// ---------- 製造コスト ----------

async function runSearch() {
  const q = $("#bp-search").value.trim();
  const list = $("#bp-results");
  if (!q) { list.hidden = true; return; }
  try {
    const d = await request("GET", `/api/industry/search?q=${encodeURIComponent(q)}`);
    list.innerHTML = d.results.length ? d.results.map((r) => `<li data-id="${r.id}"><span class="names"><b>${esc(nm(r))}</b><small>${nmSub(r, " · ")}${esc(r.group)}</small></span></li>`).join("")
      : `<li class="empty">${tr("設計図のある品目が見つかりません")}</li>`;
    list.hidden = false;
  } catch (e) {
    toast(e.message, "error");
  }
}

async function loadCost(typeId = costType) {
  if (!typeId) return;
  costType = typeId;
  const box = $("#cost");
  box.innerHTML = `<p class="muted">${tr("計算しています…")}</p>`;
  const p = new URLSearchParams({
    type_id: typeId, runs: $("#f-runs").value, me: $("#f-me").value, te: $("#f-te").value, system: $("#f-system").value,
    facility_tax: $("#f-tax").value, material_bonus: $("#f-bonus").value, character_id: $("#f-char").value,
  });
  let d;
  try {
    d = await request("GET", `/api/industry/cost?${p}`);
  } catch (e) {
    box.innerHTML = `<div class="warn">${esc(e.message)}</div>`;
    return;
  }
  const rows = d.materials.map((m) => `<tr><td>${esc(nm(m))}${m.buildable ? ` <button class="link" type="button" data-cost="${m.type_id}">${tr("🧮 これも計算")}</button>` : ""}</td>
    <td class="r num">${fmtNum(m.quantity)}</td><td class="r num">${m.sell != null ? fmtIsk(m.sell) : `<span class="warn-text">${tr("なし")}</span>`}</td>
    <td class="r num">${fmtIsk((m.sell || 0) * m.quantity)}</td><td class="r num muted">${fmtIsk((m.buy || 0) * m.quantity)}</td></tr>`).join("");
  const total = d.materials_sell + d.job_cost;
  const revenue = (d.product.sell || 0) * d.product.units;
  const profit = revenue - total;
  const buyInstead = d.product.sell != null ? (total / d.product.units < d.product.sell
    ? `<span class="badge ok">${tr("作る方が安い")}</span>` : `<span class="badge missing">${tr("買う方が安い")}</span>`) : "";
  box.innerHTML = `<div class="preview-head"><div><h3>${esc(nm(d.product))} ×${fmtNum(d.product.units)}</h3>
      <small class="muted">${tr("{0}（{1}）", esc(d.blueprint), (d.activity === "reaction" ? tr("リアクション") : `${tr("製造・ME {0} / TE {1}", d.me, d.te)}`))}</small></div>${buyInstead}</div>
    <div class="stat-row">
      <div class="stat-card"><small class="muted">${tr("材料費（Jita 売値）")}</small><b>${fmtIsk(d.materials_sell)} ISK</b><small class="muted">${tr("買い注文で揃えると {0}", fmtIsk(d.materials_buy))}</small></div>
      <div class="stat-card"><small class="muted">${tr("生産の手数料")}</small><b>${fmtIsk(d.job_cost)} ISK</b>
        <small class="muted">${tr("{0} + 税 {1} + SCC 4%", (d.system ? `${tr("{0} 指数 {1}", esc(d.system), fmtPct((d.cost_index || 0) * 100, 2))}` : tr("星系が不明（指数 0 で計算）")), fmtPct(d.facility_tax, 2))}</small></div>
      <div class="stat-card"><small class="muted">${tr("1 個あたりの原価")}</small><b>${fmtIsk(d.cost_per_unit)} ISK</b>
        <small class="muted">${tr("Jita 売値 {0} · 買値 {1}", d.product.sell != null ? fmtIsk(d.product.sell) : "-", d.product.buy != null ? fmtIsk(d.product.buy) : "-")}</small></div>
      <div class="stat-card total"><small class="muted">${tr("利益（Jita 売値で売った場合・税の前）")}</small><b>${d.product.sell != null ? signedIsk(profit) : "-"}</b>
        <small class="muted">${tr("作業時間 {0}{1}", esc(fmtMinutes(d.seconds / 60)), d.skills_used ? "" : tr("（スキルなし）"))}</small></div>
    </div>
    ${d.missing_prices ? `<p class="warn-text small-note">${tr("Jita に売り注文の無い材料が {0} 件あります（金額に含まれていません）。", d.missing_prices)}</p>` : ""}
    <div class="table-scroll"><table class="orders"><thead><tr><th>${tr("材料")}</th><th class="r">${tr("数量")}</th><th class="r">${tr("Jita 売値")}</th><th class="r">${tr("金額")}</th><th class="r">${tr("買い注文なら")}</th></tr></thead>
      <tbody>${rows}</tbody></table></div>`;
}

const signedIsk = (n) => `<span class="${n >= 0 ? "ok-text" : "warn-text"}">${n >= 0 ? "+" : ""}${fmtIsk(n)} ISK</span>`;

async function loadBlueprints() {
  const box = $("#bps");
  box.innerHTML = `<p class="muted">${tr("読み込み中…")}</p>`;
  try {
    const d = await request("GET", `/api/industry/blueprints?${idsQuery(ids)}`);
    box.innerHTML = charErrors(d.characters) + (d.blueprints.length ? `<div class="table-scroll"><table class="orders"><thead><tr><th>${tr("設計図")}</th><th>${tr("種類")}</th>
      <th class="r">ME / TE</th><th>${tr("キャラクター・場所")}</th><th></th></tr></thead><tbody>${d.blueprints.map((b) => `<tr>
      <td><b>${esc(b.product)}</b><br><small class="muted">${esc(nm(b))}</small></td>
      <td>${b.kind}${b.kind === "BPC" ? ` <small class="muted">${tr("残り {0} 回", fmtNum(b.runs))}</small>` : ""}</td>
      <td class="r num">${b.material_efficiency} / ${b.time_efficiency}</td>
      <td><small>${esc(b.character_name)}<br><span class="muted">${esc(b.location || tr("コンテナの中など"))}</span></small></td>
      <td><button class="btn small" type="button" data-bp="${b.type_id}" data-me="${b.material_efficiency}" data-te="${b.time_efficiency}">${tr("🧮 計算")}</button></td></tr>`).join("")}</tbody></table></div>`
      : `<p class="muted">${tr("製造・リアクションの設計図がありません。")}</p>`);
  } catch (e) {
    box.innerHTML = `<div class="warn">${esc(e.message)}</div>`;
  }
}

$("#bp-search").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(runSearch, 200); });
document.addEventListener("click", (ev) => {
  const li = ev.target.closest("#bp-results li[data-id]");
  if (li) { $("#bp-results").hidden = true; $("#bp-search").value = ""; loadCost(Number(li.dataset.id)); return; }
  if (!ev.target.closest(".search-wrap")) $("#bp-results").hidden = true;
  const c = ev.target.closest("[data-cost]");
  if (c) { loadCost(Number(c.dataset.cost)); return; }
  const b = ev.target.closest("[data-bp]");
  if (b) {
    $("#f-me").value = b.dataset.me;
    $("#f-te").value = b.dataset.te;
    loadCost(Number(b.dataset.bp));
    $("#cost").scrollIntoView({ behavior: "smooth", block: "start" });
  }
});
document.querySelector(".ind-form").addEventListener("change", () => loadCost());
document.querySelector(".my-bps").addEventListener("toggle", (ev) => { if (ev.target.open) loadBlueprints(); });

// ---------- トレード × 生産の損益 ----------

let tbType = null;
let tbTimer = null;
const VERDICT = {
  profit: `<span class="badge ok">${tr("✓ 利益が出る")}</span>`,
  stock_only: `<span class="badge queued">${tr("△ 在庫を使えば現金は黒字")}</span>`,
  loss: `<span class="badge missing">${tr("✕ 赤字")}</span>`,
  no_price: `<span class="badge missing">${tr("価格なし")}</span>`,
};

function tbDetail(r) {
  const rows = r.materials.map((m) => `<tr><td>${esc(nm(m))}</td><td class="r num">${fmtNum(m.need)}</td>
    <td class="r num ${m.have ? "ok-text" : "muted"}">${fmtNum(m.have)}</td><td class="r num">${fmtNum(m.buy)}</td>
    <td class="r num">${m.unit != null ? fmtIsk(m.unit) : (m.buy ? `<span class="warn-text">${tr("なし")}</span>` : "-")}</td>
    <td class="r num">${fmtIsk(m.cost)}</td><td class="r num muted">${m.have ? fmtIsk(m.inventory_value) : "-"}</td></tr>`).join("");
  const skills = r.missing_skills.length ? `<p class="warn-text small-note">${tr("生産キャラクターのスキルが足りません: {0}", r.missing_skills.map((s) => `${tr("{0} {1}（今 {2}）", esc(s.name), ROMAN[s.level], ROMAN[s.have])}`).join(LIST_SEP))}</p>` : "";
  return `${skills}<div class="stat-row">
      <div class="stat-card"><small class="muted">${tr("売上（手数料・税の後）")}</small><b>${fmtIsk(r.revenue)}</b><small class="muted">${tr("{0} 個 × {1}", fmtNum(r.units), r.net_unit != null ? fmtIsk(r.net_unit) : "-")}</small></div>
      <div class="stat-card"><small class="muted">${tr("材料の購入")}</small><b>${fmtIsk(r.purchase)}</b></div>
      <div class="stat-card"><small class="muted">${tr("生産の手数料")}</small><b>${fmtIsk(r.job_cost)}</b></div>
      <div class="stat-card"><small class="muted">${tr("現金の利益（在庫は無料とみなす）")}</small><b>${signedIsk(r.cash_profit)}</b></div>
      <div class="stat-card total"><small class="muted">${tr("在庫の価値も含めた利益")}</small><b>${signedIsk(r.full_profit)}</b>
        <small class="muted">${tr("使う在庫の価値 {0}", fmtIsk(r.inventory_value))}</small></div></div>
    <div class="table-scroll"><table class="orders"><thead><tr><th>${tr("材料")}</th><th class="r">${tr("必要")}</th><th class="r">${tr("コーポの在庫")}</th><th class="r">${tr("買う数")}</th>
      <th class="r">${tr("単価")}</th><th class="r">${tr("購入額")}</th><th class="r">${tr("在庫の価値")}</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

async function runTradeBuild() {
  const box = $("#tb-out");
  box.innerHTML = `<p class="muted">${tr("計算しています…（設計図が多いと、価格の取得に 1 分ほどかかることがあります）")}</p>`;
  const p = new URLSearchParams({
    trader_id: $("#tb-trader").value, maker_id: $("#tb-maker").value, buy_mode: $("#tb-buy").value, sell_mode: $("#tb-sell").value,
    system: $("#tb-system").value, facility_tax: $("#tb-tax").value, use_corp: $("#tb-corp").checked ? "1" : "0",
    corp_bps: $("#tb-corpbp").checked ? "1" : "0", me: $("#tb-me").value, te: $("#tb-te").value,
  });
  if ($("#tb-runs").value) p.set("runs", $("#tb-runs").value);
  if ($("#tb-location").value) p.set("location", $("#tb-location").value);
  if (tbType) p.set("type_id", tbType);
  let d;
  try {
    d = await request("GET", `/api/industry/trade-build?${p}`);
  } catch (e) {
    box.innerHTML = `<div class="warn">${esc(e.message)}</div>`;
    return;
  }
  const loc = $("#tb-location").value;
  $("#tb-location").innerHTML = `<option value="">${tr("すべての場所")}</option>` + d.locations.map((l) => `<option value="${l.id}">${tr("{0}（{1}）", esc(l.name), fmtNum(l.count))}</option>`).join("");
  $("#tb-location").value = loc;
  const t = d.trader;
  const profits = d.results.filter((r) => r.verdict === "profit").length;
  const rows = d.results.map((r, i) => `<tr><td>${VERDICT[r.verdict]}${r.missing_skills.length ? `<br><small class="warn-text">${tr("スキル不足")}</small>` : ""}</td>
    <td><b>${esc(nm(r))}</b> ×${fmtNum(r.units)} ${r.bp_source === "character" ? "" : r.owned ? `<span class="badge queued">${tr("コーポ")}</span>` : ""}
      <br><small class="muted">${r.owned ? `${tr("{0}・ME {1} / TE {2}{3}・{4} 回", r.kind, r.me, r.te, r.me_known ? "" : tr("（不明なので仮定）"), r.runs)}` : `${tr("設計図なし（ME {0} / TE {1} と仮定）・{2} 回", r.me, r.te, r.runs)}`}</small></td>
    <td class="r num">${signedIsk(r.full_profit)}<br><small class="muted">${tr("現金 {0}", fmtIsk(r.cash_profit))}</small></td>
    <td class="r num">${r.margin != null ? fmtPct(r.margin, 1) : "-"}</td>
    <td class="r num">${r.profit_per_hour != null ? fmtIsk(r.profit_per_hour) : "-"}<br><small class="muted">${esc(fmtMinutes(r.seconds / 60))}</small></td>
    <td class="r num ${r.daily_volume != null && r.daily_volume < r.units / 7 ? "warn-text" : ""}">${r.daily_volume != null ? fmtNum(Math.round(r.daily_volume)) : "-"}</td>
    <td class="r num">${fmtIsk(r.inventory_value)}</td></tr>
    <tr class="tb-detail-row"><td colspan="7"><details><summary>${tr("内訳")}</summary>${tbDetail(r)}</details></td></tr>`).join("");
  box.innerHTML = `<div class="stat-row">
      <div class="stat-card"><small class="muted">${tr("トレード: {0}", esc(t.name))}</small><b>${tr("税 {0} · 仲介 {1}", fmtPct(t.tax, 2), fmtPct(t.broker, 2))}</b>
        <small class="muted">${tr("Accounting {0}・Broker Relations {1}{2}", ROMAN[t.accounting], ROMAN[t.broker_relations], (t.standing_reduction ? `${tr("・スタンディング −{0}", fmtPct(t.standing_reduction, 2))}` : ""))}</small></div>
      <div class="stat-card"><small class="muted">${tr("生産: {0}", esc(d.maker.name))}</small><b>${tr("Industry {0}・Advanced {1}", ROMAN[d.maker.industry], ROMAN[d.maker.advanced_industry])}</b>
        <small class="muted">${d.system ? `${tr("{0} 製造指数 {1}", esc(d.system), fmtPct((d.cost_indices.manufacturing || 0) * 100, 2))}` : tr("星系が不明（指数 0）")}</small></div>
      <div class="stat-card total"><small class="muted">${tr("判定")}</small><b>${tr("{0} 件中 {1} 件で利益", d.results.length, profits)}</b>
        <small class="muted">${d.use_corp ? (d.stock_note ? esc(d.stock_note) : `${tr("コーポの在庫 {0} 種類を差し引き", fmtNum(d.stock_types))}`) : tr("コーポの資産は使わない")}</small></div></div>
    ${t.note ? `<p class="muted small-note">${esc(t.note)}</p>` : ""}
    <p class="muted small-note">${tr("コーポの設計図: {0}", (d.corp_bp_note ? esc(d.corp_bp_note) : `${tr("{0} 種類", fmtNum(d.corp_bp_count))}`))}</p>
    <div class="table-scroll"><table class="orders tb-table"><thead><tr><th>${tr("判定")}</th><th>${tr("製品")}</th><th class="r">${tr("利益")}<br><small>${tr("在庫の価値込み")}</small></th><th class="r">${tr("利益率")}</th>
      <th class="r">${tr("1 時間あたり")}<br><small>${tr("作業時間")}</small></th><th class="r">${tr("1 日の取引量")}<br><small>${tr("Jita 7 日平均")}</small></th><th class="r">${tr("使う在庫")}</th></tr></thead>
      <tbody>${rows || `<tr><td colspan="7" class="muted">${tr("結果がありません")}</td></tr>`}</tbody></table></div>
    <p class="muted small-note">${tr("「利益」は、コーポの在庫を使う分も「今すぐ買い注文に売った額」として費用に含めたものです（在庫をそのまま売るより得か）。 「現金」は在庫を無料とみなした、実際に出ていくお金との差です。1 日の取引量が作る数に比べて少ない（赤字）ものは、売り切るのに時間がかかります。 複数の製品を調べるときは、それぞれがコーポの在庫を全部使える前提です。")}</p>`;
}

$("#tb-search").addEventListener("input", () => {
  clearTimeout(tbTimer);
  tbTimer = setTimeout(async () => {
    const q = $("#tb-search").value.trim();
    const list = $("#tb-results");
    if (!q) { list.hidden = true; return; }
    try {
      const d = await request("GET", `/api/industry/search?q=${encodeURIComponent(q)}`);
      list.innerHTML = d.results.length ? d.results.map((r) => `<li data-tb="${r.id}" data-name="${esc(nm(r))}"><span class="names"><b>${esc(nm(r))}</b><small>${nmSub(r)}</small></span></li>`).join("")
        : `<li class="empty">${tr("設計図のある品目が見つかりません")}</li>`;
      list.hidden = false;
    } catch (e) {
      toast(e.message, "error");
    }
  }, 200);
});

document.addEventListener("click", (ev) => {
  const li = ev.target.closest("#tb-results li[data-tb]");
  if (li) {
    tbType = Number(li.dataset.tb);
    $("#tb-results").hidden = true;
    $("#tb-search").value = "";
    $("#tb-item").innerHTML = `${tr("品目: <b>{0}</b>", esc(li.dataset.name))} <button class="link" type="button" id="tb-clear">${tr("設計図すべてに戻す")}</button>`;
    return;
  }
  if (ev.target.id === "tb-clear") {
    tbType = null;
    $("#tb-item").textContent = tr("品目: 生産キャラクター・コーポの設計図すべて");
  }
  if (!ev.target.closest("#tb-search")) $("#tb-results").hidden = true;
});
$("#tb-run").addEventListener("click", runTradeBuild);

function fillTradeBuildChars() {
  const ready = characters.filter((c) => !c.missing);
  const trade = [...ready].sort((a, b) => (b.trade_skills.accounting + b.trade_skills.broker_relations) - (a.trade_skills.accounting + a.trade_skills.broker_relations));
  const make = [...ready].sort((a, b) => (b.industry_skills?.industry || 0) + (b.industry_skills?.advanced_industry || 0) - (a.industry_skills?.industry || 0) - (a.industry_skills?.advanced_industry || 0));
  $("#tb-trader").innerHTML = trade.map((c) => `<option value="${c.character_id}">${tr("{0}（Accounting {1}・Broker {2}）", esc(c.character_name), ROMAN[c.trade_skills.accounting], ROMAN[c.trade_skills.broker_relations])}</option>`).join("");
  $("#tb-maker").innerHTML = make.map((c) => `<option value="${c.character_id}">${tr("{0}（Industry {1}・Advanced {2}）", esc(c.character_name), ROMAN[c.industry_skills?.industry || 0], ROMAN[c.industry_skills?.advanced_industry || 0])}</option>`).join("");
}

// ---------- 採掘 ----------

async function loadMining() {
  const box = $("#mining");
  box.innerHTML = `<p class="muted">${tr("読み込み中…")}</p>`;
  try {
    const d = await request("GET", `/api/industry/mining?${idsQuery(ids)}`);
    const total = d.by_type.reduce((s, t) => s + t.value, 0);
    const qty = d.by_type.reduce((s, t) => s + t.quantity, 0);
    box.innerHTML = charErrors(d.characters) + (d.entries.length ? `
      <div class="stat-row"><div class="stat-card total"><small class="muted">${tr("合計（{0} 日）", d.days)}</small><b>${fmtIsk(total)} ISK</b><small class="muted">${tr("{0} 個", fmtNum(qty))}</small></div>
        ${d.by_character.map((c) => `<div class="stat-card"><small class="muted">${esc(c.character_name)}</small><b>${fmtIsk(c.value)} ISK</b><small class="muted">${tr("{0} 個", fmtNum(c.quantity))}</small></div>`).join("")}</div>
      <div class="card"><h3>${tr("日ごとの採掘額")}</h3>${svgChart(d.by_day.map((x) => ({ x: x.date.slice(5), y: x.value })), { kind: "bar" })}</div>
      <div class="table-scroll"><table class="orders"><thead><tr><th>${tr("鉱石・資源")}</th><th class="r">${tr("数量")}</th><th class="r">${tr("Jita 買値")}</th><th class="r">${tr("金額")}</th></tr></thead>
        <tbody>${d.by_type.map((t) => `<tr><td>${esc(nm(t))}</td><td class="r num">${fmtNum(t.quantity)}</td><td class="r num">${t.buy != null ? fmtIsk(t.buy) : "-"}</td><td class="r num">${fmtIsk(t.value)}</td></tr>`).join("")}</tbody></table></div>`
      : `<p class="muted">${tr("30 日以内の採掘の記録はありません。")}</p>`);
  } catch (e) {
    box.innerHTML = `<div class="warn">${esc(e.message)}</div>`;
  }
}

function loadAll(force = false) {
  loadJobs(force);
  loadMining();
  if (document.querySelector(".my-bps").open) loadBlueprints();
}

$("#reload").addEventListener("click", () => loadAll(true));

(async () => {
  try {
    const d = await request("GET", "/api/characters");
    characters = d.characters;
    groups = d.groups;
    $("#f-char").innerHTML = characters.filter((c) => !c.missing).map((c) => `<option value="${c.character_id}">${esc(c.character_name)}</option>`).join("");
    fillTradeBuildChars();
    ids = renderCharFilter($("#char-filter"), characters, groups, (next) => { ids = next; loadAll(); });
    loadAll();
    const typeId = new URLSearchParams(location.search).get("type_id");
    if (typeId) loadCost(Number(typeId));
  } catch (e) {
    toast(e.message, "error");
  }
})();
