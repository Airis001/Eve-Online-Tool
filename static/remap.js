"use strict";
// 属性の割り振り: スキルキュー・スキルプランを一番速く訓練できる属性

const ORDER = ["perception", "memory", "willpower", "intelligence", "charisma"];

function attrTable(d, attrs, highlight) {
  return `<table class="orders rm-attrs"><tbody>${ORDER.map((a) => `<tr><td>${esc(nm(d, "attr_ja", "attr_en")[a])}</td>
    <td class="r num ${highlight && attrs[a] !== d.base[a] ? "ok-text" : ""}"><b>${attrs[a]}</b></td></tr>`).join("")}</tbody></table>`;
}

async function run() {
  const box = $("#rm-out");
  box.innerHTML = `<p class="muted">${tr("計算しています…")}</p>`;
  let d;
  try {
    d = await request("POST", "/api/tools/remap", { character_id: Number($("#rm-char").value), mode: $("#rm-mode").value, text: $("#rm-text").value });
  } catch (e) {
    box.innerHTML = `<div class="warn">${esc(e.message)}</div>`;
    return;
  }
  const saved = d.current.minutes - d.best.minutes;
  const card = (title, minutes, extra = "", best = false) => `<div class="stat-card${best ? " total" : ""}"><small class="muted">${title}</small>
    <b>${esc(fmtMinutes(minutes))}</b>${minutes < d.current.minutes - 1 ? `<small class="ok-text">${tr("今より {0} 短い", esc(fmtMinutes(d.current.minutes - minutes)))}</small>` : `<small class="muted">${extra}</small>`}</div>`;
  const hasImplants = ORDER.some((a) => d.implant_bonus[a]);
  box.innerHTML = `<p class="muted small-note">${tr("{0} · {1} 手順 · {2} SP", esc(d.character_name), fmtNum(d.skills), fmtNum(Math.round(d.sp)))}</p>
    <div class="stat-row">
      ${card(tr("今の属性のまま"), d.current.minutes, tr("今の属性"))}
      ${card(tr("最適な割り振り（今のインプラント）"), d.best.minutes, "", true)}
      ${card(tr("今の割り振り＋ +5 インプラント"), d.current_plus5.minutes)}
      ${card(tr("最適な割り振り＋ +5 インプラント"), d.best_plus5.minutes, "", true)}
    </div>
    <div class="cols">
      <div class="card"><h3>${tr("今の属性 <small class=\"muted\">{0}</small>", hasImplants ? tr("インプラント込み") : "")}</h3>${attrTable(d, d.current.attrs)}</div>
      <div class="card"><h3>${tr("最適な割り振り <small class=\"muted\">インプラントの前（リマップで設定する値）</small>")}</h3>${attrTable(d, d.best.attrs, true)}
        <p class="small-note">${saved > 1 ? `${tr("この割り振りにすると <b class=\"ok-text\">{0}</b> 短くなります。", esc(fmtMinutes(saved)))}` : tr("今の割り振りがほぼ最適です。")}
          ${d.bonus_remaps != null ? `${tr("ボーナスリマップ: 残り {0} 回。", d.bonus_remaps)}` : ""}${d.remap_available ? ` ${tr("次の通常のリマップ: {0}", esc(fmtLocal(d.remap_available)))}` : ""}</p></div>
    </div>
    <p class="muted small-note">${tr("属性は各 17〜27、追加の 14 ポイントを振り分けます。訓練時間は Omega クローン（主属性 + 副属性 ÷ 2）で計算し、加速器（ブースター）は含めません。")}</p>`;
}

$("#rm-mode").addEventListener("change", () => { $("#rm-text").hidden = $("#rm-mode").value !== "text"; });
$("#rm-run").addEventListener("click", run);

(async () => {
  try {
    const { characters } = await request("GET", "/api/characters");
    const ready = characters.filter((c) => !c.missing);
    const saved = loadJson(REC_CHAR_KEY, null);
    $("#rm-char").innerHTML = ready.map((c) => `<option value="${c.character_id}" ${c.character_id === saved ? "selected" : ""}>${esc(c.character_name)}</option>`).join("");
    if (ready.length) run();
  } catch (e) {
    toast(e.message, "error");
  }
})();
