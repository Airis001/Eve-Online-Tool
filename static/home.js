"use strict";
// ホーム: 各ページへの入口と、キャラクターの状況の一覧

const QUEUE_WARN_MS = 24 * 60 * 60 * 1000;

function queueState(c) {
  if (c.missing) return { text: tr("未取得"), cls: "muted" };
  if (!c.queue_length) return { text: tr("⚠ 空"), cls: "warn-text" };
  const end = new Date(c.queue_end).getTime();
  if (end < Date.now() + QUEUE_WARN_MS) return { text: `⚠ ${fmtLocal(c.queue_end)}`, cls: "warn-text" };
  return { text: fmtLocal(c.queue_end), cls: "" };
}

function renderCharacters(chars) {
  if (!chars.length) {
    $("#characters").innerHTML = `<div class="card empty-card">${tr("キャラクターがいません。<a href=\"/login\">キャラクターを追加</a>してください。")}</div>`;
    return;
  }
  const rows = chars.map((c) => {
    const q = queueState(c);
    const relogin = c.missing_scopes?.length ? ` <span class="badge queued" title="${tr("新しい機能の権限を許可するため")}">${tr("再ログインが必要")}</span>` : "";
    return `<tr><td>${esc(c.character_name)}${relogin}</td>
      <td class="r num">${c.missing ? "-" : fmtNum(c.total_sp)}</td>
      <td class="r num">${c.missing ? "-" : fmtNum(c.unallocated_sp)}</td>
      <td class="${q.cls}">${esc(q.text)}</td>
      <td class="muted">${c.missing ? "-" : esc(fmtLocal(c.fetched_at))}</td></tr>`;
  }).join("");
  $("#characters").innerHTML = `<div class="table-scroll"><table class="matrix home-table">
    <thead><tr><th>${tr("キャラクター")}</th><th class="r">${tr("総 SP")}</th><th class="r">${tr("未割り当て SP")}</th><th>${tr("キュー完了")}</th><th>${tr("取得日時")}</th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
}

// ---------- やることリスト ----------

const TODO_SEEN_KEY = "todo:seen";
const LEVEL_BADGE = { high: `<span class="badge missing">${tr("要対応")}</span>`, mid: `<span class="badge queued">${tr("注意")}</span>`, info: `<span class="badge ok">${tr("お知らせ")}</span>` };

async function loadTodo() {
  const box = $("#todo");
  let d;
  try {
    d = await request("GET", "/api/todo");
  } catch (e) {
    box.innerHTML = `<div class="warn">${esc(e.message)}</div>`;
    return;
  }
  const seen = new Set(loadJson(TODO_SEEN_KEY, []));
  const fresh = d.items.filter((i) => i.level !== "info" && !seen.has(i.key));
  if (fresh.length && "Notification" in window && Notification.permission === "granted" && seen.size) {
    new Notification(tr("EVE ツール: やることリスト"), { body: fresh.slice(0, 5).map((i) => `${i.character_name}: ${i.text}`).join("\n") });
  }
  saveJson(TODO_SEEN_KEY, [...new Set([...seen, ...d.items.map((i) => i.key)])].slice(-1000));
  box.innerHTML = (d.items.length ? `<ul class="todo-list">${d.items.map((i) => `<li class="${fresh.includes(i) ? "todo-new" : ""}">
      ${LEVEL_BADGE[i.level]} <span class="muted">${esc(i.category)}</span> <b>${esc(i.character_name)}</b> ${esc(i.text)}
      <a href="${esc(i.link)}">${tr("開く →")}</a></li>`).join("")}</ul>` : `<p class="ok-text">${tr("✓ 対応が必要なものはありません。")}</p>`)
    + `<small class="muted">${tr("{0} に確認{1}", esc(fmtLocal(d.checked_at)), (d.failed.length ? `${tr("（取得できなかった項目: {0}。再ログインが必要な場合があります）", esc(d.failed.join(LIST_SEP)))}` : ""))}</small>`;
}

async function loadStatus() {
  try {
    const s = await request("GET", "/api/tools/status");
    $("#server-status").innerHTML = s.online ? `· <span class="badge ok">${tr("サーバー稼働中")}</span> ${tr("{0} 人", fmtNum(s.players))}`
      : `· <span class="badge missing">${tr("サーバーに接続できません")}</span>`;
  } catch {
    $("#server-status").textContent = "";
  }
}

$("#todo-reload").addEventListener("click", loadTodo);
$("#todo-notify").addEventListener("click", async () => {
  if (!("Notification" in window)) { toast(tr("このブラウザは通知に対応していません。"), "error"); return; }
  const p = await Notification.requestPermission();
  toast(p === "granted" ? tr("このページを開いている間、新しい項目を通知します。") : tr("通知が許可されませんでした。"), p === "granted" ? "ok" : "error");
});
// アカウントでサインインして使っているとき（クラウド）は、アカウントのページへのリンクを出す
(async () => {
  try {
    const { name } = await request("GET", "/api/account");
    if (!name) return;
    $("#account-link").textContent = `👤 ${name}`;
    $("#account-link").hidden = false;
  } catch { /* 出せなくても、ほかの表示は続ける */ }
})();

setInterval(loadTodo, 10 * 60 * 1000);
setInterval(loadStatus, 5 * 60 * 1000);
loadTodo();
loadStatus();

(async () => {
  try {
    const [{ characters }, watch] = await Promise.all([
      request("GET", "/api/characters"),
      request("GET", "/api/market/watchlist"),
    ]);
    const ready = characters.filter((c) => !c.missing);
    const total = ready.reduce((s, c) => s + c.total_sp, 0);
    $("#summary").textContent = characters.length
      ? `${tr("{0} キャラクター · 合計 {1} SP", characters.length, fmtNum(total))}`
      : tr("キャラクターが登録されていません。「＋ キャラクター追加」から EVE にログインしてください。");
    $("#skills-stat").textContent = characters.length ? `${tr("{0} キャラクター", characters.length)}` : tr("キャラクター未登録");
    $("#market-stat").textContent = `${tr("比較リスト {0} 件", watch.items.length)}`;
    renderCharacters(characters);
  } catch (e) {
    toast(e.message, "error");
  }
})();
