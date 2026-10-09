"use strict";
// PI: コロニーの一覧と、余り・不足をなくすための提案

let characters = [];
let groups = [];
let ids = new Set();
const PLANET_JA = { barren: tr("荒地"), gas: tr("ガス"), ice: tr("アイス"), lava: tr("溶岩"), oceanic: tr("海洋"), plasma: tr("プラズマ"), storm: tr("嵐"), temperate: tr("温暖") };
const TIER = ["P0", "P1", "P2", "P3", "P4"];
const HOME_KEY = "pi:home-system";

const perDay = (n) => `${fmtNum(Math.round(n))} <small class="muted">${tr("/日")}</small>`;
const planetKind = (k) => PLANET_JA[k] || k || "?";

// ---------- 抽出機の配置図 ----------

let layouts = [];

// ECU を中心にしたヘッドの位置（緯度経度 → 平面）。上が北
function layoutPoints(rec) {
  const [lat0, lon0] = rec.ecu;
  const colat = [lat0, ...rec.heads.map((h) => h[0])].some((v) => v > Math.PI / 2 + 0.01); // 0〜π の余緯度か
  const k = colat ? Math.sin(lat0) : Math.cos(lat0);
  const pts = rec.heads.map(([lat, lon]) => {
    let dl = lon - lon0;
    if (dl > Math.PI) dl -= 2 * Math.PI;
    if (dl < -Math.PI) dl += 2 * Math.PI;
    return { x: dl * k, y: colat ? lat - lat0 : lat0 - lat };
  });
  return pts;
}

function layoutStats(rec) {
  const pts = layoutPoints(rec);
  const r = rec.head_radius || 0;
  const dist = pts.map((p) => Math.hypot(p.x, p.y));
  let minGap = Infinity;
  pts.forEach((a, i) => pts.slice(i + 1).forEach((b) => { minGap = Math.min(minGap, Math.hypot(a.x - b.x, a.y - b.y)); }));
  return { avg: dist.reduce((s, d) => s + d, 0) / (dist.length || 1), minGap, r };
}

function layoutMap(rec, size = 150) {
  const pts = layoutPoints(rec);
  const r = rec.head_radius || 0;
  const extent = Math.max(...pts.map((p) => Math.max(Math.abs(p.x), Math.abs(p.y)) + r), r * 2, 1e-6) * 1.1;
  const s = size / 2 / extent;
  const c = size / 2;
  const circles = pts.map((p, i) => `<circle cx="${c + p.x * s}" cy="${c + p.y * s}" r="${Math.max(r * s, 1)}" class="head-area"/>
    <circle cx="${c + p.x * s}" cy="${c + p.y * s}" r="3" class="head"><title>${tr("ヘッド {0}", i + 1)}</title></circle>`).join("");
  return `<svg class="layout-map" viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" role="img">
    <line x1="${c}" y1="4" x2="${c}" y2="${size - 4}" class="axis"/><line x1="4" y1="${c}" x2="${size - 4}" y2="${c}" class="axis"/>
    ${circles}<rect x="${c - 4}" y="${c - 4}" width="8" height="8" class="ecu"><title>ECU</title></rect>
    <text x="${c + 3}" y="11" class="north">N</text></svg>`;
}

function layoutSummary(rec) {
  const st = layoutStats(rec);
  const ratio = st.r ? ` ${tr("· ECU からの距離は採掘範囲の平均 {0} 倍 · ヘッドの間隔は最小 {1} 倍", (st.avg / st.r).toFixed(1), (st.minGap / st.r).toFixed(1))}` : "";
  return `<small class="muted">${tr("{0} · {1}（{2}）· ヘッド {3} 本 · {4}/日（1 本 {5}）{6} · 設置 {7}", esc(rec.character_name), esc(rec.planet_name || ""), esc(planetKind(rec.planet_type)), rec.heads.length, fmtNum(Math.round(rec.per_day)), fmtNum(Math.round(rec.per_head_day)), ratio, esc(fmtLocal(rec.install_time)))}</small>`;
}

// 作り直す惑星・資源に一番近い記録（同じ惑星 → 同じ種類の惑星の順。ヘッド 1 本あたりの抽出量が多いもの）
function bestLayout(planetId, planetKindName, resource) {
  const same = layouts.filter((l) => l.resource === resource && l.planet_id === planetId);
  if (same.length) return { rec: same[0], exact: true };
  const kind = layouts.filter((l) => l.resource === resource && l.planet_type === planetKindName);
  return kind.length ? { rec: kind[0], exact: false } : null;
}

async function loadLayouts() {
  const box = $("#layouts");
  try {
    ({ layouts } = await request("GET", "/api/pi/layouts"));
  } catch (e) {
    box.innerHTML = `<div class="warn">${esc(e.message)}</div>`;
    return;
  }
  if (!layouts.length) {
    box.innerHTML = `<p class="muted">${tr("まだ記録がありません（PI の権限でコロニーを読み込むと記録されます）。")}</p>`;
    return;
  }
  const byRes = {};
  layouts.forEach((l) => { (byRes[nm(l, "resource_ja", "resource_en")] ||= []).push(l); });
  box.innerHTML = `<div class="layout-grid">${Object.entries(byRes).map(([res, list]) => `<div class="card">
    <h3>${esc(res)} <small class="muted">${tr("{0} 件の記録", list.length)}</small></h3>
    ${list.slice(0, 3).map((l, i) => `<div class="layout-rec">${layoutMap(l, 120)}<div><b>${tr("{0}{1}/日・本", i === 0 ? "🥇 " : "", fmtNum(Math.round(l.per_head_day)))}</b><br>${layoutSummary(l)}</div></div>`).join("")}
    ${list.length > 3 ? `<small class="muted">${tr("ほか {0} 件", list.length - 3)}</small>` : ""}</div>`).join("")}</div>`;
}

// ---------- コロニー ----------

function extractorBadge(ex) {
  if (!ex.active) return `<span class="badge missing">${tr("停止中")}</span>`;
  if (ex.hours_left < 24) return `<span class="badge queued">${tr("あと {0}", esc(fmtMinutes(ex.hours_left * 60)))}</span>`;
  return `<span class="badge ok">${tr("あと {0}", esc(fmtMinutes(ex.hours_left * 60)))}</span>`;
}

function colonyCard(c) {
  const ex = c.extractors.map((e) => `<li>⛏ ${esc(nm(e))} ${perDay(e.per_day)} ${extractorBadge(e)}
    ${e.head_positions?.length && e.ecu?.[0] != null ? `<details class="mini-details"><summary>${tr("配置図（ヘッド {0} 本）", e.heads)}</summary>
      ${layoutMap({ ecu: e.ecu, heads: e.head_positions, head_radius: e.head_radius }, 120)}</details>` : ""}</li>`).join("");
  const fac = c.factory_list.map((f) => `<li>🏭 ${TIER[f.tier]} ${esc(nm(f))} ×${f.count}</li>`).join("");
  const warn = c.extractors.some((e) => !e.active) ? " warn-border" : "";
  return `<div class="pi-colony${warn}"><div><b>${esc(c.planet_name)}</b> <span class="badge queued">${esc(planetKind(c.planet_type))}</span>
    <small class="muted">${tr("CC Lv{0} · {1} 設備", c.upgrade_level, c.num_pins)}</small></div>
    <ul class="pi-list">${ex}${fac || (ex ? "" : `<li class="muted">${tr("設備なし")}</li>`)}</ul></div>`;
}

async function loadColonies() {
  const box = $("#colonies");
  box.innerHTML = `<p class="muted">${tr("読み込み中…")}</p>`;
  try {
    const d = await request("GET", `/api/pi/colonies?${idsQuery(ids)}`);
    loadLayouts();
    box.innerHTML = charErrors(d.characters) + d.characters.filter((r) => r.data).map((r) => {
      const cols = r.data.colonies;
      const stopped = cols.flatMap((c) => c.extractors).filter((e) => !e.active).length;
      return `<div class="card pi-char"><div class="section-head"><h3>${esc(r.character_name)}</h3>
        <span><span class="badge ${cols.length < r.data.max_planets ? "queued" : "ok"}">${tr("コロニー {0} / {1}", cols.length, r.data.max_planets)}</span>
        ${stopped ? ` <span class="badge missing">${tr("抽出機の停止 {0}", stopped)}</span>` : ""}</span></div>
        ${cols.length ? `<div class="pi-colonies">${cols.map(colonyCard).join("")}</div>` : `<p class="muted">${tr("コロニーがありません。")}</p>`}</div>`;
    }).join("");
  } catch (e) {
    box.innerHTML = `<div class="warn">${esc(e.message)}</div>`;
  }
}

// ---------- 提案 ----------

function actionLine(a) {
  switch (a.kind) {
    case "new":
      return a.planet
        ? `${tr("🆕 <b>{0}</b>: <b>{1}</b>（{2}）に新しいコロニー → <b>{3}</b> を採掘", esc(a.character_name), esc(a.planet.name), esc(planetKind(a.planet.kind)), esc(nm(a)))}`
        : `${tr("🆕 <b>{0}</b>: 空き枠で <b>{1}</b> を採掘{2}", esc(a.character_name), esc(nm(a)), (a.no_planet ? `${tr("（")}<span class="warn-text">${tr("拠点の星系に {0} の採れる惑星がありません", esc(nm(a)))}</span>${tr("）")}` : ""))}`;
    case "convert":
      return `${tr("🔄 <b>{0}</b>: <b>{1}</b> の <b>{2}</b>（余っている）の抽出を <b>{3}</b> に切り替え {4}", esc(a.character_name), esc(a.planet.name), esc(nm(a, "from_ja", "from_en")), esc(nm(a)), (a.same_planet ? "" : `<span class="warn-text">${tr("（この惑星では {0} が採れないので、採れる惑星にコロニーを移す）", esc(nm(a)))}</span>`))}`;
    case "adjust":
      return `${tr("🔧 <b>{0}</b> を少し増やす（抽出惑星 {1} 個分）: 今の抽出機のヘッドを増やす・プログラムを短くするなどで対応", esc(nm(a)), a.planets.toFixed(2))}`;
    default:
      return `${tr("⚠ <b>{0}</b> の抽出を増やす枠がありません（Interplanetary Consolidation を上げるか、キャラクターを増やす）", esc(nm(a)))}`;
  }
}

function planCard(p, values) {
  const v = values.find((x) => x.type_id === p.type_id);
  const gainIsk = v?.sell ? ` <span class="muted">${tr("（+{0} ISK/日）", fmtIsk(p.gain_per_day * v.sell))}</span>` : "";
  const steps = [];
  if (p.use_surplus.length) steps.push(`<li>${tr("♻ 余っている材料を回す: {0}", p.use_surplus.map((s) => `<b>${esc(nm(s))}</b> ${perDay(s.amount)}`).join(LIST_SEP))}</li>`);
  if (p.idle.length) steps.push(`<li>${tr("🏭 今ある工場の空きを使う: {0}（材料が届けば動きます）", p.idle.map((s) => `${esc(nm(s))} +${perDay(s.amount)}`).join(LIST_SEP))}</li>`);
  if (p.new_factories.length) steps.push(`<li>${tr("🏗 工場を追加: {0}", p.new_factories.map((f) => `${TIER[f.tier]} ${esc(nm(f))} <b>${tr("{0} 台", Math.ceil(f.count - 1e-9))}</b> <small class="muted">(${f.count.toFixed(2)})</small>`).join(LIST_SEP))}</li>`);
  if (p.extract.length) steps.push(`<li>${tr("⛏ 抽出を増やす: {0}", p.extract.map((e) => `<b>${esc(nm(e))}</b> ${perDay(e.amount)} <small class="muted">${tr("（抽出惑星 約 {0} 個分）", e.planets.toFixed(2))}</small>`).join(LIST_SEP))}</li>`);
  return `<div class="card pi-plan"><div class="section-head"><h3>${TIER[p.tier]} ${esc(nm(p))} <small class="muted">${tr("工場 {0} 台", p.count)}</small></h3>
      <span>${tr("稼働率 <b class=\"{0}\">{1}</b> → 満稼働で <b>+{2}</b>/日{3}", p.utilization < 0.5 ? "warn-text" : "", fmtPct(p.utilization * 100, 0), fmtNum(Math.round(p.gain_per_day)), gainIsk)}</span></div>
    <small class="muted">${tr("足りない材料: {0}", p.short.map((s) => `${tr("{0} {1}/日", esc(nm(s)), fmtNum(Math.round(s.amount)))}`).join(LIST_SEP))}</small>
    <ol class="pi-steps">${steps.join("")}</ol>
    ${p.actions.length ? `<div class="pi-actions"><b>${tr("割り当て")}</b><ul>${p.actions.map((a) => `<li>${actionLine(a)}</li>`).join("")}</ul></div>` : ""}</div>`;
}

function flowTable(items) {
  const rows = items.filter((i) => i.supply > 0 || i.demand > 0).map((i) => {
    const surplus = i.surplus > 0.5 ? `<span class="warn-text">+${fmtNum(Math.round(i.surplus))}</span>` : "";
    const short = i.shortage > 0.5 ? `<span class="warn-text">−${fmtNum(Math.round(i.shortage))}</span>` : "";
    const end = i.demand === 0 && i.tier > 0;
    return `<tr><td><span class="badge queued">${TIER[i.tier]}</span> ${esc(nm(i))}${end ? ` <span class="badge ok">${tr("製品")}</span>` : ""}</td>
      <td class="r num">${fmtNum(Math.round(i.supply))}</td><td class="r num">${end ? "-" : fmtNum(Math.round(i.used))}</td>
      <td class="r num">${end ? "-" : fmtNum(Math.round(i.demand))}</td><td class="r num">${end ? "" : surplus}</td><td class="r num">${short}</td></tr>`;
  }).join("");
  return `<details class="card"><summary>${tr("品目ごとの 1 日の生産・消費")}</summary><div class="table-scroll"><table class="orders"><thead><tr><th>${tr("品目")}</th><th class="r">${tr("生産量")}</th><th class="r">${tr("使用量")}</th>
    <th class="r">${tr("満稼働に必要")}</th><th class="r">${tr("余り")}</th><th class="r">${tr("不足")}</th></tr></thead><tbody>${rows}</tbody></table></div></details>`;
}

function homeTable(home, free) {
  if (!home) return "";
  const slots = free.map((f) => `<span class="badge ${f.free > 0 ? "queued" : "ok"}">${esc(f.name)} ${f.used}/${f.max}</span>`).join(" ");
  return `<details class="card"><summary>${tr("拠点 {0} の惑星と、キャラクターの枠", esc(home.name))}</summary>
    <p class="small-note">${slots}</p>
    <div class="table-scroll"><table class="orders"><thead><tr><th>${tr("惑星")}</th><th>${tr("種類")}</th><th>${tr("採れる資源")}</th><th>${tr("使っているキャラクター")}</th></tr></thead>
    <tbody>${home.planets.map((p) => `<tr><td>${esc(p.name)}</td><td>${esc(planetKind(p.kind))}</td>
      <td><small>${p.resources.map((r) => esc(nm(r))).join(LIST_SEP) || `<span class="muted">${tr("PI 不可")}</span>`}</small></td>
      <td><small>${esc(p.users.join(LIST_SEP))}${p.planned?.length ? ` <span class="ok-text">${tr("＋提案: {0}", esc(p.planned.join(LIST_SEP)))}</span>` : ""}</small></td></tr>`).join("")}</tbody></table></div></details>`;
}

async function loadPlan() {
  const box = $("#plan");
  box.innerHTML = `<p class="muted">${tr("計算しています…（コロニーの数が多いと少し時間がかかります）")}</p>`;
  const system = $("#home-input").value.trim() || $("#home-system").value;
  const params = new URLSearchParams({ ids: [...ids].join(",") });
  if (system) params.set("system", system);
  if ($("#per-planet").value) params.set("per_planet", $("#per-planet").value);
  let d;
  try {
    d = await request("GET", `/api/pi/plan?${params}`);
  } catch (e) {
    box.innerHTML = `<div class="warn">${esc(e.message)}</div>`;
    return;
  }
  const prev = $("#home-system").value;
  $("#home-system").innerHTML = `<option value="">${tr("自動（コロニーが一番多い星系）")}</option>` + d.systems.map((s) =>
    `<option value="${s.id}">${tr("{0}（コロニー {1}）", esc(s.name), s.count)}</option>`).join("");
  $("#home-system").value = prev;
  $("#per-planet").placeholder = `${tr("自動: {0}", fmtNum(Math.round(d.per_planet)))}`;
  if (d.home) saveJson(HOME_KEY, d.home.id);

  const values = d.values;
  const totalNow = values.reduce((s, v) => s + (v.sell || 0) * v.per_day, 0);
  const totalGain = values.reduce((s, v) => s + (v.sell || 0) * v.gain, 0);
  const products = values.length ? `<div class="stat-row">${values.map((v) => `<div class="stat-card"><small class="muted">${esc(nm(v))}</small>
      <b>${tr("{0} /日", fmtNum(Math.round(v.per_day)))}</b><small class="muted">${v.sell ? `${tr("{0} ISK/日", fmtIsk(v.per_day * v.sell))}` : tr("価格なし")}${v.gain > 0.5 ? ` · <span class="ok-text">+${fmtNum(Math.round(v.gain))}</span>` : ""}</small></div>`).join("")}
      <div class="stat-card total"><small class="muted">${tr("製品の合計（Jita 売値）")}</small><b>${tr("{0} ISK/日", fmtIsk(totalNow))}</b>
        <small>${totalGain > 0 ? `${tr("提案どおりで")} <span class="ok-text">${tr("+{0} ISK/日", fmtIsk(totalGain))}</span>` : tr("すべて満稼働です")}</small></div></div>` : `<p class="muted">${tr("工場がありません。")}</p>`;
  const leftover = d.leftover.length ? `<div class="alert info"><span>${tr("提案のあとも余る材料: {0}", d.leftover.map((x) => `${tr("<b>{0}</b> {1}/日{2}", esc(nm(x)), fmtNum(Math.round(x.amount)), (x.planets != null ? `${tr("（抽出惑星 {0} 個分）", x.planets.toFixed(2))}` : ""))}`).join(LIST_SEP))}
    <br><small>${tr("これを使う工場を追加するか、その分の抽出惑星を他の資源に切り替えると無駄がなくなります。")}</small></span></div>` : "";
  box.innerHTML = `${charErrors(d.characters)}
    ${d.home ? `<p class="small-note muted">${tr("拠点: <b>{0}</b> · 抽出惑星 1 つの抽出量: {1}/日{2}", esc(d.home.name), fmtNum(Math.round(d.per_planet)), (d.per_planet_measured ? `${tr("（自分の平均 {0}）", fmtNum(Math.round(d.per_planet_measured)))}` : tr("（目安）")))}</p>` : ""}
    ${d.stopped_extractors ? `<div class="alert info"><span>${tr("⚠ 止まっている抽出機が {0} 台あります。計算は、これらを再び動かす前提です。", d.stopped_extractors)}</span></div>` : ""}
    <h3>${tr("製品")}</h3>${products}
    ${d.plans.length ? `<h3>${tr("満稼働にするための提案")}</h3>${d.plans.map((p) => planCard(p, values)).join("")}` : (values.length ? `<p class="ok-text">${tr("✓ すべての製品の工場が満稼働です。")}</p>` : "")}
    ${leftover}${flowTable(d.items)}${homeTable(d.home, d.free)}`;
}

// ---------- ゼロから配置し直す ----------

function layoutRow(x) {
  const days = Number($("#rd-program").value);
  if (x.role === "extract") {
    const perRun = x.p0_per_day * days;
    const ecus = x.heads_per_ecu.map((h, i) => `${tr("ECU {0}: {1}・ヘッド {2} 本・{3} 日", i + 1, esc(nm(x, "resource_ja", "resource_en")), h, days)}`).join("<br>");
    return `<li><span class="badge queued">${tr("抽出")}</span> ${tr("<b>{0}</b>（{1}）: <b>{2}</b> {3} → {4} {5} {6}", esc(x.planet.name), esc(planetKind(x.planet.kind)), esc(nm(x, "resource_ja", "resource_en")), perDay(x.p0_per_day), esc(nm(x, "p1_ja", "p1_en") || ""), perDay(x.p1_per_day), extractSteps(x, days))}
      <div class="pi-setup"><div><b>${tr("抽出プログラム")}</b><br>${ecus}<br><small class="muted">${tr("1 回の期間で約 {0} 個", fmtNum(Math.round(perRun)))}</small></div>
        <div><b>${tr("設備")}</b><br>${tr("司令基地 1{0}", x.launchpad ? tr("・発射台 1") : "")}<br>${tr("ECU {0}・ヘッド {1} 本", x.ecus, x.heads)}<br>${tr("基本工場（インダストリー施設）{0} 台 {1}", x.basic, x.launchpad ? "" : `<br><small class="muted">${tr("発射台なし（司令基地から打ち上げ）")}</small>`)}</div></div></li>`;
  }
  const total = x.factories.reduce((s, f) => s + f.count, 0);
  const kind = x.factories.some((f) => f.tier === 4) ? tr("ハイテク工場") : tr("高度工場");
  const fac = x.factories.length ? x.factories.map((f) => `${TIER[f.tier]} ${esc(nm(f))} ×${f.count}`).join("<br>") : tr("（予備）");
  return `<li><span class="badge ok">${tr("工場")}</span> ${tr("<b>{0}</b>（{1}）{2}", esc(x.planet.name), esc(planetKind(x.planet.kind)), factorySteps(x, kind))}
    <div class="pi-setup"><div><b>${tr("工場のレシピ")}</b><br>${fac}</div>
      <div><b>${tr("設備")}</b><br>${tr("司令基地 1・発射台 1")}<br>${tr("{0}（インダストリー施設）{1} 台", kind, total)}</div></div></li>`;
}

// 抽出惑星の作り方（手順と、記録した配置）
function extractSteps(x, days) {
  const found = bestLayout(x.planet.planet_id, x.planet.kind, x.resource);
  const ref = found ? `<div class="layout-rec">${layoutMap(found.rec, 130)}<div><b>${found.exact ? tr("この惑星での前回の配置") : `${tr("同じ種類の惑星（{0}）での配置", esc(found.rec.planet_name || ""))}`}</b><br>
      ${layoutSummary(found.rec)}<br><small>${tr("この形を目安に、スキャンで濃い場所を確かめて置いてください。")}</small></div></div>`
    : `<p class="muted small-note">${tr("この資源の配置の記録はありません。")}</p>`;
  const perEcu = x.heads_per_ecu.map((h, i) => `${tr("ECU {0} はヘッド {1} 本", i + 1, h)}`).join(LIST_SEP);
  return `<details class="mini-details"><summary>${tr("📘 配置の手順")}</summary><ol class="pi-steps">
    <li>${tr("惑星を開き、「スキャン」で <b>{0}</b> を表示して、濃い場所（赤〜白）を探す。", esc(nm(x, "resource_ja", "resource_en")))}</li>
    <li>${tr("司令基地を置き、<b>Lv{0}</b> にアップグレードする。{1}", x.level, x.launchpad ? tr("近くに発射台を 1 つ置く。") : tr("（発射台は置かず、司令基地から打ち上げる）"))}</li>
    <li>${x.ecus > 1 ? tr("ECU {0} 台を、それぞれ別の濃い場所の中心に置く。", x.ecus) : tr("ECU を濃い場所の中心に置く。")}</li>
    <li>${tr("{0}。ヘッドは濃い場所の上に、採掘範囲の円どうしが重ならないように並べる（重なると互いの抽出量が減る）。", perEcu)}</li>
    <li>${tr("プログラム: 資源 <b>{0}</b>・期間 <b>{1} 日</b>で「インストール」する。", esc(nm(x, "resource_ja", "resource_en")), days)}</li>
    <li>${tr("基本工場を <b>{0} 台</b>置き、レシピ「{1}」を設定する。", x.basic, esc(nm(x, "p1_ja", "p1_en") || ""))}</li>
    <li>${tr("リンク: {0}を中心に、ECU・基本工場をそれぞれつなぐ。", x.launchpad ? tr("発射台") : tr("司令基地"))}</li>
    <li>${tr("ルート: ECU → {0}（{1}）、{2} → 基本工場（{3}）、基本工場 → {4}（{5}）。", x.launchpad ? tr("発射台") : tr("司令基地"), esc(nm(x, "resource_ja", "resource_en")), x.launchpad ? tr("発射台") : tr("司令基地"), esc(nm(x, "resource_ja", "resource_en")), x.launchpad ? tr("発射台") : tr("司令基地"), esc(nm(x, "p1_ja", "p1_en") || ""))}</li>
  </ol>${ref}</details>`;
}

function factorySteps(x, kind) {
  if (!x.factories.length) return "";
  return `<details class="mini-details"><summary>${tr("📘 配置の手順")}</summary><ol class="pi-steps">
    <li>${tr("司令基地を置き、<b>Lv{0}</b> にアップグレードする。近くに発射台を 1 つ置く。", x.level)}</li>
    <li>${tr("{0}を置き、レシピを設定する: {1}。", kind, x.factories.map((f) => `${tr("「{0}」{1} 台", esc(nm(f)), f.count)}`).join(LIST_SEP))}</li>
    <li>${tr("リンク: 発射台を中心に、各工場をつなぐ（リンクが短いほど CPU・パワーグリッドを使わない）。")}</li>
    <li>${tr("ルート: 発射台 → 各工場（材料）、各工場 → 発射台（製品）。材料は抽出惑星から運んで発射台に入れる。")}</li>
  </ol></details>`;
}

async function loadRedesign() {
  const box = $("#redesign");
  box.innerHTML = `<p class="muted">${tr("計算しています…（初回は価格の取得に少し時間がかかります）")}</p>`;
  const params = new URLSearchParams({ ids: [...ids].join(","), price: $("#rd-price").value });
  const system = $("#home-input").value.trim() || $("#home-system").value;
  if (system) params.set("system", system);
  if ($("#rd-target").value) params.set("target", $("#rd-target").value);
  if ($("#rd-head").value) params.set("per_head", $("#rd-head").value);
  let d;
  try {
    [d] = await Promise.all([request("GET", `/api/pi/redesign?${params}`), loadLayouts()]);
  } catch (e) {
    box.innerHTML = `<div class="warn">${esc(e.message)}</div>`;
    return;
  }
  const prevTarget = $("#rd-target").value;
  $("#rd-target").innerHTML = `<option value="">${tr("自動（1 日の ISK が最大）")}</option>` + d.ranking.map((r) =>
    `<option value="${r.type_id}">${tr("{0} {1}（{2} ISK/日）", TIER[r.tier], esc(nm(r)), fmtIsk(r.isk_per_day))}</option>`).join("");
  $("#rd-target").value = prevTarget;
  $("#rd-head").placeholder = `${tr("自動: {0}", fmtNum(Math.round(d.per_head)))}`;

  const diff = d.total_isk_per_day - d.current_isk_per_day;
  const chars = d.characters.map((c) => `<span class="badge queued">${tr("{0}: 枠 {1}・司令基地 Lv{2}", esc(c.name), c.slots, c.ccu)}</span>`).join(" ");
  const products = d.products.map((p) => `<div class="stat-card"><small class="muted">${TIER[p.tier]} ${esc(nm(p))}</small>
    <b>${tr("{0} /日", fmtNum(Math.round(p.per_day * 10) / 10))}</b><small class="muted">${tr("{0} ISK/日（1 個 {1}）", fmtIsk(p.isk_per_day), fmtIsk(p.price))}</small></div>`).join("");
  const byChar = {};
  d.layout.forEach((x) => { (byChar[x.name] ||= []).push(x); });
  const layout = Object.entries(byChar).map(([name, rows]) => `<div class="card pi-char"><h3>${esc(name)} <small class="muted">${tr("{0} 惑星", rows.length)}</small></h3>
    <ul class="pi-layout">${rows.map(layoutRow).join("")}</ul></div>`).join("");
  const ranking = d.ranking.map((r, i) => `<tr><td class="r muted">${i + 1}</td><td>${TIER[r.tier]} ${esc(nm(r))}</td>
    <td class="r num">${fmtNum(Math.round(r.per_day * 10) / 10)}</td><td class="r num">${fmtIsk(r.price)}</td><td class="r num"><b>${fmtIsk(r.isk_per_day)}</b></td>
    <td class="r num">${r.extract_planets} / ${r.factory_planets}</td></tr>`).join("");
  const p0 = d.products.flatMap((p) => p.p0).map((x) => `${esc(nm(x))} ${fmtNum(Math.round(x.per_day))}`).join(LIST_SEP);
  box.innerHTML = `${d.errors.length ? charErrors(d.errors) : ""}
    <p class="small-note">${tr("拠点 <b>{0}</b> · コロニーの枠 <b>{1}</b>{2} · ヘッド 1 本 {3}/日{4}", esc(d.home.name), d.total_slots, (d.unused ? `${tr("（使わない枠 {0}）", d.unused)}` : ""), fmtNum(Math.round(d.per_head)), (d.per_head_measured ? `${tr("（今の抽出機の平均 {0}）", fmtNum(Math.round(d.per_head_measured)))}` : tr("（目安）")))}</p>
    <p>${chars}</p>
    <div class="stat-row">${products}
      <div class="stat-card total"><small class="muted">${tr("この配置の合計")}</small><b>${tr("{0} ISK/日", fmtIsk(d.total_isk_per_day))}</b>
        <small>${tr("今の配置 {0} ISK/日 →", fmtIsk(d.current_isk_per_day))} <span class="${diff >= 0 ? "ok-text" : "warn-text"}">${diff >= 0 ? "+" : ""}${fmtIsk(diff)}</span>
        ${tr("· 30 日で {0}</small>", fmtIsk(d.total_isk_per_day * 30))}</div></div>
    <p class="muted small-note">${tr("必要な P0: {0}", p0)}</p>
    <h3>${tr("キャラクターごとの配置")}</h3><div class="pi-layout-grid">${layout}</div>
    <details class="card"><summary>${tr("製品ごとの比較（全部の枠をその製品に使った場合）")}</summary>
      <div class="table-scroll"><table class="orders"><thead><tr><th class="r">#</th><th>${tr("製品")}</th><th class="r">${tr("1 日の量")}</th><th class="r">${tr("1 個の価格")}</th>
        <th class="r">${tr("ISK / 日")}</th><th class="r">${tr("抽出 / 工場の惑星")}</th></tr></thead><tbody>${ranking}</tbody></table></div></details>
    <p class="muted small-note">${tr("抽出プログラムの期間が短いほど 1 日の抽出量は増えます（抽出量は期間の後半ほど減るため）。「ヘッド 1 本の 1 日の抽出量」は、その期間で動かしたときの実績に合わせてください。 ヘッドは資源の濃い場所（スキャンで赤く見える場所）に、互いに離して置いてください。 抽出惑星は 1 つの資源（ECU は最大 2 台）を掘って同じ惑星で P1 にし、工場惑星に運んで P2 以上を作る前提です。 抽出量は資源の濃さ・抽出の期間で大きく変わるので、「ヘッド 1 本の 1 日の抽出量」を自分の実績に合わせてください。 同じ惑星に多くのコロニーを置くと資源が減りやすいので、なるべく分散させています。輸送の手間・税関の税は含めていません。")}</p>`;
}

$("#rd-run").addEventListener("click", loadRedesign);
$("#rd-program").addEventListener("change", () => { if (document.querySelector(".pi-layout")) loadRedesign(); });
$("#plan-run").addEventListener("click", loadPlan);
$("#home-system").addEventListener("change", () => { $("#home-input").value = ""; loadPlan(); });
$("#reload").addEventListener("click", () => { loadColonies(); loadPlan(); });

(async () => {
  try {
    const d = await request("GET", "/api/characters");
    characters = d.characters;
    groups = d.groups;
    ids = renderCharFilter($("#char-filter"), characters, groups, (next) => { ids = next; loadColonies(); loadPlan(); });
    const saved = loadJson(HOME_KEY, null);
    if (saved) $("#home-system").innerHTML = `<option value="${saved}" selected>${tr("前回の拠点")}</option>`;
    loadPlan();
    loadColonies();
  } catch (e) {
    toast(e.message, "error");
  }
})();
