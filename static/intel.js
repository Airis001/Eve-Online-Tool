"use strict";
// 情報: ローカルの危険度・D-Scan の整理・星系の最近の撃墜

const LEVEL = { high: `<span class="badge missing">${tr("危険")}</span>`, mid: `<span class="badge queued">${tr("注意")}</span>`, low: `<span class="badge ok">${tr("低")}</span>` };

async function post(url, body, box) {
  box.innerHTML = `<p class="muted">${tr("調べています…")}</p>`;
  try {
    return await request("POST", url, body);
  } catch (e) {
    box.innerHTML = `<div class="warn">${esc(e.message)}</div>`;
    return null;
  }
}

// ---------- ローカル ----------

$("#lc-run").addEventListener("click", async () => {
  const box = $("#lc-out");
  const d = await post("/api/tools/local", { text: $("#lc-text").value }, box);
  if (!d) return;
  const high = d.pilots.filter((p) => p.level === "high").length;
  box.innerHTML = `<div class="stat-row">
      <div class="stat-card ${high ? "total" : ""}"><small class="muted">${tr("パイロット")}</small><b>${tr("{0} 人", d.pilots.length)}</b><small class="${high ? "warn-text" : "muted"}">${tr("危険 {0} 人", high)}</small></div>
      ${d.groups.slice(0, 5).map((g) => `<div class="stat-card"><small class="muted">${esc(g.name)}</small><b>${tr("{0} 人", g.count)}</b></div>`).join("")}</div>
    ${d.not_found.length ? `<p class="muted small-note">${tr("見つからない名前: {0}", esc(d.not_found.join(LIST_SEP)))}</p>` : ""}
    <div class="table-scroll"><table class="orders"><thead><tr><th>${tr("危険度")}</th><th>${tr("パイロット")}</th><th>${tr("所属")}</th><th class="r">${tr("撃墜 / 損失")}</th><th class="r">${tr("危険度（%）")}</th><th class="r">${tr("最近の関与")}</th><th></th></tr></thead>
    <tbody>${d.pilots.map((p) => `<tr><td>${LEVEL[p.level]}</td><td><b>${esc(p.name)}</b></td>
      <td><small>${esc(p.corporation || "")}${p.alliance ? `<br><span class="muted">${esc(p.alliance)}</span>` : ""}</small></td>
      <td class="r num">${p.checked ? `${fmtNum(p.kills)} / ${fmtNum(p.losses)}` : "-"}${p.solo ? `<br><small class="muted">${tr("ソロ {0}", fmtNum(p.solo))}</small>` : ""}</td>
      <td class="r num">${p.danger != null ? p.danger : "-"}${p.gang != null ? `<br><small class="muted">${tr("集団 {0}", p.gang)}</small>` : ""}</td>
      <td class="r num">${p.recent_kills || "-"}</td>
      <td><a class="btn small" href="${esc(p.zkill)}" target="_blank" rel="noopener noreferrer">zKill</a></td></tr>`).join("")}</tbody></table></div>
    <p class="muted small-note">${tr("危険度（%）は zKillboard の dangerRatio（撃墜の多さの目安）、集団は gangRatio（集団での撃墜の割合）、最近の関与は直近に撃墜・損失に関わった数です。")}</p>`;
});

// ---------- D-Scan ----------

$("#ds-run").addEventListener("click", async () => {
  const box = $("#ds-out");
  const d = await post("/api/tools/dscan", { text: $("#ds-text").value }, box);
  if (!d) return;
  box.innerHTML = `<div class="stat-row">
      <div class="stat-card total"><small class="muted">${tr("艦")}</small><b>${d.ship_count}</b><small class="muted">${tr("全 {0} 件・グリッド内（7,500km 以内）{1}", d.total, d.on_grid)}</small></div>
      ${d.classes.map((c) => `<div class="stat-card"><small class="muted">${esc(c.class)}</small><b>${c.count}</b></div>`).join("")}</div>
    <div class="cols">
      <div class="card"><h3>${tr("艦の種類")}</h3><table class="orders"><tbody>${d.ships.map((s) => `<tr><td><b>${esc(nm(s))}</b><br><small class="muted">${esc(s.group || "")}</small></td>
        <td class="muted"><small>${esc(s.class)}</small></td><td class="r num"><b>${s.count}</b></td></tr>`).join("") || `<tr><td class="muted">${tr("艦はありません")}</td></tr>`}</tbody></table></div>
      <div class="card"><h3>${tr("艦以外")}</h3><table class="orders"><tbody>${d.others.map((o) => `<tr><td>${esc(nm(o))}</td><td class="r num">${o.count}</td></tr>`).join("") || `<tr><td class="muted">${tr("なし")}</td></tr>`}</tbody></table></div>
    </div>`;
});

// ---------- 星系の撃墜 ----------

async function systemKills() {
  const box = $("#sk-out");
  const system = $("#sk-system").value.trim();
  if (!system) { toast(tr("星系名を入力してください。"), "error"); return; }
  saveJson("intel:system", system);
  box.innerHTML = `<p class="muted">${tr("調べています…")}</p>`;
  let d;
  try {
    d = await request("GET", `/api/tools/system-kills?system=${encodeURIComponent(system)}`);
  } catch (e) {
    box.innerHTML = `<div class="warn">${esc(e.message)}</div>`;
    return;
  }
  const ago = (m) => (m < 60 ? `${tr("{0} 分前", Math.round(m))}` : m < 1440 ? `${tr("{0} 時間前", Math.round(m / 60))}` : `${tr("{0} 日前", Math.round(m / 1440))}`);
  box.innerHTML = `<div class="stat-row">
      <div class="stat-card ${d.camp ? "total" : ""}"><small class="muted">${esc(d.system || "")}</small><b class="${d.camp ? "warn-text" : ""}">${d.camp ? tr("⚠ キャンプの可能性") : d.last_hour ? tr("注意") : tr("最近の撃墜は少なめ")}</b></div>
      <div class="stat-card"><small class="muted">${tr("直近 1 時間")}</small><b>${tr("{0} 件", d.last_hour)}</b></div>
      <div class="stat-card"><small class="muted">${tr("直近 24 時間")}</small><b>${tr("{0} 件", d.last_day)}</b></div></div>
    <div class="table-scroll"><table class="orders"><thead><tr><th>${tr("時間")}</th><th>${tr("被害")}</th><th>${tr("とどめ")}</th><th class="r">${tr("攻撃側")}</th><th class="r">${tr("金額")}</th><th></th></tr></thead>
    <tbody>${d.kills.map((k) => `<tr class="${k.minutes_ago <= 60 ? "danger-row" : ""}"><td><small>${esc(ago(k.minutes_ago))}</small></td>
      <td><b>${esc(k.victim_ship)}</b><br><small class="muted">${esc(k.victim)}${k.victim_group ? ` · ${esc(k.victim_group)}` : ""}</small></td>
      <td>${esc(k.final_ship)}<br><small class="muted">${esc(k.final_blow)}${k.attacker_group ? ` · ${esc(k.attacker_group)}` : ""}</small></td>
      <td class="r num">${k.attackers}</td><td class="r num">${k.value != null ? fmtIsk(k.value) : "-"}</td>
      <td><a class="btn small" href="${esc(k.url)}" target="_blank" rel="noopener noreferrer">zKill</a></td></tr>`).join("") || `<tr><td colspan="6" class="muted">${tr("最近の撃墜はありません")}</td></tr>`}</tbody></table></div>`;
}

$("#sk-run").addEventListener("click", systemKills);
$("#sk-system").addEventListener("keydown", (ev) => { if (ev.key === "Enter") systemKills(); });
$("#sk-system").value = loadJson("intel:system", "") || "";
