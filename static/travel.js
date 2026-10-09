"use strict";
// 移動: ルートと危険度・目的地の設定・ジャンプクローン・ジャンプ疲労

const ROUTE_KEY = "travel:route";
let characters = [];

function secBadge(s) {
  const cls = { highsec: "sec-hi", lowsec: "sec-low", nullsec: "sec-null", pochven: "sec-null" }[s.kind] || "sec-wh";
  const label = s.kind === "wormhole" || s.kind === "pochven" ? s.label : (s.security ?? 0).toFixed(1);
  return `<span class="badge ${cls}">${esc(label)}</span>`;
}

function danger(s) {
  if (s.ship_kills >= 10 || s.pod_kills >= 5) return `<span class="badge missing">${tr("⚠ 危険")}</span>`;
  if (s.ship_kills >= 3) return `<span class="badge queued">${tr("注意")}</span>`;
  return "";
}

async function currentSystemName() {
  const id = gameCharId();
  try {
    const d = await request("GET", "/api/wormhole/locations");
    return d.characters.find((c) => c.character_id === id)?.system?.name || "";
  } catch {
    return "";
  }
}

async function runRoute() {
  const box = $("#route");
  let from = $("#r-from").value.trim();
  const to = $("#r-to").value.trim();
  if (!to) { toast(tr("目的地を入力してください。"), "error"); return; }
  box.innerHTML = `<p class="muted">${tr("ルートを調べています…")}</p>`;
  if (!from) {
    from = await currentSystemName();
    if (!from) { box.innerHTML = `<div class="warn">${tr("現在地を取得できません（再ログインが必要な場合があります）。出発地を入力してください。")}</div>`; return; }
    $("#r-from").placeholder = `${tr("現在地: {0}", from)}`;
  }
  const flag = $("#r-flag").value;
  const avoid = $("#r-avoid").value.trim();
  const ship = $("#r-ship").value.trim();
  const min_sec = $("#r-minsec").value;
  const max_low = $("#r-maxlow").value;
  saveJson(ROUTE_KEY, { to, flag, avoid, ship, min_sec, max_low });
  let d;
  try {
    d = await request("GET", `/api/travel/route?${new URLSearchParams({ from, to, flag, avoid, ship, min_sec, max_low, autopilot: 1, character_id: gameCharId() })}`);
  } catch (e) {
    box.innerHTML = `<div class="warn">${esc(e.message)}</div>`;
    return;
  }
  const dest = d.systems[d.systems.length - 1];
  const rows = d.systems.map((s, i) => `<tr class="${s.ship_kills >= 10 ? "danger-row" : ""}"><td class="r muted">${i}</td>
    <td><b>${esc(s.name)}</b> <small class="muted">${esc(s.region || "")}</small></td><td>${secBadge(s)}</td>
    <td class="r num">${s.ship_kills ? `<b>${s.ship_kills}</b>` : "0"}</td><td class="r num">${s.pod_kills || 0}</td>
    <td class="r num muted">${fmtNum(s.jumps)}</td><td>${danger(s)}</td>
    <td><button class="btn small" type="button" data-wp="${s.id}" data-name="${esc(s.name)}" title="${tr("経由地に追加")}">${tr("＋")}</button></td></tr>`).join("");
  box.innerHTML = `<div class="route-head"><div>${tr("<b>{0} → {1}</b> · <b>{2}</b> ジャンプ（{3}） {4} · 直近 1 時間の撃墜 {5}{6}", esc(d.systems[0].name), esc(dest.name), d.jumps, esc(d.flag_label), routeSafetyHtml(d), d.ship_kills, autopilotHtml(d.autopilot))}</div>
    <div class="fit-actions">${routeGameButton(d)}<button class="btn ${d.flag === "highsec" ? "" : "primary"}" type="button" data-dest="${dest.id}" data-name="${esc(dest.name)}">${tr("🎯 ゲームの目的地に設定")}</button></div></div>
    <div class="table-scroll"><table class="orders"><thead><tr><th class="r">#</th><th>${tr("星系")}</th><th>${tr("セキュリティ")}</th><th class="r">${tr("艦の撃墜")}</th>
      <th class="r">${tr("ポッド")}</th><th class="r">${tr("ジャンプ数")}</th><th></th><th></th></tr></thead><tbody>${rows}</tbody></table></div>
    <p class="muted small-note">${tr("「＋」は、その星系をゲームの経由地の最後に追加します。")}</p>`;
}

$("#r-run").addEventListener("click", runRoute);
// 「通る星系のセキュリティ」は「ローセクを通らない最短」のときだけ使う
function toggleMinSec() {
  $("#r-minsec-label").hidden = $("#r-flag").value !== "highsec";
  $("#r-maxlow-label").hidden = $("#r-flag").value !== "highsec";
}
$("#r-flag").addEventListener("change", toggleMinSec);
["#r-from", "#r-to", "#r-avoid", "#r-ship"].forEach((s) => $(s).addEventListener("keydown", (ev) => { if (ev.key === "Enter") runRoute(); }));

document.addEventListener("click", (ev) => {
  const dest = ev.target.closest("[data-dest]");
  if (dest) {
    gameAction("/api/ui/waypoint", { destination_id: Number(dest.dataset.dest), clear: true }, `${tr("目的地を {0} に設定しました", dest.dataset.name)}`);
    return;
  }
  const wp = ev.target.closest("[data-wp]");
  if (wp) gameAction("/api/ui/waypoint", { destination_id: Number(wp.dataset.wp), clear: false }, `${tr("{0} を経由地に追加しました", wp.dataset.name)}`);
});

// ---------- クローン ----------

async function loadClones() {
  const box = $("#clones");
  try {
    const d = await request("GET", "/api/travel/clones");
    box.innerHTML = charErrors(d.characters) + `<div class="clone-grid">${d.characters.filter((c) => c.jump_clones).map((c) => `
      <div class="card"><div class="section-head"><h3>${esc(c.character_name)}</h3>
        ${c.clone_ready_at ? `<span class="badge queued">${tr("クローンジャンプ: あと {0}", esc(timeLeft(c.clone_ready_at)))}</span>` : `<span class="badge ok">${tr("クローンジャンプ可")}</span>`}</div>
        <small class="muted">${tr("ホーム: {0} · 待ち時間 {1} 時間", esc(c.home?.name || "-"), c.cooldown_hours)}</small>
        ${c.fatigue_expire ? `<div class="warn-text small-note">${tr("ジャンプ疲労: あと {0}（{1} まで）", esc(timeLeft(c.fatigue_expire)), esc(fmtLocal(c.fatigue_expire)))}</div>`
          : c.fatigue_needs_scope ? `<div class="small-note muted">${tr("ジャンプ疲労: <a href=\"/login\">再ログイン</a>が必要")}</div>` : `<div class="small-note ok-text">${tr("ジャンプ疲労なし")}</div>`}
        <ul class="clone-list">${c.jump_clones.length ? c.jump_clones.map((j) => `<li><b>${esc(j.name || j.location || tr("不明な場所"))}</b>
          ${j.name ? `<small class="muted">${esc(j.location || "")}</small>` : ""}
          <small class="muted">${j.implants.length ? esc(j.implants.join(LIST_SEP)) : tr("インプラントなし")}</small></li>`).join("") : `<li class="muted">${tr("ジャンプクローンはありません")}</li>`}</ul></div>`).join("")}</div>`;
  } catch (e) {
    box.innerHTML = `<div class="warn">${esc(e.message)}</div>`;
  }
}

(async () => {
  try {
    const d = await request("GET", "/api/characters");
    characters = d.characters.filter((c) => !c.missing);
    $("#game-char").innerHTML = gameCharSelect(characters);
    const saved = loadJson(ROUTE_KEY, null);
    $("#r-flag").innerHTML = routeFlagOptions(saved?.flag || "highsec");
    $("#r-minsec").innerHTML = minSecOptions(saved?.min_sec || 0.5);
    $("#r-maxlow").innerHTML = maxLowOptions(saved?.max_low || 0);
    toggleMinSec();
    if (saved) { $("#r-to").value = saved.to || ""; $("#r-avoid").value = saved.avoid || ""; $("#r-ship").value = saved.ship || ""; }
  } catch (e) {
    toast(e.message, "error");
  }
  loadClones();
})();
