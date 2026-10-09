"use strict";
// おすすめ艦船: キャラクターが今乗れる艦・10 日以内に乗れる艦（役割ごと）

let charId = null;
let data = null;
const TECH = { 1: "T1", 2: "T2", 3: "T3" };

function stats(s, role) {
  const parts = [];
  if ((role === "missile" || role === "bomber") && s.launchers) parts.push(`${tr("ランチャー {0}", s.launchers)}`);
  if (role === "turret" && s.turrets) parts.push(`${tr("タレット {0}", s.turrets)}`);
  if (role === "exploration" && s.virus_bonus) parts.push(`${tr("ハッキングの強さ +{0}", fmtNum(s.virus_bonus))}`);
  if (role === "salvage") parts.push(`${tr("ハイスロット {0}", s.hi_slots)}`);
  if (role === "special_hauler" && s.special_hold) parts.push(`${tr("専用カーゴ {0} m³", fmtNum(s.special_hold))}`);
  if (role === "drone" || role === "drone_mining" || s.bandwidth >= 25) {
    if (s.bandwidth) parts.push(`${tr("ドローン帯域 {0} Mbit/s", fmtNum(s.bandwidth))}`);
    if (s.drone_bay) parts.push(`${tr("ドローンベイ {0} m³", fmtNum(s.drone_bay))}`);
  }
  if (role === "hauler" || role.startsWith("mining")) parts.push(`${tr("カーゴ {0} m³", fmtNum(s.cargo))}`);
  if (role.startsWith("mining") && s.mining_hold) parts.push(`${tr("採掘カーゴ {0} m³", fmtNum(s.mining_hold))}`);
  return parts.map((p) => `<span>${esc(p)}</span>`).join("");
}

function shipRow(s, role, soon) {
  const time = soon
    ? (s.status === "queued" ? `<span class="badge queued">${tr("⏳ キュー済 {0}", esc(fmtLocal(s.ready_at)))}</span>`
      : `<span class="badge missing">${tr("あと {0}", esc(fmtMinutes(s.minutes)))}</span>`)
    : `<span class="badge ok">${tr("✓ 乗れます")}</span>`;
  return `<li class="ship-rec">
    <div class="ship-rec-main"><b>${esc(nm(s))}</b><small class="muted">${nmSub(s, " · ")}${esc(s.group)} · ${TECH[s.tech] || ""}</small>
      <div class="ship-rec-stats">${stats(s, role)}</div></div>
    <div class="ship-rec-side">${time}
      <div class="fit-actions">
        <button class="btn small primary" type="button" data-action="ship-fits" data-id="${s.type_id}" data-name="${esc(nm(s))}">${tr("🛠 おすすめフィット")}</button>
        ${soon ? `<button class="btn small" type="button" data-action="plan" data-id="${s.type_id}" data-name="${esc(nm(s))}">${tr("📋 スキルプラン")}</button>` : ""}
        <a class="btn small" href="/market?type_id=${s.type_id}">${tr("🛒 相場")}</a>
      </div></div></li>`;
}

function render() {
  const roles = data.roles.map((r) => [r.role, r]);
  $("#role-tabs").innerHTML = roles.map(([role, r]) =>
    `<a href="#role-${role}">${esc(r.label)} <small>${r.now.length} / ${r.soon.length}</small></a>`).join("");
  $("#rec-body").innerHTML = roles.map(([role, r]) => `
    <section class="rec-role" id="role-${role}"><h2>${esc(r.label)}</h2>
      <div class="rec-cols">
        <div><h3>${tr("✓ 今乗れる")} <span class="muted">${r.now.length}</span></h3>
          ${r.now.length ? `<ul class="ship-rec-list">${r.now.map((s) => shipRow(s, role, false)).join("")}</ul>` : `<p class="muted">${tr("今乗れる艦はありません。")}</p>`}</div>
        <div><h3>${tr("⏳ 10 日以内の訓練で乗れる")} <span class="muted">${r.soon.length}</span></h3>
          ${r.soon.length ? `<ul class="ship-rec-list">${r.soon.map((s) => shipRow(s, role, true)).join("")}</ul>` : `<p class="muted">${tr("10 日以内に乗れる艦はありません。")}</p>`}</div>
      </div></section>`).join("");
}

async function load() {
  $("#rec-body").innerHTML = `<p class="muted">${tr("艦船を調べています…（初回は少し時間がかかります）")}</p>`;
  try {
    data = await request("GET", withBoostQuery(`/api/recommend/ships?character_id=${charId}`));
  } catch (e) {
    $("#rec-body").innerHTML = `<div class="warn">${esc(e.message)}</div>`;
    return;
  }
  $("#rec-note").innerHTML = boostQuery()
    ? `<div class="alert boost"><span>${tr("🧠 スキルチェッカーで設定したブーストを、訓練時間の計算に反映しています。")}</span></div>` : "";
  render();
}

// ---------- 艦を選んだときのおすすめフィット ----------

bindWcsToggle();  // 次に艦のフィットを開いたときから反映

async function openShipFits(typeId, name) {
  const dialog = $("#ship-fits-dialog");
  const body = $("#ship-fits-body");
  body.innerHTML = `<span class="muted">${tr("{0} のフィットを調べています…", esc(name))}</span>`;
  dialog.showModal();
  let d;
  try {
    d = await request("GET", withBoostQuery(`/api/recommend/ship-fits?character_id=${charId}&type_id=${typeId}${wcsQuery()}`));
  } catch (e) {
    body.innerHTML = `<div class="warn">${esc(e.message)}</div>`;
    return;
  }
  const note = d.auto
    ? `<div class="alert info"><span>${tr("この艦には定番フィット・保存したフィットが無いため、役割に合わせて<b>自動で組んだフィット（試作）</b>を出しています。 艦のスロット・ボーナスから機械的に組んだ「とりあえず使える構成」で、艦固有の使い方までは考えていません。")}</span></div>`
    : "";
  const cards = d.fits.length
    ? d.fits.map((e) => fitCard(e, !e.usable_now, true)).join("")
    : `<p class="muted">${tr("この艦のフィットを用意できませんでした。")}</p>`;
  body.innerHTML = `
    <div class="plan-head"><div><h3>${tr("{0} のおすすめフィット", esc(nm(d)))}</h3><span class="muted">${nmSub(d)}</span></div>
      <button class="icon-btn" type="button" title="${tr("閉じる")}" data-action="close-ship-fits">×</button></div>
    ${note}<div class="ship-fits-list">${cards}</div>`;
  hydrateJitaCosts(body);
}

document.addEventListener("click", async (ev) => {
  const el = ev.target.closest("[data-action='plan'], [data-action='ship-fits'], [data-action='close-ship-fits']");
  if (!el) return;
  try {
    if (el.dataset.action === "plan") {
      await openPlanDialog({ types: [Number(el.dataset.id)], charId, title: `${tr("{0} に乗る", el.dataset.name)}` });
    } else if (el.dataset.action === "ship-fits") {
      await openShipFits(Number(el.dataset.id), el.dataset.name);
    } else {
      $("#ship-fits-dialog").close();
    }
  } catch (e) {
    toast(e.message, "error");
  }
});

$("#ship-fits-dialog").addEventListener("click", (ev) => { if (ev.target.id === "ship-fits-dialog") ev.target.close(); });

$("#rec-char").addEventListener("change", () => {
  charId = Number($("#rec-char").value);
  fitCardCharId = charId;
  saveJson(REC_CHAR_KEY, charId);
  load();
});

(async () => {
  try {
    const { characters } = await request("GET", "/api/characters");
    const ready = characters.filter((c) => !c.missing);
    if (!ready.length) {
      $("#rec-body").innerHTML = `<div class="card empty-card">${tr("キャラクターがいません。<a href=\"/login\">キャラクターを追加</a>してください。")}</div>`;
      return;
    }
    const saved = loadJson(REC_CHAR_KEY, null);
    charId = ready.some((c) => c.character_id === saved) ? saved : ready[0].character_id;
    fitCardCharId = charId;
    $("#rec-char").innerHTML = ready.map((c) =>
      `<option value="${c.character_id}" ${c.character_id === charId ? "selected" : ""}>${tr("{0}（{1} SP）", esc(c.character_name), fmtNum(c.total_sp))}</option>`).join("");
    await load();
  } catch (e) {
    toast(e.message, "error");
  }
})();
