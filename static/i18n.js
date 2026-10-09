"use strict";
// 画面の言語（日本語・英語）。/i18n.js がこのファイルの前に LANG と I18N_DICT（英語訳）を入れて返す
// 文言は日本語をそのまま見出しにする: tr("{0} 星系", n) → 英語のときは "{0} systems" に n を入れる

const LANG = window.LANG || "ja";
const LOCALE = LANG === "en" ? "en-US" : "ja-JP";

// 引数のうち辞書に載っている文字列（サーバーの日本語の値など）も訳して入れる
function tr(key, ...args) {
  const dict = LANG === "en" ? window.I18N_DICT || {} : {};
  const look = (s) => (typeof s === "string" && Object.hasOwn(dict, s) ? dict[s] : null);
  const text = look(key) || key;
  const arg = (a) => look(a) || String(a);
  return args.length ? text.replace(/\{(\d+)\}/g, (m, i) => (i < args.length ? arg(args[i]) : m)) : text;
}

// {ja: 日本語名, en: 英語名} のような項目の、今の言語の名前
function nm(item, ja = "ja", en = "en") {
  if (!item) return "";
  return LANG === "en" ? (item[en] || item[ja] || "") : (item[ja] || item[en] || "");
}

// ナビに言語の切り替えを付ける
document.addEventListener("DOMContentLoaded", () => {
  const nav = document.querySelector(".site-nav-inner");
  if (!nav) return;
  const next = LANG === "en" ? "ja" : "en";
  const link = document.createElement("a");
  link.className = "lang-switch";
  link.href = `/lang?to=${next}&next=${encodeURIComponent(location.pathname + location.search)}`;
  link.textContent = next === "en" ? "🌐 English" : "🌐 日本語";
  link.lang = next;
  nav.append(link);
});

// 名前の補足（日本語のときは英語名を添える。英語のときは出さない）
function nmSub(item, suffix = "", en = "en") {
  return LANG === "en" || !item?.[en] ? "" : esc(item[en]) + suffix;
}

// 並べるときの区切り（日本語「、」「・」→ 英語「, 」）
const LIST_SEP = LANG === "en" ? ", " : "、";
const DOT_SEP = LANG === "en" ? ", " : "・";
