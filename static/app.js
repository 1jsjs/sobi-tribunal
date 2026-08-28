"use strict";
/* 소비 재판소 — 프론트 뼈대 (F301).
 * - 화면 6개 전환
 * - api(): 봉투 벗기기 + res.ok 판정 + 판사 말투 토스트
 * - 로딩 오버레이(의사봉) + 버튼 이중클릭 방지
 * 판정·점수 계산은 여기 없음(서버가 한다). 게이지 합산은 F304에서.
 */

/* ── 화면 전환 ─────────────────────────────────────────── */
const SCREENS = ["summon", "intake", "dossier", "courtroom", "verdict", "records"];

function showScreen(name) {
  SCREENS.forEach((s) => {
    const el = document.querySelector(`[data-screen="${s}"]`);
    if (el) el.hidden = s !== name;
  });
  window.scrollTo({ top: 0, behavior: "instant" in window ? "instant" : "auto" });
}

/* ── 애플리케이션 상태(재판 내내 들고 다니는 것) ───────── */
const state = {
  email: null,
  dossier: null, // 조서
  photoUrl: null, // 증거물 액자용 (presigned 또는 objectURL)
  trial: null, // {opening, questions, source}
  answers: [], // [{questionId, choiceIndex}]
  plea: null,
};

/* ── 봉투를 벗기는 fetch 래퍼 ──────────────────────────── */
async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  let body = null;
  try {
    body = await res.json();
  } catch (_e) {
    throw new ApiError("법정이 응답을 알아듣지 못했소.");
  }
  // 응답 봉투 계약: {success, data} | {success:false, error:{code,message}}
  if (!res.ok || !body || body.success !== true) {
    const msg = (body && body.error && body.error.message) || "알 수 없는 사유로 기각되었소.";
    const code = body && body.error && body.error.code;
    throw new ApiError(msg, code);
  }
  return body.data;
}

class ApiError extends Error {
  constructor(message, code) {
    super(message);
    this.name = "ApiError";
    this.code = code || null;
  }
}

/* ── 로딩 오버레이 (연출 문구 인자) ───────────────────── */
const overlayEl = document.getElementById("overlay");
const overlayText = document.getElementById("overlay-text");

function showLoading(text) {
  overlayText.textContent = text || "잠시 기다리시오…";
  overlayEl.hidden = false;
}
function hideLoading() {
  overlayEl.hidden = true;
}

/* 버튼 이중클릭 방지: 비동기 작업 동안 버튼 비활성화 + 오버레이 */
async function withBusy(btn, loadingText, fn) {
  if (btn && btn.disabled) return; // 이미 진행 중
  if (btn) btn.disabled = true;
  if (loadingText) showLoading(loadingText);
  try {
    return await fn();
  } finally {
    if (loadingText) hideLoading();
    if (btn) btn.disabled = false;
  }
}

/* ── 토스트 (판사 말투 에러) ──────────────────────────── */
const toastEl = document.getElementById("toast");
let toastTimer = null;

function toast(message, { judge = true } = {}) {
  toastEl.textContent = judge ? `기각하오 — ${message}` : message;
  toastEl.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toastEl.hidden = true;
  }, 3200);
}

/* 에러를 한곳에서 처리 */
function handleError(err) {
  if (err instanceof ApiError) {
    toast(err.message);
  } else {
    toast(err && err.message ? err.message : "예기치 못한 오류가 났소.");
    // 개발 편의: 콘솔에도 남긴다
    console.error(err);
  }
}

/* ── 카테고리 셀렉트 채우기 (constants와 동일 라벨) ─────── */
const CATEGORY_LABELS = {
  FASHION_BEAUTY: "패션·뷰티",
  FOOD_DINING: "식음료·외식",
  DIGITAL_APPLIANCE: "가전·디지털",
  HOBBY_LEISURE: "취미·여가",
  LIVING_GROCERY: "생활·식료품",
  OTHER: "기타",
};

function fillCategorySelect() {
  const sel = document.getElementById("d-category");
  if (!sel || sel.options.length) return;
  Object.entries(CATEGORY_LABELS).forEach(([code, label]) => {
    const opt = document.createElement("option");
    opt.value = code;
    opt.textContent = label;
    sel.appendChild(opt);
  });
}

/* ── 표시 유틸 ─────────────────────────────────────────── */
function won(n) {
  const v = Number(n) || 0;
  return v.toLocaleString("ko-KR") + "원";
}

/* ── 음소거 토글 (자리만 — F304에서 speechSynthesis 연결) ── */
const muteBtn = document.getElementById("btn-mute");
const audio = { muted: false };
if (muteBtn) {
  muteBtn.addEventListener("click", () => {
    audio.muted = !audio.muted;
    muteBtn.textContent = audio.muted ? "🔇" : "🔊";
    muteBtn.setAttribute("aria-pressed", String(audio.muted));
  });
}

/* ── 헤더 내비게이션 ───────────────────────────────────── */
document.getElementById("btn-home").addEventListener("click", () => {
  showScreen(state.email ? "intake" : "summon");
});
document.getElementById("btn-records").addEventListener("click", () => {
  if (!state.email) {
    toast("먼저 출석부터 하시오.");
    showScreen("summon");
    return;
  }
  loadRecords();
});

/* ── 소환장: 이메일 출석 (localStorage 기억) ──────────── */
const EMAIL_KEY = "tribunal_email";

document.getElementById("summon-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const raw = document.getElementById("summon-email").value.trim().toLowerCase();
  if (!raw || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(raw)) {
    toast("이메일 형식이 올바르지 않소.");
    return;
  }
  state.email = raw;
  try {
    localStorage.setItem(EMAIL_KEY, raw);
  } catch (_e) {
    /* 프라이빗 모드 등 — 무시 */
  }
  showScreen("intake");
});

/* ── 전과 기록 로드 (F305에서 상세·사진 확장) ─────────── */
async function loadRecords() {
  showScreen("records");
  const listEl = document.getElementById("record-list");
  const emptyEl = document.getElementById("records-empty");
  listEl.innerHTML = "";
  emptyEl.hidden = true;
  try {
    const rows = await api(
      "/api/records?email=" + encodeURIComponent(state.email)
    );
    if (!rows.length) {
      emptyEl.hidden = false;
      return;
    }
    rows.forEach((r) => listEl.appendChild(renderRecordItem(r)));
  } catch (err) {
    handleError(err);
  }
}

function renderRecordItem(r) {
  const li = document.createElement("li");
  li.className = "record-item";
  li.innerHTML = `
    <span class="r-emoji">${r.typeEmoji || "⚖️"}</span>
    <span class="r-main">
      <div class="r-item">${escapeHtml(r.itemName || "물건")} · ${won(r.price)}</div>
      <div class="r-sub">${escapeHtml(r.typeName || "")}</div>
    </span>
    <span class="badge ${r.guilt}">${escapeHtml(r.guiltLabel || "")}</span>`;
  li.addEventListener("click", () => {
    // 상세는 F305에서. 지금은 사건번호만 알린다.
    toast(`사건 #${r.id} — ${r.guiltLabel}`, { judge: false });
  });
  return li;
}

function escapeHtml(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

/* ── 화면 전환 버튼(뼈대 수준 — 각 흐름은 F302~F305에서) ── */
document.getElementById("btn-manual-entry").addEventListener("click", () => {
  fillCategorySelect();
  showScreen("dossier");
});
document.getElementById("btn-to-records").addEventListener("click", () => {
  if (state.email) loadRecords();
  else showScreen("summon");
});
document.getElementById("btn-new-trial").addEventListener("click", () => {
  showScreen("intake");
});
document.getElementById("btn-records-new").addEventListener("click", () => {
  showScreen("intake");
});

/* ── 부팅 ──────────────────────────────────────────────── */
function boot() {
  fillCategorySelect();
  try {
    const saved = localStorage.getItem(EMAIL_KEY);
    if (saved) state.email = saved;
  } catch (_e) {
    /* 무시 */
  }
  showScreen(state.email ? "intake" : "summon");
}

// 외부(F302~F305) 연결용으로 최소한만 노출
window.tribunal = { state, api, showScreen, showLoading, hideLoading, withBusy, toast, handleError, won, escapeHtml, loadRecords, fillCategorySelect, audio };

boot();
