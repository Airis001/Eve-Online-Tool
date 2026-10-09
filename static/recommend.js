"use strict";
// おすすめフィット: キャラクターのスキルで使えるフィット（役割ごと）

// カードの表示・ボタンの動作は fitcards.js にある

let data = null;
let charId = null;
const PAGE_PURPOSE = document.body.dataset.purpose || ""; // PvE・PvP のページでは、その用途の役割だけ

function renderRole(role, r) {
  const now = r.now.length ? r.now.map((e) => fitCard(e, false)).join("") : `<p class="muted">${tr("今のスキルで使えるフィットはありません。")}</p>`;
  const soon = r.soon.length ? r.soon.map((e) => fitCard(e, true)).join("") : `<p class="muted">${tr("10 日以内の訓練で使えるフィットはありません。")}</p>`;
  return `<section class="rec-role" id="role-${role}"><h2>${esc(r.label)}</h2>
    <div class="rec-cols"><div><h3>${tr("✓ 今すぐ使える")} <span class="muted">${r.now.length}</span></h3>${now}</div>
      <div><h3>${tr("⏳ 10 日以内の訓練で使える")} <span class="muted">${r.soon.length}</span></h3>${soon}</div></div></section>`;
}

function render() {
  fitsByKey.clear();
  const roles = data.roles.map((r) => [r.role, r]);
  $("#role-tabs").innerHTML = roles.map(([role, r]) =>
    `<a href="#role-${role}">${esc(r.label)} <small>${r.now.length} / ${r.soon.length}</small></a>`).join("");
  $("#rec-body").innerHTML = roles.map(([role, r]) => renderRole(role, r)).join("");
  hydrateJitaCosts($("#rec-body"));
}

async function load() {
  $("#rec-body").innerHTML = `<p class="muted">${tr("おすすめを計算しています…（初回は少し時間がかかります）")}</p>`;
  try {
    data = await request("GET", withBoostQuery(`/api/recommend/fits?character_id=${charId}${wcsQuery()}${PAGE_PURPOSE ? `&purpose=${PAGE_PURPOSE}` : ""}`));
  } catch (e) {
    $("#rec-body").innerHTML = `<div class="warn">${esc(e.message)}</div>`;
    return;
  }
  $("#rec-note").innerHTML = boostQuery()
    ? `<div class="alert boost"><span>${tr("🧠 スキルチェッカーで設定したブーストを、訓練時間の計算に反映しています。")}</span></div>` : "";
  render();
}

bindWcsToggle(() => load());

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
