"use strict";
// 流通ミッション: エージェントを探す → 確認して回るルート → 受注ルート → 受取と配達のルート（一筆書き）→ 割り込みで計算し直す

const PARAMS_KEY = "dist:params";
// {エージェント ID: {take: 受注したか, pickup: 受取場所の星系名（空 = 受注場所）, dest: 配達先の星系名, volume: 荷物の体積 m³, urgent: 緊急か}}
const ORDERS_KEY = "dist:orders";
// 配達の進み具合: {capacity, missions: [{key, label, pickup: 星系 ID, pickupName, dropoff, dropoffName, volume, urgent,
//   state: "waiting"（受取待ち）| "loaded"（積んでいる）| "done"（配達済み）}]}
const TRIP_KEY = "dist:trip";
let found = null;        // /api/dist/agents の結果
let systemIds = null;    // 星系名（英語・日本語、小文字）→ ID
let systemNames = null;  // 星系 ID → 英語名
let pickup = null;       // 受注ルートの結果
let orders = loadJson(ORDERS_KEY, {}) || {};
let trip = loadJson(TRIP_KEY, null);
let lastRoute = null;    // 最後に出した受取と配達のルート（keys: 地点の index → ミッションの key）

function secBadge(s) {
  const cls = { highsec: "sec-hi", lowsec: "sec-low", nullsec: "sec-null" }[s.kind] || "sec-wh";
  return `<span class="badge ${cls}">${(s.security ?? 0).toFixed(1)}</span>`;
}

function routeOptions() {
  return { min_sec: Number($("#ds-minsec").value), max_low: Number($("#ds-maxlow").value) };
}

async function loadSystems() {
  if (systemIds) return;
  const d = await request("GET", "/api/dist/systems");
  systemIds = new Map();
  systemNames = new Map();
  for (const [id, en, ja] of d.systems) {
    systemIds.set(en.toLowerCase(), id);
    if (ja) systemIds.set(ja.toLowerCase(), id);
    systemNames.set(id, en);
  }
  $("#ds-system-list").innerHTML = d.systems.map(([, en, ja, sec]) => `<option value="${esc(en)}">${LANG !== "ja" ? "" : esc(ja || "")} ${sec.toFixed(1)}</option>`).join("");
}

async function currentSystemName() {
  try {
    const d = await request("GET", "/api/wormhole/locations");
    return d.characters.find((c) => c.character_id === gameCharId())?.system?.name || "";
  } catch {
    return "";
  }
}

function saveOrders() {
  saveJson(ORDERS_KEY, orders);
}

function saveTrip() {
  saveJson(TRIP_KEY, trip);
}

const ACTION = { pickup: tr("📦 受取"), dropoff: tr("📬 配達") };
const URGENT = `<span class="badge missing">${tr("⚡ 緊急")}</span>`;

// 地点で行う受取・配達。progress のときは「済んだ」の印を付けられる
function actionHtml(a, d) {
  const key = d.keys?.[a.index];
  const m = trip?.missions.find((x) => x.key === key);
  const done = m && (a.type === "dropoff" ? m.state === "done" : m.state !== "waiting");
  const body = `<span class="badge ${a.type === "pickup" ? "queued" : "ok"}">${ACTION[a.type]}</span>${a.urgent ? ` ${URGENT}` : ""} ${esc(a.label)}`
    + `${a.volume ? ` <small class="muted">${fmtNum(a.volume)} m³</small>` : ""}${a.at != null ? ` <small class="muted">${tr("{0} ジャンプ目", a.at)}</small>` : ""}`;
  return key ? `<label class="ds-act ${done ? "done" : ""}"><input type="checkbox" data-step="${esc(key)}|${a.type}" ${done ? "checked" : ""}> ${body}</label>` : body;
}

// 回る順番とルートの表示（②③④で共有）。④は星系ごとに受取・配達する荷物も出す
function tourHtml(d, title) {
  const stops = d.stops.map((s, i) => `<li>${secBadge(s)} <b>${esc(s.name)}</b>${s.ja && LANG === "ja" ? ` <small class="muted">${esc(s.ja)}</small>` : ""}
    <small class="muted">${tr("{0} {1} ジャンプ", i ? tr("前から") : tr("出発から"), s.jumps)}</small>
    ${s.actions ? `<div class="ds-actions">${s.actions.map((a) => actionHtml(a, d)).join("<br>")}
      ${d.capacity ? `<div class="small-note muted">${tr("ここを出るときの積載 <b>{0}</b> / {1} m³", fmtNum(s.load), fmtNum(d.capacity))}</div>` : ""}</div>` : ""}</li>`).join("");
  const missed = (d.unreachable.length
    ? `<div class="warn">${tr("この決まり（ローセク・セキュリティ）では行けない{0}があります: {1}", d.stops[0]?.actions ? tr("ミッション") : tr("星系"), esc(d.unreachable.map((s) => s.name || s).join(LIST_SEP)))}</div>` : "")
    + (d.too_big?.length ? `<div class="warn">${tr("カーゴの容量より大きい荷物があります（このルートには入れていません）: {0}", esc(d.too_big.join(LIST_SEP)))}</div>` : "");
  const path = d.systems.map((s) => `${esc(s.name)}`).join(" → ");
  return `<div class="card"><div class="route-head"><div>${tr("🗺 <b>{0}</b> · {1} から <b>{2}</b> か所・合計 <b>{3}</b> ジャンプ {4}{5}", esc(title), esc(d.start.name), d.stops.length, d.jumps, routeSafetyHtml(d), (d.urgent_done_at != null ? ` <span class="badge missing">${tr("⚡ 緊急の配達は {0} ジャンプ目までに完了", d.urgent_done_at)}</span>` : ""))}</div>
      <div class="fit-actions">${d.jumps ? routeGameButton(d) : ""}</div></div>
    ${missed}${d.stops.length ? `<ol class="ds-stops">${stops}</ol>` : `<p class="muted">${tr("回る星系がありません。")}</p>`}
    ${d.jumps ? `<details class="mini-details"><summary>${tr("通る星系（{0}）", d.systems.length)}</summary><p class="small-note">${path}</p></details>` : ""}</div>`;
}

async function tour(start, systems) {
  return request("POST", "/api/dist/tour", { start, systems, ...routeOptions() });
}

function agentRows() {
  // ②のルートの順に、ステーションごとのエージェント
  const rank = new Map((found.check?.stops || []).map((s, i) => [s.id, i + 1]));
  const stations = [...found.stations].sort((a, b) => (rank.get(a.system.id) ?? 0) - (rank.get(b.system.id) ?? 0) || a.name.localeCompare(b.name));
  return stations.map((st) => `<div class="card ds-station"><div class="section-head"><h3>${secBadge(st.system)} ${esc(st.name)}</h3>
      <small class="muted">${tr("{0} · 基準から {1} ジャンプ{2}", esc(st.system.name), st.jumps, (rank.has(st.system.id) ? ` ${tr("· ルートの {0} か所目", rank.get(st.system.id))}` : ""))}</small></div>
    <table class="orders ds-agents"><thead><tr><th></th><th>${tr("エージェント")}</th><th>${tr("受取場所")}</th><th>${tr("配達先")}</th><th>${tr("体積（m³）")}</th><th>${tr("緊急")}</th></tr></thead><tbody>${st.agents.map((a) => {
      const o = orders[a.id] || {};
      const off = o.take ? "" : "disabled";
      return `<tr><td><label class="ds-take"><input type="checkbox" data-take="${a.id}" ${o.take ? "checked" : ""}> ${tr("受注")}</label></td>
        <td><b>${esc(a.name)}</b> <span class="badge queued">L${a.level}</span>${a.locator ? ` <span class="badge ok" title="${tr("居場所を調べられるエージェント")}">${tr("ロケーター")}</span>` : ""}
          <br><small class="muted">${esc(a.corp)}</small></td>
        <td><input type="text" data-pickup="${a.id}" list="ds-system-list" placeholder="${tr("受注場所（{0}）", esc(st.system.name))}" value="${esc(o.pickup || "")}" ${off}
          title="${tr("荷物を別の場所で受け取るミッション（回収）のときだけ入れる")}"></td>
        <td><input type="text" data-dest="${a.id}" list="ds-system-list" placeholder="${tr("配達先の星系")}" value="${esc(o.dest || "")}" ${off}></td>
        <td><input type="number" data-volume="${a.id}" min="0" step="any" placeholder="m³" value="${esc(o.volume ?? "")}" ${off}></td>
        <td><input type="checkbox" data-urgent="${a.id}" title="${tr("緊急（なるべく早く受け取り・届ける）")}" ${o.urgent ? "checked" : ""} ${off}></td></tr>`;
    }).join("")}</tbody></table></div>`).join("");
}

function render() {
  $("#ds-agents-section").hidden = false;
  $("#ds-check-route").innerHTML = (found.check ? tourHtml(found.check, tr("エージェントを確認して回るルート")) : "")
    + `<p class="muted small-note">${tr("{0} から {1} ジャンプ以内に、流通エージェントが {2} 人（{3} ステーション）います。", esc(found.base.name), found.jumps, found.agents, found.stations.length)}</p>`;
  $("#ds-agents").innerHTML = found.stations.length ? agentRows() : `<div class="card empty-card">${tr("流通エージェントが見つかりません。ジャンプ数を増やしてください。")}</div>`;
}

async function search() {
  let system = $("#ds-system").value.trim();
  const box = $("#ds-check-route");
  $("#ds-agents-section").hidden = false;
  box.innerHTML = `<p class="muted">${tr("エージェントを探しています…")}</p>`;
  $("#ds-agents").innerHTML = "";
  if (!system) {
    system = await currentSystemName();
    if (!system) { box.innerHTML = `<div class="warn">${tr("今いる星系を取得できません。基準の星系を入力してください。")}</div>`; return; }
    $("#ds-system").placeholder = `${tr("今いる星系: {0}", system)}`;
  }
  const levels = [...document.querySelectorAll(".ds-levels input:checked")].map((i) => i.value).join(",");
  const params = { system, jumps: $("#ds-jumps").value, levels, ...routeOptions() };
  saveJson(PARAMS_KEY, { ...params, system: $("#ds-system").value.trim(), cargo: $("#ds-cargo").value });
  try {
    found = await request("GET", `/api/dist/agents?${new URLSearchParams(params)}`);
    const systems = [...new Set(found.stations.map((st) => st.system.id))];
    found.check = systems.length ? await tour(found.base.id, systems) : null;
  } catch (e) {
    box.innerHTML = `<div class="warn">${esc(e.message)}</div>`;
    return;
  }
  pickup = null;
  $("#ds-pickup-route").innerHTML = "";
  render();
}

function takenAgents() {
  if (!found) return [];
  return found.stations.flatMap((st) => st.agents.filter((a) => orders[a.id]?.take).map((a) => ({ ...a, system: st.system })));
}

async function calcPickup() {
  const taken = takenAgents();
  if (!taken.length) { toast(tr("受注したエージェントに印を付けてください。"), "error"); return null; }
  $("#ds-pickup-route").innerHTML = `<p class="muted">${tr("受注ルートを計算しています…")}</p>`;
  try {
    pickup = await tour(found.base.id, [...new Set(taken.map((a) => a.system.id))]);
  } catch (e) {
    $("#ds-pickup-route").innerHTML = `<div class="warn">${esc(e.message)}</div>`;
    return null;
  }
  $("#ds-pickup-route").innerHTML = tourHtml(pickup, tr("受注ルート（受注するエージェントだけを回る）"));
  $("#ds-delivery-section").hidden = false;
  return pickup;
}

// ③の入力から、配達の進み具合（trip）を作る
async function buildTrip() {
  const taken = takenAgents();
  const missing = taken.filter((a) => !orders[a.id]?.dest?.trim());
  if (!taken.length) { toast(tr("受注したエージェントに印を付けてください。"), "error"); return null; }
  if (missing.length) { toast(`${tr("配達先が入っていません: {0}", missing.map((a) => a.name).join(LIST_SEP))}`, "error"); return null; }
  await loadSystems();
  const unknown = [];
  const lookup = (name) => {
    const id = systemIds.get(name.trim().toLowerCase());
    if (!id) unknown.push(name);
    return id;
  };
  const capacity = Number($("#ds-cargo").value) || 0;
  const noVolume = taken.filter((a) => !(Number(orders[a.id].volume) > 0));
  if (capacity && noVolume.length) {
    toast(`${tr("カーゴの容量を入れたときは、荷物の体積も入れてください: {0}", noVolume.map((a) => a.name).join(LIST_SEP))}`, "error");
    return null;
  }
  const missions = taken.map((a) => {
    const o = orders[a.id];
    const at = o.pickup?.trim() ? lookup(o.pickup) : a.system.id;
    const to = lookup(o.dest);
    return { key: `a${a.id}`, label: a.name, agentSystem: a.system.id, pickup: at, pickupName: systemNames.get(at),
      dropoff: to, dropoffName: systemNames.get(to), volume: Number(o.volume) || 0, urgent: Boolean(o.urgent), state: "waiting" };
  });
  if (unknown.length) { toast(`${tr("見つからない星系があります: {0}", unknown.join(LIST_SEP))}`, "error"); return null; }
  if (!pickup && !(await calcPickup())) return null;
  // 受取場所が受注場所と同じ荷物は、受注したときにそのステーションの格納庫に入る。受注した順に、カーゴに入るだけ積んだとみなし、
  // 積みきれなかった分は④でそのステーションへ取りに行く
  const acceptOrder = new Map(pickup.stops.map((s, i) => [s.id, i]));
  let loaded = 0;
  const left = [];
  missions.sort((a, b) => (acceptOrder.get(a.agentSystem) ?? 0) - (acceptOrder.get(b.agentSystem) ?? 0));
  for (const m of missions) {
    if (m.pickup !== m.agentSystem) continue;  // 別の場所で受け取る（回収）
    if (!capacity || loaded + m.volume <= capacity) {
      loaded += m.volume;
      m.state = "loaded";
    } else {
      left.push(m.label);
    }
  }
  return { trip: { capacity, missions }, left };
}

// trip の残り（配達済みを除く）を、start から回るルートにする
async function routeTrip(start, title, notes = "") {
  const box = $("#ds-delivery-route");
  const rest = trip.missions.filter((m) => m.state !== "done");
  if (!rest.length) {
    box.innerHTML = `<div class="card"><p class="ok-text">${tr("✓ すべての荷物を配達しました。")}</p></div>`;
    lastRoute = null;
    renderReroute();
    return;
  }
  trip.capacity = Number($("#ds-cargo").value) || 0;
  saveTrip();
  box.innerHTML = `<p class="muted">${tr("受取と配達のルートを計算しています…")}</p>`;
  const payload = rest.map((m) => ({ label: m.label, pickup: m.state === "loaded" ? null : m.pickup, dropoff: m.dropoff,
    volume: m.volume, urgent: m.urgent }));
  try {
    const d = await request("POST", "/api/dist/deliver", { start, missions: payload, capacity: trip.capacity, ...routeOptions() });
    d.keys = rest.map((m) => m.key);
    lastRoute = { d, title, notes };
    renderRoute();
  } catch (e) {
    box.innerHTML = `<div class="warn">${esc(e.message)}</div>`;
  }
  renderReroute();
}

function renderRoute() {
  if (!lastRoute) return;
  const { d, title, notes } = lastRoute;
  const urgent = trip.missions.filter((m) => m.urgent && m.state !== "done").length;
  const cargo = d.capacity
    ? `${tr("カーゴ {0} m³: 出発のときに積んでいる荷物 {1} m³、途中の最大の積載 {2} m³。", fmtNum(d.capacity), fmtNum(d.initial_load), fmtNum(d.max_load))}`
    : tr("カーゴの容量は考えていません（①でカーゴ容量を入れると、積みきれる順番にします）。");
  $("#ds-delivery-route").innerHTML = tourHtml(d, title)
    + `<p class="small-note">${tr("{0}どの荷物も、受取場所を通ってから配達先へ行く順番です。{1}{2} 済んだ受取・配達には印を付けてください。", notes, (urgent ? `${tr("緊急の荷物（{0} 件）は、合計ジャンプ数が少し増えても先に回します。", urgent)}` : ""), cargo)}</p>`;
}

async function calcDelivery() {
  const built = await buildTrip();
  if (!built) return;
  trip = built.trip;
  saveTrip();
  const fetches = trip.missions.filter((m) => m.pickup !== m.agentSystem).length;
  const notes = `${tr("受注 {0} ジャンプのあと、ミッション {1} 件{2}。", pickup.jumps, trip.missions.length, (fetches ? `${tr("（うち別の場所で受け取る {0} 件）", fetches)}` : ""))}`
    + (built.left.length ? `${tr("積みきれなかった {0} は、エージェントのステーションの格納庫へ取りに行く順番に入れています。", built.left.join(LIST_SEP))}` : "");
  await routeTrip(pickup.end, tr("受取と配達のルート（最後に受注した星系から）"), notes);
}

// ---------- 割り込み: 現在地と新しい緊急ミッション ----------

const STATE = { waiting: `<span class="badge queued">${tr("受取待ち")}</span>`, loaded: `<span class="badge ok">${tr("積んでいる")}</span>`, done: `<span class="badge">${tr("配達済み")}</span>` };

function renderReroute() {
  const box = $("#ds-reroute");
  box.hidden = !trip;
  if (!trip) return;
  const rows = trip.missions.map((m) => `<tr class="${m.state === "done" ? "muted" : ""}"><td>${STATE[m.state]}</td>
    <td><b>${esc(m.label)}</b></td>
    <td>${m.state === "waiting" ? esc(m.pickupName || "") : "—"} → ${esc(m.dropoffName || "")}</td>
    <td class="r num">${m.volume ? `${fmtNum(m.volume)} m³` : "-"}</td>
    <td><label class="ds-take"><input type="checkbox" data-trip-urgent="${esc(m.key)}" ${m.urgent ? "checked" : ""} ${m.state === "done" ? "disabled" : ""}> ${tr("緊急")}</label></td>
    <td>${m.added ? `<button class="icon-btn" type="button" title="${tr("消す")}" data-trip-remove="${esc(m.key)}">×</button>` : ""}</td></tr>`).join("");
  $("#ds-trip-list").innerHTML = `<table class="orders ds-trip"><thead><tr><th>${tr("状態")}</th><th>${tr("ミッション")}</th><th>${tr("受取 → 配達先")}</th><th class="r">${tr("体積")}</th><th></th><th></th></tr></thead>
    <tbody>${rows}</tbody></table>`;
}

async function addUrgent() {
  await loadSystems();
  const label = $("#ds-new-label").value.trim() || tr("緊急ミッション");
  const fromName = $("#ds-new-pickup").value.trim();
  const toName = $("#ds-new-dest").value.trim();
  const from = fromName ? systemIds.get(fromName.toLowerCase()) : null;
  const to = systemIds.get(toName.toLowerCase());
  if (!to) { toast(toName ? `${tr("星系「{0}」が見つかりません。", toName)}` : tr("配達先を入れてください。"), "error"); return; }
  if (fromName && !from) { toast(`${tr("星系「{0}」が見つかりません。", fromName)}`, "error"); return; }
  const volume = Number($("#ds-new-volume").value) || 0;
  if (trip.capacity && !(volume > 0)) { toast(tr("カーゴの容量を使っているときは、体積も入れてください。"), "error"); return; }
  trip.missions.push({ key: `n${Date.now()}`, label, pickup: from, pickupName: from ? systemNames.get(from) : "", dropoff: to,
    dropoffName: systemNames.get(to), volume, urgent: $("#ds-new-urgent").checked, state: from ? "waiting" : "loaded", added: true });
  saveTrip();
  ["#ds-new-label", "#ds-new-pickup", "#ds-new-dest", "#ds-new-volume"].forEach((s) => { $(s).value = ""; });
  renderReroute();
  toast(`${tr("「{0}」を追加しました。「現在地から計算し直す」を押してください。", label)}`, "ok");
}

async function reroute() {
  await loadSystems();
  let name = $("#ds-here").value.trim();
  if (!name) {
    name = await currentSystemName();
    if (!name) { toast(tr("今いる星系を取得できません。現在地を入力してください。"), "error"); return; }
    $("#ds-here").placeholder = `${tr("今いる星系: {0}", name)}`;
  }
  const here = systemIds.get(name.toLowerCase());
  if (!here) { toast(`${tr("星系「{0}」が見つかりません。", name)}`, "error"); return; }
  const rest = trip.missions.filter((m) => m.state !== "done");
  const notes = tr("現在地 {0} から計算し直しました。残り {1} 件（積んでいる {2} 件・受取待ち {3} 件）。配達済みの {4} 件は除いています。",
    systemNames.get(here), rest.length, rest.filter((m) => m.state === "loaded").length,
    rest.filter((m) => m.state === "waiting").length, trip.missions.length - rest.length);
  await routeTrip(here, tr("受取と配達のルート（現在地から計算し直し）"), notes);
}

// ---------- 入力 ----------

document.addEventListener("change", (ev) => {
  const take = ev.target.closest("[data-take]");
  if (take) {
    const id = take.dataset.take;
    orders[id] = { ...(orders[id] || {}), take: take.checked };
    for (const attr of ["data-dest", "data-pickup", "data-volume", "data-urgent"]) {
      const el = document.querySelector(`[${attr}="${id}"]`);
      if (el) el.disabled = !take.checked;
    }
    if (take.checked) document.querySelector(`[data-dest="${id}"]`)?.focus();
    pickup = null;  // 受注が変わったら、ルートは計算し直す
    saveOrders();
    return;
  }
  const urgent = ev.target.closest("[data-urgent]");
  if (urgent) {
    orders[urgent.dataset.urgent] = { ...(orders[urgent.dataset.urgent] || {}), urgent: urgent.checked };
    saveOrders();
    return;
  }
  // ルートの「済んだ」の印: 受取 → 積んでいる、配達 → 配達済み
  const step = ev.target.closest("[data-step]");
  if (step && trip) {
    const [key, type] = step.dataset.step.split("|");
    const m = trip.missions.find((x) => x.key === key);
    if (!m) return;
    if (type === "pickup") m.state = step.checked ? (m.state === "done" ? "done" : "loaded") : "waiting";
    else m.state = step.checked ? "done" : "loaded";
    saveTrip();
    renderRoute();
    renderReroute();
    return;
  }
  const tripUrgent = ev.target.closest("[data-trip-urgent]");
  if (tripUrgent && trip) {
    const m = trip.missions.find((x) => x.key === tripUrgent.dataset.tripUrgent);
    if (m) m.urgent = tripUrgent.checked;
    saveTrip();
  }
});
document.addEventListener("input", (ev) => {
  for (const [attr, field] of [["dest", "dest"], ["volume", "volume"], ["pickup", "pickup"]]) {
    const el = ev.target.closest(`[data-${attr}]`);
    if (el && el.dataset[attr]) {
      orders[el.dataset[attr]] = { ...(orders[el.dataset[attr]] || {}), [field]: el.value };
      saveOrders();
    }
  }
});
document.addEventListener("click", (ev) => {
  const rm = ev.target.closest("[data-trip-remove]");
  if (rm && trip) {
    trip.missions = trip.missions.filter((m) => m.key !== rm.dataset.tripRemove);
    saveTrip();
    renderReroute();
  }
});

$("#ds-run").addEventListener("click", search);
$("#ds-system").addEventListener("keydown", (ev) => { if (ev.key === "Enter") search(); });
$("#ds-pickup").addEventListener("click", calcPickup);
$("#ds-delivery").addEventListener("click", calcDelivery);
$("#ds-new-add").addEventListener("click", addUrgent);
$("#ds-reroute-run").addEventListener("click", reroute);
$("#ds-clear").addEventListener("click", () => {
  if (!confirm(tr("受注の印と配達先、配達の進み具合をすべて消しますか？"))) return;
  orders = {};
  trip = null;
  lastRoute = null;
  saveOrders();
  saveTrip();
  pickup = null;
  $("#ds-pickup-route").innerHTML = "";
  $("#ds-delivery-route").innerHTML = "";
  renderReroute();
  if (found) render();
});

(async () => {
  const saved = loadJson(PARAMS_KEY, null) || {};
  $("#ds-maxlow").innerHTML = maxLowOptions(saved.max_low || 0);
  $("#ds-minsec").innerHTML = minSecOptions(saved.min_sec || 0.5);
  if (saved.system) $("#ds-system").value = saved.system;
  if (saved.jumps != null) $("#ds-jumps").value = saved.jumps;
  if (saved.cargo) $("#ds-cargo").value = saved.cargo;
  if (saved.levels) document.querySelectorAll(".ds-levels input").forEach((i) => { i.checked = saved.levels.split(",").includes(i.value); });
  // 配達の途中で閉じても、続きから割り込み・計算し直しができる
  if (trip) {
    $("#ds-delivery-section").hidden = false;
    renderReroute();
  }
  try {
    const { characters } = await request("GET", "/api/characters");
    $("#game-char").innerHTML = gameCharSelect(characters.filter((c) => !c.missing));
  } catch (e) {
    toast(e.message, "error");
  }
  loadSystems().catch(() => { /* SDE の準備中など。配達ルートの計算のときにもう一度読む */ });
})();
