"use strict";
// フィットの比較: 保存したフィット・ゲーム内のフィット・貼り付けた EFT を並べて比べる

const COMPARE_KEY = "compare:efts"; // 他のページの「⚖ 比較」から追加される EFT（最大 3）
const SLOTS = 3;
let fits = [];            // /api/fittings の保存・ゲーム内のフィット
let efts = (loadJson(COMPARE_KEY, []) || []).slice(0, SLOTS);
let results = [];

function slotHtml(i) {
  const options = fits.map((f, n) => `<option value="${n}">${esc(nm(f, "ship_ja", "ship_en"))} · ${esc(f.name)}</option>`).join("");
  return `<div class="card cp-slot"><h3>${tr("フィット {0}", i + 1)}</h3>
    <select data-pick="${i}"><option value="">${tr("保存・ゲーム内のフィットから選ぶ…")}</option>${options}</select>
    <textarea data-eft="${i}" rows="6" placeholder="${tr("または EFT を貼り付け")}">${esc(efts[i] || "")}</textarea>
    <button class="btn small" type="button" data-clear="${i}">${tr("空にする")}</button></div>`;
}

function renderSlots() {
  $("#cp-slots").innerHTML = Array.from({ length: SLOTS }, (_, i) => slotHtml(i)).join("");
}

async function evaluateAll() {
  saveJson(COMPARE_KEY, efts);
  const charId = Number($("#cp-char").value) || null;
  results = await Promise.all(efts.map(async (eft) => {
    if (!eft?.trim()) return null;
    try {
      const fit = await request("POST", "/api/fitbuilder/import", { eft });
      return await request("POST", "/api/fitbuilder/evaluate", { ...fit, character_id: charId });
    } catch (e) {
      return { error: e.message };
    }
  }));
  renderTable();
}

function best(values, higher = true) {
  const nums = values.filter((v) => typeof v === "number");
  if (nums.length < 2) return null;
  return higher ? Math.max(...nums) : Math.min(...nums);
}

function renderTable() {
  const cols = results.map((r, i) => ({ r, i })).filter((c) => c.r);
  if (!cols.length) { $("#cp-table").innerHTML = `<p class="muted">${tr("フィットを選ぶか、EFT を貼り付けてください。")}</p>`; return; }
  const row = (label, get, fmt = (v) => v, higher = true) => {
    const vals = cols.map((c) => (c.r.error ? null : get(c.r)));
    const b = best(vals, higher);
    return `<tr><th>${label}</th>${vals.map((v) => `<td class="r num ${b != null && v === b ? "ok-text" : ""}">${v == null ? "-" : fmt(v)}</td>`).join("")}</tr>`;
  };
  const res = (k) => (r) => r.resources[k].used;
  const hold = (k) => (r) => r.holds[k]?.total;
  const head = cols.map((c) => `<th class="r">${c.r.error ? `<span class="warn-text">${esc(c.r.error)}</span>` : `${esc(nm(c.r.ship))}<br><small class="muted">${esc(c.r.name)}</small>`}</th>`).join("");
  $("#cp-table").innerHTML = `<div class="table-scroll"><table class="orders cp-table"><thead><tr><th></th>${head}</tr></thead><tbody>
    ${row(tr("DPS（目安）"), (r) => r.dps.total, (v) => fmtNum(Math.round(v)))}
    ${row(tr("採掘（m³/秒）"), (r) => r.dps.mining?.total || null, (v) => v.toLocaleString(LOCALE, { maximumFractionDigits: 2 }))}
    ${row(tr("ドローン採掘（m³/秒）"), (r) => (r.dps.mining_m3_min ? r.dps.mining_m3_min / 60 : null), (v) => v.toLocaleString(LOCALE, { maximumFractionDigits: 2 }))}
    ${row(tr("ワープまで（秒）"), (r) => r.align.normal, (v) => v.toFixed(1), false)}
    ${row(tr("ワープコアの強度"), (r) => r.warp_strength.base + r.warp_strength.wcs)}
    ${row(tr("パワーグリッド 使用"), res("power"), (v) => fmtNum(Math.round(v)), false)}
    ${row(tr("CPU 使用"), res("cpu"), (v) => fmtNum(Math.round(v)), false)}
    ${row(tr("カーゴ（m³）"), hold("cargo"), (v) => fmtNum(Math.round(v)))}
    ${row(tr("ドローンベイ（m³）"), hold("drone_bay"), (v) => fmtNum(Math.round(v)))}
    ${row(tr("採掘カーゴ（m³）"), hold("mining_hold"), (v) => fmtNum(Math.round(v)))}
    ${row(tr("訓練時間（分）"), (r) => (r.skills.usable ? 0 : r.skills.minutes), (v) => (v ? esc(fmtMinutes(v)) : tr("✓ 今すぐ")), false)}
    <tr><th>${tr("装着の問題")}</th>${cols.map((c) => `<td><small class="${c.r.errors?.length ? "warn-text" : "ok-text"}">${c.r.error ? "" : c.r.errors.length ? c.r.errors.map(esc).join("<br>") : tr("✓ なし")}</small></td>`).join("")}</tr>
    <tr><th>${tr("購入費")}</th>${cols.map((c) => `<td>${c.r.error ? "" : `<div class="rec-cost" data-bom="${c.r.bom.map(([t, q, k]) => `${t}:${q}:${k}`).join(",")}" data-has-bay="${c.r.bom.some(([, , k]) => k === "bay") ? 1 : ""}"></div>`}</td>`).join("")}</tr>
    <tr><th></th>${cols.map((c) => `<td>${c.r.error ? "" : `<button class="btn small" type="button" data-open="${c.i}">${tr("✏️ 編集")}</button>`}</td>`).join("")}</tr>
  </tbody></table></div><p class="muted small-note">${tr("緑は一番良い値です。数値は目安です。")}</p>`;
  hydrateJitaCosts($("#cp-table"));
}

$("#cp-slots").addEventListener("change", (ev) => {
  const pick = ev.target.closest("[data-pick]");
  if (pick && pick.value !== "") {
    const i = Number(pick.dataset.pick);
    efts[i] = fits[Number(pick.value)].eft;
    document.querySelector(`[data-eft="${i}"]`).value = efts[i];
    evaluateAll();
  }
});
$("#cp-slots").addEventListener("input", (ev) => {
  const t = ev.target.closest("[data-eft]");
  if (!t) return;
  efts[Number(t.dataset.eft)] = t.value;
  clearTimeout(t._timer);
  t._timer = setTimeout(evaluateAll, 600);
});
$("#cp-slots").addEventListener("click", (ev) => {
  const b = ev.target.closest("[data-clear]");
  if (!b) return;
  efts[Number(b.dataset.clear)] = "";
  renderSlots();
  evaluateAll();
});
$("#cp-table").addEventListener("click", (ev) => {
  const b = ev.target.closest("[data-open]");
  if (!b) return;
  saveJson("fitbuilder:eft", efts[Number(b.dataset.open)]);
  location.href = "/fitting";
});
$("#cp-char").addEventListener("change", evaluateAll);

(async () => {
  try {
    const [{ characters }, f] = await Promise.all([request("GET", "/api/characters"), request("GET", "/api/fittings")]);
    fits = f.fittings.filter((x) => x.eft);
    const saved = loadJson(REC_CHAR_KEY, null);
    $("#cp-char").innerHTML = characters.filter((c) => !c.missing).map((c) => `<option value="${c.character_id}" ${c.character_id === saved ? "selected" : ""}>${esc(c.character_name)}</option>`).join("")
      + `<option value="">${tr("全スキル V")}</option>`;
  } catch (e) {
    toast(e.message, "error");
  }
  renderSlots();
  evaluateAll();
})();
