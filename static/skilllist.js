"use strict";
// スキル一覧: 選んだキャラクターの全スキルをグループごとに表示してコピー

const SL_KEY = "skilllist:settings";
let data = null;
const settings = { show: "trained", lang: "ja", sort: "group", ...loadJson(SL_KEY, {}) };

const nameOf = (s) => (settings.lang === "en" ? s.en : settings.lang === "both" ? `${tr("{0}（{1}）", nm(s), s.en)}` : nm(s));
const groupOf = (s) => (settings.lang === "en" ? s.group : nm(s, "group_ja", "group"));

function visibleSkills() {
  if (!data) return [];
  let list = settings.show === "trained" ? data.skills : settings.show === "missing" ? data.not_injected : [...data.skills, ...data.not_injected];
  const q = $("#sl-filter").value.trim().toLowerCase();
  if (q) list = list.filter((s) => [nm(s), s.en, s.group, nm(s, "group_ja", "group")].some((v) => (v || "").toLowerCase().includes(q)));
  const by = {
    group: (a, b) => groupOf(a).localeCompare(groupOf(b)) || nameOf(a).localeCompare(nameOf(b)),
    level: (a, b) => b.level - a.level || b.sp - a.sp,
    sp: (a, b) => b.sp - a.sp,
    name: (a, b) => nameOf(a).localeCompare(nameOf(b)),
  }[settings.sort];
  return [...list].sort(by);
}

function levelCell(s) {
  if (!s.injected) return `<span class="muted">${tr("未注入")}</span>`;
  const pips = [1, 2, 3, 4, 5].map((i) => `<span class="pip ${i <= s.level ? "on" : s.queued && i <= s.queued ? "queued" : ""}"></span>`).join("");
  return `<span class="pips">${pips}</span> <b>${ROMAN[s.level]}</b>${s.queued && s.queued > s.level ? ` <small class="muted">${tr("→ {0}（キュー）", ROMAN[s.queued])}</small>` : ""}`;
}

function render() {
  const list = visibleSkills();
  const d = data;
  const five = d.skills.filter((s) => s.level === 5).length;
  $("#sl-summary").innerHTML = `<div class="stat-row">
    <div class="stat-card total"><small class="muted">${tr("{0} の合計 SP", esc(d.character_name))}</small><b>${fmtNum(d.total_sp)}</b>
      <small class="muted">${tr("未割り当て {0}", fmtNum(d.unallocated_sp))}</small></div>
    <div class="stat-card"><small class="muted">${tr("習得済みのスキル")}</small><b>${fmtNum(d.skills.length)}</b><small class="muted">${tr("V は {0}", fmtNum(five))}</small></div>
    <div class="stat-card"><small class="muted">${tr("未注入のスキル")}</small><b>${fmtNum(d.not_injected.length)}</b></div>
    <div class="stat-card"><small class="muted">${tr("データの取得")}</small><b>${esc(fmtLocal(d.fetched_at))}</b><small class="muted">${tr("<a href=\"/skills\">スキルチェッカー</a>で更新")}</small></div></div>`;
  if (!list.length) { $("#sl-body").innerHTML = `<p class="muted">${tr("該当するスキルはありません。")}</p>`; return; }
  const row = (s) => `<tr class="${s.injected ? "" : "muted-row"}"><td>${esc(nameOf(s))}</td><td>${levelCell(s)}</td><td class="r num">${s.injected ? fmtNum(s.sp) : "-"}</td></tr>`;
  if (settings.sort !== "group") {
    $("#sl-body").innerHTML = `<p class="muted small-note">${tr("{0} スキル", list.length)}</p><div class="table-scroll"><table class="orders sl-table"><thead><tr><th>${tr("スキル")}</th><th>${tr("レベル")}</th><th class="r">SP</th></tr></thead>
      <tbody>${list.map(row).join("")}</tbody></table></div>`;
    return;
  }
  const groups = new Map();
  list.forEach((s) => { if (!groups.has(groupOf(s))) groups.set(groupOf(s), []); groups.get(groupOf(s)).push(s); });
  $("#sl-body").innerHTML = `<p class="muted small-note">${tr("{0} スキル・{1} グループ", list.length, groups.size)}</p><div class="sl-groups">${[...groups].map(([g, rows]) => {
    const sp = rows.reduce((t, s) => t + s.sp, 0);
    return `<div class="card sl-group"><h3>${esc(g)} <small class="muted">${tr("{0} スキル · {1} SP", rows.filter((s) => s.injected).length, fmtNum(sp))}</small></h3>
      <table class="orders sl-table"><tbody>${rows.map(row).join("")}</tbody></table></div>`;
  }).join("")}</div>`;
}

function copyText(kind) {
  const list = visibleSkills();
  if (!list.length) { toast(tr("コピーするスキルがありません。"), "error"); return null; }
  if (kind === "plan") return list.filter((s) => s.injected && s.level > 0).map((s) => `${s.en} ${s.level}`).join("\n");
  if (kind === "tsv") {
    return [tr("グループ\tスキル\t英語名\tレベル\tSP"), ...list.map((s) => `${nm(s, "group_ja", "group")}\t${nm(s)}\t${s.en}\t${s.injected ? s.level : tr("未注入")}\t${s.sp}`)].join("\n");
  }
  const lines = [`${tr("{0} のスキル（合計 {1} SP）", data.character_name, fmtNum(data.total_sp))}`];
  let group = null;
  for (const s of list) {
    if (settings.sort === "group" && groupOf(s) !== group) {
      group = groupOf(s);
      lines.push("", `■ ${group}`);
    }
    lines.push(`${nameOf(s)} ${s.injected ? ROMAN[s.level] : tr("（未注入）")}`);
  }
  return lines.join("\n");
}

document.querySelector(".sl-controls").addEventListener("click", async (ev) => {
  const b = ev.target.closest("[data-copy]");
  if (!b) return;
  const text = copyText(b.dataset.copy);
  if (text == null) return;
  await navigator.clipboard.writeText(text);
  toast(`${tr("{0} 行をコピーしました。", text.split("\n").length)}`, "ok");
});

for (const [id, key] of [["#sl-show", "show"], ["#sl-lang", "lang"], ["#sl-sort", "sort"]]) {
  $(id).value = settings[key];
  $(id).addEventListener("change", () => { settings[key] = $(id).value; saveJson(SL_KEY, settings); render(); });
}
$("#sl-filter").addEventListener("input", () => render());

async function load() {
  $("#sl-body").innerHTML = `<p class="muted">${tr("読み込み中…")}</p>`;
  try {
    data = await request("GET", `/api/skill-list?character_id=${$("#sl-char").value}`);
    render();
  } catch (e) {
    $("#sl-body").innerHTML = `<div class="warn">${esc(e.message)}</div>`;
  }
}

$("#sl-char").addEventListener("change", () => { saveJson("skilllist:character", Number($("#sl-char").value)); load(); });

(async () => {
  try {
    const { characters } = await request("GET", "/api/characters");
    const ready = characters.filter((c) => !c.missing);
    if (!ready.length) { $("#sl-body").innerHTML = `<div class="card empty-card">${tr("キャラクターがいません。<a href=\"/login\">キャラクターを追加</a>してください。")}</div>`; return; }
    const saved = loadJson("skilllist:character", null);
    $("#sl-char").innerHTML = ready.map((c) => `<option value="${c.character_id}" ${c.character_id === saved ? "selected" : ""}>${tr("{0}（{1} SP）", esc(c.character_name), fmtNum(c.total_sp))}</option>`).join("");
    load();
  } catch (e) {
    toast(e.message, "error");
  }
})();
