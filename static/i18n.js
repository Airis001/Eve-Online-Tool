"use strict";
// 画面の言語。/i18n.js がこのファイルの前に LANG・LANG_NAMES・I18N_DICT（今の言語の訳）を入れて返す
// 文言は日本語をそのまま見出しにする: tr("{0} 星系", n) → 英語のときは "{0} systems" に n を入れる

const LANG = window.LANG || "ja";
const LOCALES = { ja: "ja-JP", en: "en-US", de: "de-DE", fr: "fr-FR", es: "es-ES", ru: "ru-RU", ko: "ko-KR", zh: "zh-CN" };
const LOCALE = LOCALES[LANG] || "en-US";

// 引数のうち辞書に載っている文字列（サーバーの日本語の値など）も訳して入れる
function tr(key, ...args) {
  const dict = LANG === "ja" ? {} : window.I18N_DICT || {};
  const look = (s) => (typeof s === "string" && Object.hasOwn(dict, s) ? dict[s] : null);
  const text = look(key) || key;
  const arg = (a) => look(a) || String(a);
  return args.length ? text.replace(/\{(\d+)\}/g, (m, i) => (i < args.length ? arg(args[i]) : m)) : text;
}

// {ja: 日本語名, en: 英語名, loc: 今の言語の名前} のような項目の、今の言語の名前
// （loc / 〇〇_loc は、日本語・英語以外のときにサーバーが足す）
function nm(item, ja = "ja", en = "en") {
  if (!item) return "";
  if (LANG === "ja") return item[ja] || item[en] || "";
  const loc = en === "en" ? "loc" : en.endsWith("_en") ? `${en.slice(0, -3)}_loc` : null;
  return (loc && item[loc]) || item[en] || item[ja] || "";
}

// ナビに言語の切り替えのメニューを付ける
document.addEventListener("DOMContentLoaded", () => {
  const nav = document.querySelector(".site-nav-inner");
  if (!nav) return;
  const names = window.LANG_NAMES || { ja: "日本語", en: "English" };
  const back = encodeURIComponent(location.pathname + location.search);
  const menu = document.createElement("details");
  menu.className = "nav-group lang-switch";
  menu.innerHTML = `<summary>🌐 ${esc(names[LANG] || LANG)}</summary><div class="nav-menu">${Object.entries(names).map(([code, label]) =>
    `<a href="/lang?to=${code}&next=${back}" lang="${code}"${code === LANG ? ' aria-current="true"' : ""}>${esc(label)}</a>`).join("")}</div>`;
  nav.append(menu);
});

// 名前の補足（英語以外のときは英語名を添える。今の言語の名前と同じなら出さない）
function nmSub(item, suffix = "", en = "en") {
  if (LANG === "en" || !item?.[en] || nm(item, "ja", en) === item[en]) return "";
  return esc(item[en]) + suffix;
}

// 並べるときの区切り（日本語「、」「・」→ ほかの言語「, 」）
const LIST_SEP = LANG === "ja" ? "、" : ", ";
const DOT_SEP = LANG === "ja" ? "・" : ", ";
