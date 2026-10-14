"use strict";
// ミッション: 敵の勢力ごとの撃ってくる属性・弱い属性と、ミッションの検索（説明文・出てくる勢力）

const MS_KEY = "missions:params";
const DMG = ["em", "thermal", "kinetic", "explosive"];
const dmgLabel = (k) => ({ em: tr("EM"), thermal: tr("熱"), kinetic: tr("キネティック"), explosive: tr("爆発") }[k]);
// 属性ごとのミサイル・ドローン（弱点を突くときの目安）
const MISSILES = { em: "Mjolnir", thermal: "Inferno", kinetic: "Scourge", explosive: "Nova" };
const DRONES = { em: "Acolyte / Infiltrator / Praetor", thermal: "Hobgoblin / Hammerhead / Ogre", kinetic: "Hornet / Vespa / Wasp", explosive: "Warrior / Valkyrie / Berserker" };
// 海賊を先に、よく出会う順
const ORDER = [500010, 500020, 500011, 500012, 500019, 500025, 500018, 500001, 500004, 500003, 500002, 500008, 500015, 500006];
let factions = [];
let timer = null;

const pct = (v) => `${Math.round(v * 100)}%`;
const dot = (k) => `<span class="dmg-dot dmg-${k}"></span>`;

// 割合の大きい属性（1 位と、1 位に近いもの・2 割以上のもの）
function topTypes(values, { near = 0.05, min = 0.2 } = {}) {
  const order = DMG.map((k, i) => ({ k, v: values[i] })).sort((a, b) => b.v - a.v);
  return order.filter((x, i) => i === 0 || (i === 1 && (x.v >= min || order[0].v - x.v <= near))).map((x) => x.k);
}

function bars(values, sort = true) {
  const rows = DMG.map((k, i) => ({ k, v: values[i] }));
  if (sort) rows.sort((a, b) => b.v - a.v);
  return rows.map(({ k, v }) => `<div class="dmg-row"><span>${dot(k)}${dmgLabel(k)}</span>
    <span class="dmg-track"><span class="dmg-${k}" style="width:${Math.min(v, 1) * 100}%"></span></span><span class="num">${pct(v)}</span></div>`).join("");
}

function factionCard(f, size, extraClass = "") {
  const p = f.profiles[size] || f.profiles.all;
  const weak = topTypes(p.taken, { near: 0.06, min: 9 });  // 弱点は 1 位と、1 位に近いものだけ
  const layers = [tr("シールド"), tr("アーマー"), tr("ストラクチャー")].map((l, i) => `${l} ${pct(p.layers[i])}`).join(" · ");
  const dealt = p.dealt ? `<div><b>${tr("撃ってくる属性")}</b>${bars(p.dealt)}
      <small>${tr("上げる耐性: {0}", topTypes(p.dealt).map((k) => `${dot(k)}${dmgLabel(k)}`).join(LIST_SEP))}</small></div>`
    : `<div><b>${tr("撃ってくる属性")}</b><p class="muted">${tr("データがありません")}</p></div>`;
  return `<div class="card faction-card ${extraClass}" data-faction="${f.faction_id}">
    <h3>${esc(f.name)}</h3>
    <small class="muted">${tr("NPC {0} 種類から · HP の内訳: {1}", fmtNum(p.count), layers)}</small>
    ${dealt}
    <div><b>${tr("弱い属性（受けるダメージ）")}</b>${bars(p.taken)}
      <small>${tr("使う属性: {0}", weak.map((k) => `${dot(k)}${dmgLabel(k)}`).join(LIST_SEP))}</small><br>
      <small class="muted">${tr("ミサイル: {0} · ドローン: {1}", weak.map((k) => MISSILES[k]).join(" / "), weak.map((k) => DRONES[k]).join(" / "))}</small></div>
  </div>`;
}

function renderFactions() {
  const size = $("#ms-size").value;
  const sorted = [...factions].sort((a, b) => (ORDER.indexOf(a.faction_id) + 1 || 99) - (ORDER.indexOf(b.faction_id) + 1 || 99));
  $("#ms-factions").innerHTML = sorted.map((f) => factionCard(f, size)).join("");
}

function searchLinks(en) {
  const ddg = `https://duckduckgo.com/?q=${encodeURIComponent(`site:eve-survival.org "${en}"`)}`;
  return `<a class="btn small" href="${ddg}" target="_blank" rel="noopener">${tr("🔎 EVE-Survival で探す")}</a>
    <a class="btn small" href="https://eve-survival.org/?wakka=MissionReports" target="_blank" rel="noopener">${tr("📚 EVE-Survival のミッション一覧")}</a>`;
}

function renderResults(d) {
  const box = $("#ms-results");
  if (!d.results.length) {
    box.innerHTML = d.query.length < 2 ? "" : `<p class="muted">${tr("見つかりませんでした")}</p>`;
    return;
  }
  const size = $("#ms-size").value;
  box.innerHTML = d.results.map((r) => {
    const variants = r.variants.map((v) => {
      const mentioned = v.mentioned.map((m) => `<button class="btn small" type="button" data-show-faction="${m.faction_id}">${esc(m.name)}</button>`).join("");
      const data = v.faction_name && !v.mentioned.some((m) => m.faction_id === v.faction)
        ? `<small class="muted">${tr("データ上の勢力: {0}（依頼主のこともあります）", esc(v.faction_name))}</small>` : "";
      const cards = v.mentioned.slice(0, 2).map((m) => factions.find((f) => f.faction_id === m.faction_id)).filter(Boolean)
        .map((f) => factionCard(f, size)).join("");
      return `<div class="mission-variant">
        <div class="chip-row"><b>${tr("出てくる勢力（推定）")}</b>${mentioned || `<span class="muted">${tr("説明文に勢力の名前がありません（ゲームの目的の画面で確かめて、下の一覧を見てください）")}</span>`}${data}</div>
        ${cards ? `<div class="faction-grid">${cards}</div>` : ""}
        <details><summary>${tr("説明文")}</summary><p class="brief">${esc(v.brief)}</p></details></div>`;
    }).join("");
    return `<div class="card mission-result"><div class="section-head"><div><h3>${esc(r.name)}</h3>${r.name !== r.en ? `<small class="muted">${esc(r.en)}</small>` : ""}</div>
        <div class="chip-row">${searchLinks(r.en)}</div></div>
      <small class="muted">${tr("同じ名前のミッション {0} 件（勢力・レベル違い）", fmtNum(r.count))}</small>
      ${variants}${r.more ? `<small class="muted">${tr("ほか {0} 件", r.more)}</small>` : ""}</div>`;
  }).join("") + (d.total > d.results.length ? `<p class="muted small-note">${tr("{0} 件のうち {1} 件を表示しています。名前をもう少し詳しく入れてください。", fmtNum(d.total), d.results.length)}</p>` : "");
}

async function search() {
  const q = $("#ms-q").value.trim();
  saveJson(MS_KEY, { q, size: $("#ms-size").value });
  if (q.length < 2) { $("#ms-results").innerHTML = ""; return; }
  try {
    const d = await request("GET", `/api/missions/search?q=${encodeURIComponent(q)}`);
    if ($("#ms-q").value.trim() !== q) return;  // 入力が変わった
    renderResults(d);
  } catch (e) {
    $("#ms-results").innerHTML = `<div class="warn">${esc(e.message)}</div>`;
  }
}

$("#ms-q").addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(search, 300); });
$("#ms-size").addEventListener("change", () => { renderFactions(); search(); });
document.addEventListener("click", (ev) => {
  const btn = ev.target.closest("[data-show-faction]");
  if (!btn) return;
  const card = $(`#ms-factions [data-faction="${btn.dataset.showFaction}"]`);
  if (!card) return;
  document.querySelectorAll("#ms-factions .highlight").forEach((c) => c.classList.remove("highlight"));
  card.classList.add("highlight");
  card.scrollIntoView({ behavior: "smooth", block: "center" });
});

(async () => {
  const saved = loadJson(MS_KEY, null) || {};
  if (saved.size) $("#ms-size").value = saved.size;
  const q = new URLSearchParams(location.search).get("q") ?? saved.q;
  if (q) $("#ms-q").value = q;
  try {
    factions = (await request("GET", "/api/missions/factions")).factions;
    renderFactions();
    search();
  } catch (e) {
    $("#ms-factions").innerHTML = `<div class="warn">${esc(e.message)}</div>`;
  }
})();
