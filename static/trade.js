"use strict";
// ステーション内トレードの候補（Jita 4-4）

let timer = null;

function renderResult(job) {
  const r = job.result;
  const rows = r.items.map((i) => `<tr><td><b>${esc(nm(i))}</b><br><small class="muted">${nmSub(i)}</small></td>
    <td class="r num">${fmtIsk(i.buy)}<br><small class="muted">${tr("{0} 件", i.buy_orders)}</small></td><td class="r num">${fmtIsk(i.sell)}<br><small class="muted">${tr("{0} 件", i.sell_orders)}</small></td>
    <td class="r num ok-text">+${fmtIsk(i.profit)}</td><td class="r num">${fmtPct(i.margin, 1)}</td>
    <td class="r num">${fmtNum(Math.round(i.volume))}</td><td class="r num"><b>${fmtIsk(i.potential)}</b></td>
    <td><a class="btn small" href="/market?type_id=${i.type_id}">🛒</a></td></tr>`).join("");
  $("#tr-out").innerHTML = `<p class="muted small-note">${tr("{0} の注文 {1} 件（Jita 4-4 の {2} 品目）から · 売上税 {3}・仲介手数料 {4}", esc(fmtLocal(job.at)), fmtNum(r.orders), fmtNum(r.types), fmtPct(r.tax, 2), fmtPct(r.broker, 2))}</p>
    <div class="table-scroll"><table class="orders"><thead><tr><th>${tr("品目")}</th><th class="r">${tr("最高の買い値")}</th><th class="r">${tr("最安の売り値")}</th><th class="r">${tr("1 個の利益")}</th><th class="r">${tr("利益率")}</th>
      <th class="r">${tr("1 日の取引量")}<br><small>${tr("7 日平均")}</small></th><th class="r">${tr("1 日の利益の目安")}<br><small>${tr("取引量の 1 割")}</small></th><th></th></tr></thead>
    <tbody>${rows || `<tr><td colspan="8" class="muted">${tr("条件に合う品目がありません")}</td></tr>`}</tbody></table></div>
    <p class="muted small-note">${tr("注文の件数が多い品目は価格の更新競争が激しく、実際に約定させるのは大変です。出品数と取引量を見て判断してください。")}</p>`;
}

async function poll() {
  clearTimeout(timer);
  let job;
  try {
    job = await request("GET", "/api/tools/station-trade");
  } catch (e) {
    $("#tr-out").innerHTML = `<div class="warn">${esc(e.message)}</div>`;
    return;
  }
  if (job.state === "running") {
    $("#tr-out").innerHTML = `<p class="muted">${tr("注文を読み込んでいます… {0}%", job.progress)}</p><div class="mini-bar"><span style="width:${job.progress}%"></span></div>`;
    timer = setTimeout(poll, 1500);
  } else if (job.state === "error") {
    $("#tr-out").innerHTML = `<div class="warn">${esc(job.error)}</div>`;
  } else if (job.state === "ready") {
    renderResult(job);
  } else {
    $("#tr-out").innerHTML = `<p class="muted">${tr("「探す」を押してください。")}</p>`;
  }
}

$("#tr-run").addEventListener("click", async () => {
  try {
    await request("POST", "/api/tools/station-trade", {
      character_id: Number($("#tr-char").value), min_price: Number($("#tr-min-price").value), min_margin: Number($("#tr-min-margin").value),
    });
  } catch (e) {
    toast(e.message, "error");
  }
  poll();
});

(async () => {
  try {
    const { characters } = await request("GET", "/api/characters");
    const ready = characters.filter((c) => !c.missing)
      .sort((a, b) => (b.trade_skills.broker_relations + b.trade_skills.accounting) - (a.trade_skills.broker_relations + a.trade_skills.accounting));
    $("#tr-char").innerHTML = ready.map((c) => `<option value="${c.character_id}">${tr("{0}（Accounting {1}・Broker {2}）", esc(c.character_name), ROMAN[c.trade_skills.accounting], ROMAN[c.trade_skills.broker_relations])}</option>`).join("");
  } catch (e) {
    toast(e.message, "error");
  }
  poll();
})();
