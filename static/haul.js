"use strict";
// ハブ間の転売: 交易ハブで買って別のハブで売ると利益が出る品目と、そのあいだの安全なルート

const HAUL_KEY = "haul:params";
let timer = null;
let hubs = [];

const hubName = (id) => hubs.find((h) => h.station_id === id)?.name || id;

function methodLabel(i) {
  return i.method === "instant" ? `<span class="badge ok">${tr("すぐ売る")}</span>` : `<span class="badge queued">${tr("売り注文")}</span>`;
}

function renderResult(job) {
  const r = job.result;
  const cargo = r.cargo > 0;
  const rows = r.items.map((i) => `<tr><td><b>${esc(nm(i))}</b><br><small class="muted">${nmSub(i)}</small></td>
    <td class="r num">${fmtIsk(i.cost)}<br><small class="muted">${tr("{0} 個", fmtNum(i.src_qty))}</small></td>
    <td class="r num">${i.dst_buy != null ? fmtIsk(i.dst_buy) : "-"}<br><small class="muted">${tr("{0} 件", i.dst_buy_orders)}</small></td>
    <td class="r num">${i.dst_sell != null ? fmtIsk(i.dst_sell) : "-"}<br><small class="muted">${tr("{0} 件", i.dst_sell_orders)}</small></td>
    <td class="r num ok-text">+${fmtIsk(i.profit)}<br>${methodLabel(i)}</td><td class="r num">${fmtPct(i.margin, 1)}</td>
    <td class="r num">${fmtNum(Math.round(i.volume))}<br><small class="muted">${tr("平均 {0}", fmtIsk(i.average))}</small></td>
    <td class="r num">${i.recent_orders != null ? `${tr("<b>{0}</b> 件", fmtNum(i.recent_orders))}` : "-"}<br><small class="muted">${i.recent_volume != null ? `${tr("{0} 個", fmtNum(i.recent_volume))}` : ""}</small></td>
    <td class="r num">${i.m3 != null ? i.m3.toLocaleString(LOCALE, { maximumFractionDigits: 2 }) : "-"}<br><small class="muted">${i.per_m3 != null ? `${fmtIsk(i.per_m3)}/m³` : ""}</small></td>
    ${cargo ? `<td class="r num">${i.load ? `${tr("{0} 個", fmtNum(i.load))}<br><b>${fmtIsk(i.load_profit)}</b>` : i.load === 0 ? `<small class="warn-text">${tr("積めません")}</small>` : "-"}</td>` : ""}
    <td class="r num"><b>${fmtIsk(i.potential)}</b></td>
    <td><a class="btn small" href="/market?type_id=${i.type_id}" title="${tr("マーケットで見る")}">🛒</a></td></tr>`).join("");
  $("#hl-out").innerHTML = `<h2>${tr("📦 {0} で買って {1} で売る", esc(r.src_name), esc(r.dst_name))}</h2>
    <p class="muted small-note">${tr("{0} の注文 {1} 件から · 手数料（{2}・{3}）売上税 {4}・仲介手数料 {5}", esc(fmtLocal(job.at)), fmtNum(r.orders), esc(r.trader || "-"), esc(r.dst_name), fmtPct(r.tax, 2), fmtPct(r.broker, 2))}</p>
    <div class="table-scroll"><table class="orders"><thead><tr><th>${tr("品目")}</th>
      <th class="r">${tr("仕入れ値")}<br><small>${tr("{0} 最安・買える数", esc(r.src_name))}</small></th>
      <th class="r">${tr("売り先の買い値")}<br><small>${tr("最高・注文数")}</small></th><th class="r">${tr("売り先の売り値")}<br><small>${tr("最安・注文数")}</small></th>
      <th class="r">${tr("1 個の利益")}<br><small>${tr("手数料込み")}</small></th><th class="r">${tr("利益率")}</th>
      <th class="r">${tr("売り先の取引量")}<br><small>${tr("1 日（7 日平均）")}</small></th><th class="r">${tr("直近 2 日の取引")}<br><small>${tr("件数・数量")}</small></th><th class="r">${tr("大きさ")}<br><small>${tr("m³（梱包時）")}</small></th>
      ${cargo ? `<th class="r">${tr("カーゴ {0} m³", fmtNum(r.cargo))}<br><small>${tr("積める数・利益")}</small></th>` : ""}
      <th class="r">${tr("1 日の利益の目安")}<br><small>${tr("取引量の 1 割")}</small></th><th></th></tr></thead>
    <tbody>${rows || `<tr><td colspan="12" class="muted">${tr("条件に合う品目がありません")}</td></tr>`}</tbody></table></div>
    <p class="muted small-note">${tr("「すぐ売る」は売り先の買い注文に売る場合（売上税のみ）、「売り注文」は最安より 0.01 ISK 安く出品する場合（売上税＋仲介手数料、売れるまで待つ）の利益です。 仕入れの「買える数」は最安の 2% 以内の値段で売られている数量です。「直近 2 日の取引」は、売り先の地域で直近 2 日間に成立した取引の件数と数量です（ESI の履歴。当日の分は翌日に反映されます）。「1 日の利益の目安」は、売り先の取引量の 1 割（と買える数の少ない方）を毎日売れた場合です。 運んでいるあいだに価格が変わることがあります。実際の取引価格（7 日平均）から大きく外れた注文（釣り）は除いています。")}</p>`;
}

async function poll() {
  clearTimeout(timer);
  let job;
  try {
    job = await request("GET", "/api/haul");
  } catch (e) {
    $("#hl-out").innerHTML = `<div class="warn">${esc(e.message)}</div>`;
    return;
  }
  if (job.state === "running") {
    $("#hl-out").innerHTML = `<p class="muted">${tr("注文を読み込んでいます… {0}%", job.progress)}</p><div class="mini-bar"><span style="width:${job.progress}%"></span></div>`;
    timer = setTimeout(poll, 1500);
  } else if (job.state === "error") {
    $("#hl-out").innerHTML = `<div class="warn">${esc(job.error)}</div>`;
  } else if (job.state === "ready") {
    renderResult(job);
  } else {
    $("#hl-out").innerHTML = `<p class="muted">${tr("「探す」を押してください。")}</p>`;
  }
}

async function loadRoute(src, dst) {
  const box = $("#hl-route");
  box.innerHTML = `<div class="card"><p class="muted">${tr("安全なルートを調べています…")}</p></div>`;
  const params = { from_station: src, to_station: dst, flag: $("#hl-flag").value, min_sec: $("#hl-minsec").value, max_low: $("#hl-maxlow").value, autopilot: 1,
    character_id: gameCharId(), ship: $("#hl-ship").value.trim() };
  try {
    const d = await request("GET", `/api/travel/route?${new URLSearchParams(params)}`);
    const dest = d.systems[d.systems.length - 1];
    box.innerHTML = `<div class="card"><div class="route-head"><div>${tr("🗺 <b>{0} → {1}</b> · {2}で <b>{3}</b> ジャンプ {4} · 直近 1 時間の撃墜 {5}{6}", esc(hubName(src)), esc(hubName(dst)), esc(d.flag_label), d.jumps, routeSafetyHtml(d), d.ship_kills, autopilotHtml(d.autopilot))}</div>
      <div class="fit-actions">${routeGameButton(d)}<button class="btn" type="button" data-dest="${dest.id}" data-name="${esc(dest.name)}">${tr("🎯 目的地に設定")}</button>
        <a class="btn small" href="/travel">${tr("ルートの詳細（移動）")}</a></div></div></div>`;
  } catch (e) {
    box.innerHTML = `<div class="warn">${esc(e.message)}</div>`;
  }
}

function toggleMinSec() {
  $("#hl-minsec-label").hidden = $("#hl-flag").value !== "highsec";
  $("#hl-maxlow-label").hidden = $("#hl-flag").value !== "highsec";
}
$("#hl-flag").addEventListener("change", toggleMinSec);

// 目的地の設定（ゲームのルートの設定どおりに進む）
document.addEventListener("click", (ev) => {
  const dest = ev.target.closest("[data-dest]");
  if (dest) gameAction("/api/ui/waypoint", { destination_id: Number(dest.dataset.dest), clear: true }, `${tr("目的地を {0} に設定しました", dest.dataset.name)}`);
});

$("#hl-run").addEventListener("click", async () => {
  const src = Number($("#hl-src").value);
  const dst = Number($("#hl-dst").value);
  if (src === dst) { toast(tr("仕入れ先と売り先に、ちがう交易ハブを選んでください。"), "error"); return; }
  const params = { src, dst, min_price: Number($("#hl-min-price").value), min_margin: Number($("#hl-min-margin").value),
    cargo: Number($("#hl-cargo").value) || 0 };
  saveJson(HAUL_KEY, { ...params, ship: $("#hl-ship").value.trim(), flag: $("#hl-flag").value, min_sec: $("#hl-minsec").value, max_low: $("#hl-maxlow").value });
  loadRoute(src, dst);
  try {
    await request("POST", "/api/haul", params);
  } catch (e) {
    toast(e.message, "error");
  }
  poll();
});

(async () => {
  try {
    const [{ characters }, h] = await Promise.all([request("GET", "/api/characters"), request("GET", "/api/haul/hubs")]);
    hubs = h.hubs;
    $("#game-char").innerHTML = gameCharSelect(characters.filter((c) => !c.missing));
    const options = hubs.map((x) => `<option value="${x.station_id}">${esc(x.name)}</option>`).join("");
    $("#hl-src").innerHTML = options;
    $("#hl-dst").innerHTML = options;
    const saved = loadJson(HAUL_KEY, null) || {};
    $("#hl-src").value = saved.src || hubs[0].station_id;
    $("#hl-dst").value = saved.dst || hubs[1].station_id;
    if (saved.min_price != null) $("#hl-min-price").value = saved.min_price;
    if (saved.min_margin != null) $("#hl-min-margin").value = saved.min_margin;
    if (saved.cargo) $("#hl-cargo").value = saved.cargo;
    if (saved.ship) $("#hl-ship").value = saved.ship;
    $("#hl-flag").innerHTML = routeFlagOptions(saved.flag || "highsec");
    $("#hl-minsec").innerHTML = minSecOptions(saved.min_sec || 0.5);
    $("#hl-maxlow").innerHTML = maxLowOptions(saved.max_low || 0);
    toggleMinSec();
  } catch (e) {
    toast(e.message, "error");
  }
  poll();
})();
