"use strict";
/* 소비 재판소 — 프론트 뼈대 (F301).
 * - 화면 6개 전환
 * - api(): 봉투 벗기기 + res.ok 판정 + 판사 말투 토스트
 * - 로딩 오버레이(의사봉) + 버튼 이중클릭 방지
 * 판정·점수 계산은 여기 없음(서버가 한다). 게이지 합산은 F304에서.
 */

/* ── 화면 전환 ─────────────────────────────────────────── */
const SCREENS = ["summon", "intake", "dossier", "courtroom", "plea", "verdict", "records"];

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

/* ── 판사 TTS (speechSynthesis, ko-KR / rate 0.95 / pitch 0.7) ── */
const MUTE_KEY = "tribunalMuted";
const tts = {
  muted: false,
  voice: null,
  supported: typeof window.speechSynthesis !== "undefined",
};

function pickKoVoice() {
  if (!tts.supported) return;
  const voices = window.speechSynthesis.getVoices() || [];
  tts.voice =
    voices.find((v) => v.lang === "ko-KR") ||
    voices.find((v) => /^ko/i.test(v.lang)) ||
    null;
}
if (tts.supported) {
  pickKoVoice();
  // 보이스 목록은 비동기 로드 → voiceschanged 후 다시 고른다
  window.speechSynthesis.onvoiceschanged = pickKoVoice;
}

/* speak는 반드시 사용자 제스처(클릭) 흐름에서 호출된다 */
function speak(text) {
  if (!tts.supported || tts.muted || !text) return;
  try {
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "ko-KR";
    u.rate = 0.95;
    u.pitch = 0.7;
    if (tts.voice) u.voice = tts.voice;
    window.speechSynthesis.speak(u);
  } catch (_e) {
    /* 낭독 실패는 조용히 무시 — 재판은 계속된다 */
  }
}
function stopSpeaking() {
  if (tts.supported) {
    try { window.speechSynthesis.cancel(); } catch (_e) { /* 무시 */ }
  }
}

const muteBtn = document.getElementById("btn-mute");
function applyMuteUi() {
  if (!muteBtn) return;
  muteBtn.textContent = tts.muted ? "🔇" : "🔊";
  muteBtn.setAttribute("aria-pressed", String(tts.muted));
}
try {
  tts.muted = localStorage.getItem(MUTE_KEY) === "1";
} catch (_e) {
  /* 무시 */
}
applyMuteUi();
if (muteBtn) {
  muteBtn.addEventListener("click", () => {
    tts.muted = !tts.muted;
    if (tts.muted) stopSpeaking();
    try { localStorage.setItem(MUTE_KEY, tts.muted ? "1" : "0"); } catch (_e) { /* 무시 */ }
    applyMuteUi();
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
const EMAIL_KEY = "defendantEmail";

document.getElementById("summon-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const raw = document.getElementById("summon-email").value.trim().toLowerCase();
  if (!raw || !raw.includes("@") || !raw.includes(".")) {
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

/* ══════════════════════════════════════════════════════════
 *  기소(intake) — 사진 업로드 / 수동 입력
 * ══════════════════════════════════════════════════════════ */
const MAX_EDGE = 1568; // 리사이즈 최대 변
const JPEG_QUALITY = 0.8;

const fileInput = document.getElementById("intake-file");
const uploadPreview = document.getElementById("upload-preview");
const submitEvidenceBtn = document.getElementById("btn-submit-evidence");
const intakeNotice = document.getElementById("intake-notice");
let pickedFile = null; // 원본 File
let pickedObjectUrl = null; // 원본 미리보기 URL (세션 보관)

fileInput.addEventListener("change", () => {
  const f = fileInput.files && fileInput.files[0];
  if (!f) return;
  if (!/^image\//.test(f.type)) {
    toast("사진 파일만 제출할 수 있소.");
    return;
  }
  pickedFile = f;
  if (pickedObjectUrl) URL.revokeObjectURL(pickedObjectUrl);
  pickedObjectUrl = URL.createObjectURL(f);
  uploadPreview.src = pickedObjectUrl;
  uploadPreview.hidden = false;
  intakeNotice.hidden = true;
  submitEvidenceBtn.disabled = false;
});

/* canvas 리사이즈 → JPEG Blob (최대 변 1568, 품질 0.8) */
function resizeImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      let { width, height } = img;
      const longest = Math.max(width, height);
      if (longest > MAX_EDGE) {
        const scale = MAX_EDGE / longest;
        width = Math.round(width * scale);
        height = Math.round(height * scale);
      }
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(img, 0, 0, width, height);
      canvas.toBlob(
        (blob) => {
          if (blob) resolve(blob);
          else reject(new Error("이미지를 변환하지 못했소."));
        },
        "image/jpeg",
        JPEG_QUALITY
      );
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("이미지를 읽지 못했소."));
    };
    img.src = url;
  });
}

submitEvidenceBtn.addEventListener("click", () => {
  if (!pickedFile) {
    toast("먼저 증거 사진을 고르시오.");
    return;
  }
  withBusy(submitEvidenceBtn, "증거물 감식 중...", async () => {
    try {
      const blob = await resizeImage(pickedFile);
      const form = new FormData();
      form.append("file", blob, "evidence.jpg");
      const data = await api("/api/intake", { method: "POST", body: form });
      // 증거물 액자: presigned photoUrl 우선, 없으면 원본 objectURL
      state.photoUrl = data.photoUrl || pickedObjectUrl;
      handleIntakeResult(data);
    } catch (err) {
      handleError(err);
    }
  });
});

/* intake 응답 처리: candidates 개수에 따라 분기 */
function handleIntakeResult(data) {
  const candidates = Array.isArray(data.candidates) ? data.candidates : [];
  if (candidates.length >= 2) {
    renderCandidatePicker(candidates, data.dossier);
    goToDossier(data.dossier); // 폼도 첫 후보로 채워둔다
    return;
  }
  // 서버 조서(photoKey 등)를 보관 — 최종 확정 시 photoKey 계승
  state.intakeDossier = data.dossier || null;
  // 1건(또는 0건이어도 서버가 빈 조서를 준다)
  const hasItem = data.dossier && data.dossier.itemName;
  if (!hasItem) {
    // 판독 실패 → 수동 입력 유도
    intakeNotice.hidden = false;
    intakeNotice.textContent = "증거를 판독하지 못했소. 직접 적어 자수하시오.";
    startManualEntry();
    return;
  }
  goToDossier(data.dossier);
}

/* candidates 2건 이상: "어느 건으로 기소하시겠소?" 리스트 */
function renderCandidatePicker(candidates, baseDossier) {
  const picker = document.getElementById("candidate-picker");
  picker.hidden = false;
  picker.innerHTML = '<p class="muted small">어느 건으로 기소하시겠소?</p>';
  const listWrap = document.createElement("div");
  listWrap.className = "candidate-list";
  candidates.forEach((c, i) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "choice candidate";
    const date = c.boughtAt ? ` · ${c.boughtAt}` : "";
    const merch = c.merchant ? ` · ${escapeHtml(c.merchant)}` : "";
    btn.innerHTML = `<strong>${escapeHtml(c.itemName || "물건")}</strong> · ${won(c.price)}<span class="muted small">${date}${merch}</span>`;
    btn.addEventListener("click", () => {
      // 고른 후보를 dossier에 병합해 폼 갱신
      const merged = Object.assign({}, baseDossier, {
        itemName: c.itemName,
        price: c.price,
        boughtAt: c.boughtAt || null,
        merchant: c.merchant || null,
        category: c.category || baseDossier.category || "OTHER",
      });
      picker.querySelectorAll(".candidate").forEach((el) => el.classList.remove("selected"));
      btn.classList.add("selected");
      fillDossierForm(merged);
    });
    listWrap.appendChild(btn);
  });
  picker.appendChild(listWrap);
}

/* 수동 입력: 서버 없이 빈 조서로 조서 확인 화면 진입 */
function startManualEntry() {
  fillCategorySelect();
  fillDossierForm({
    itemName: "",
    price: "",
    boughtAt: null,
    merchant: null,
    category: "OTHER",
    story: null,
    photoKey: null,
  });
  document.getElementById("candidate-picker").hidden = true;
  // 사진 없이 왔다면 액자는 원본(있으면)만
  if (!state.photoUrl && pickedObjectUrl) state.photoUrl = pickedObjectUrl;
  showScreen("dossier");
}

/* 조서 확인 화면으로: 폼 채우고 전환 */
function goToDossier(dossier) {
  fillCategorySelect();
  fillDossierForm(dossier);
  showScreen("dossier");
}

/* 금액 콤마 표기 유틸 */
function digitsOnly(s) {
  return String(s == null ? "" : s).replace(/[^\d]/g, "");
}
function commaify(s) {
  const d = digitsOnly(s);
  return d ? Number(d).toLocaleString("ko-KR") : "";
}

/* 조서 폼 채우기 */
function fillDossierForm(d) {
  document.getElementById("d-itemName").value = d.itemName || "";
  document.getElementById("d-price").value =
    d.price != null && d.price !== "" ? Number(d.price).toLocaleString("ko-KR") : "";
  document.getElementById("d-boughtAt").value = d.boughtAt || "";
  document.getElementById("d-merchant").value = d.merchant || "";
  const storyEl = document.getElementById("d-story");
  if (storyEl) storyEl.value = d.story || "";
  const catEl = document.getElementById("d-category");
  if (catEl) catEl.value = d.category && CATEGORY_LABELS[d.category] ? d.category : "OTHER";
  const usageEl = document.getElementById("d-usage");
  if (usageEl) usageEl.value = d.usage || "";
  renderDossierThumb(d.category);
}

/* 증거물 썸네일: photoUrl/objectURL 우선, 없으면 카테고리 이모지 */
const CATEGORY_EMOJI = {
  FASHION_BEAUTY: "👗",
  FOOD_DINING: "🍽️",
  DIGITAL_APPLIANCE: "💻",
  HOBBY_LEISURE: "🎨",
  LIVING_GROCERY: "🧺",
  OTHER: "📦",
};
function renderDossierThumb(category) {
  const img = document.getElementById("dossier-thumb");
  const emo = document.getElementById("dossier-thumb-emoji");
  if (!img || !emo) return;
  if (state.photoUrl) {
    img.src = state.photoUrl;
    img.hidden = false;
    emo.hidden = true;
  } else {
    emo.textContent = CATEGORY_EMOJI[category] || CATEGORY_EMOJI.OTHER;
    emo.hidden = false;
    img.hidden = true;
  }
}

document.getElementById("btn-manual-entry").addEventListener("click", () => {
  intakeNotice.hidden = true;
  startManualEntry();
});

/* ══════════════════════════════════════════════════════════
 *  조서 확인(dossier) — 인라인 수정 + 기소 확정
 * ══════════════════════════════════════════════════════════ */

/* 금액 입력 콤마 실시간 표기 */
const priceInput = document.getElementById("d-price");
if (priceInput) {
  priceInput.addEventListener("input", () => {
    const caretFromEnd = priceInput.value.length - priceInput.selectionStart;
    priceInput.value = commaify(priceInput.value);
    const pos = Math.max(0, priceInput.value.length - caretFromEnd);
    try { priceInput.setSelectionRange(pos, pos); } catch (_e) { /* 무시 */ }
  });
}

/* 폼 값 → dossier 객체 (계약 형태) */
function buildDossierFromForm() {
  const itemName = document.getElementById("d-itemName").value.trim();
  const price = parseInt(digitsOnly(document.getElementById("d-price").value), 10);
  const usageRaw = (document.getElementById("d-usage") || {}).value;
  const storyEl = document.getElementById("d-story");
  return {
    itemName: itemName,
    price: Number.isInteger(price) ? price : NaN,
    boughtAt: document.getElementById("d-boughtAt").value || null,
    merchant: document.getElementById("d-merchant").value.trim() || null,
    category: document.getElementById("d-category").value || "OTHER",
    usage: usageRaw || null, // "often"/"rare"/"unopened"/null — 점수화 안 함
    story: storyEl && storyEl.value.trim() ? storyEl.value.trim() : null,
    photoKey: state.intakeDossier ? state.intakeDossier.photoKey || null : null,
  };
}

const openTrialBtn = document.getElementById("btn-open-trial");

async function confirmIndictment() {
  const dossier = buildDossierFromForm();
  if (!dossier.itemName) {
    toast("품목명을 적으시오.");
    return;
  }
  if (!Number.isInteger(dossier.price) || dossier.price < 0) {
    toast("금액을 숫자로 적으시오.");
    return;
  }
  state.dossier = dossier;

  await withBusy(openTrialBtn, "판사님 입장 중...", async () => {
    try {
      const data = await api("/api/trial/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dossier: dossier }),
      });
      state.trial = data; // {opening, questions, source}
      state.answers = [];
      // 법정 진행은 F304. 훅이 있으면 넘기고, 없으면 화면만 전환.
      if (window.tribunal && typeof window.tribunal.onTrialStarted === "function") {
        window.tribunal.onTrialStarted();
      } else {
        showScreen("courtroom");
        const op = document.getElementById("trial-opening");
        if (op) op.textContent = data.opening || "";
      }
    } catch (err) {
      handleError(err);
      // 재시도 버튼 노출 (dossier 유지)
      showRetryStart();
    }
  });
}

openTrialBtn.addEventListener("click", confirmIndictment);

/* 시작 실패 시 재시도 버튼 (dossier 유지) */
function showRetryStart() {
  if (document.getElementById("btn-retry-start")) return;
  const btn = document.createElement("button");
  btn.className = "btn-ghost";
  btn.id = "btn-retry-start";
  btn.textContent = "다시 시도하오";
  btn.addEventListener("click", () => {
    btn.remove();
    confirmIndictment();
  });
  openTrialBtn.insertAdjacentElement("afterend", btn);
}

/* 증거를 다시 제출하겠소 → 기소 화면으로, 조서 상태 초기화 */
document.getElementById("btn-retry-intake").addEventListener("click", () => {
  state.dossier = null;
  state.intakeDossier = null;
  state.trial = null;
  state.answers = [];
  const retry = document.getElementById("btn-retry-start");
  if (retry) retry.remove();
  document.getElementById("candidate-picker").hidden = true;
  showScreen("intake");
});

/* ══════════════════════════════════════════════════════════
 *  법정(courtroom) — 질문 진행 + 심증 게이지 + TTS
 *  진행 로직은 전부 로컬. 서버 호출 없음. 판정은 서버 몫.
 * ══════════════════════════════════════════════════════════ */

/* 16유형 표 — constants.py의 표시 전용 사본 (판정 아님, 게이지 유력 유형명만) */
const CONSUMER_TYPES = {
  ERFQ: { name: "차분하고 엄격한 자기관리 끝판왕", emoji: "📒" },
  ERFD: { name: "절제를 할 줄 아는 멋진 활동가", emoji: "🏃" },
  ERSQ: { name: "관리형, 쇼핑도 즐기는 멋쟁이", emoji: "🛍️" },
  ERSD: { name: "절제할 줄 알며 패션과 스타일을 중시하는 활동가", emoji: "👔" },
  EIFQ: { name: "변화와 도전을 꿈꾸는 차분한 관리자", emoji: "🌱" },
  EIFD: { name: "절제가 쉽지 않아 고민 중인 활동가", emoji: "🎢" },
  EISQ: { name: "절제가 쉽지 않지만 노력 중인 멋쟁이", emoji: "💄" },
  EISD: { name: "패션과 스타일을 중시하는 외향형의 활동가", emoji: "🕶️" },
  GRFQ: { name: "절제할 줄 아는, 만남을 즐기는 차분한 스타일", emoji: "🍵" },
  GRFD: { name: "절제할 줄 아는, 만남을 즐기는 활동가", emoji: "🍻" },
  GRSQ: { name: "자유로운 성향의, 쇼핑도 즐기는 멋쟁이", emoji: "🎁" },
  GRSD: { name: "자유로운 영혼의, 패션과 스타일을 중시하는 활동가", emoji: "👗" },
  GIFQ: { name: "낭만과 감성을 아는 자유로운 영혼의 소유자", emoji: "🌙" },
  GIFD: { name: "낭만과 감성을 아는 기분파 활동가", emoji: "🎪" },
  GISQ: { name: "차분하고 조용한 자유로운 영혼의 소유자", emoji: "🎧" },
  GISD: { name: "패션과 낭만 감성을 중시하는 외향형의 활동가", emoji: "🕺" },
};
const AXIS_ORDER = ["EG", "RI", "FS", "QD"];
const AXIS_POLES = {
  EG: { front: "E", back: "G" },
  RI: { front: "R", back: "I" },
  FS: { front: "F", back: "S" },
  QD: { front: "Q", back: "D" },
};
const POLE_SIGN = { E: 1, G: -1, R: 1, I: -1, F: 1, S: -1, Q: 1, D: -1 };
const GAUGE_STEPS = [15, 35, 55, 75, 95]; // 확정 축 0~4개

// 재판 진행 상태
const trial = {
  questions: [],
  index: 0,
  locked: false,
};

// 게이지 계산용: 축별 pole 합(±2). 표시 전용 — 판정 아님.
function axisSums() {
  const sums = { EG: 0, RI: 0, FS: 0, QD: 0 };
  for (const a of state.answers) {
    const q = trial.questions.find((x) => x.id === a.questionId);
    if (!q || !(q.axis in sums)) continue;
    const choice = q.choices[a.choiceIndex];
    if (choice && choice.pole && POLE_SIGN[choice.pole] != null) {
      sums[q.axis] += POLE_SIGN[choice.pole] * 2;
    }
  }
  return sums;
}

// askIf 판정: 특정 축 pole 합이 whenScore와 같은지 (현재까지 answers 기준)
function shouldAsk(q) {
  if (!q.askIf) return true;
  const sums = axisSums();
  return (sums[q.askIf.axis] || 0) === q.askIf.whenScore;
}

/* onTrialStarted: 조서 확정 후 F303이 호출 */
function onTrialStarted() {
  trial.questions = (state.trial && state.trial.questions) || [];
  trial.index = 0;
  trial.locked = false;
  state.answers = [];

  // 증거물 액자
  const evImg = document.getElementById("evidence-img");
  if (evImg) {
    if (state.photoUrl) {
      evImg.src = state.photoUrl;
      evImg.style.visibility = "visible";
    } else {
      evImg.removeAttribute("src");
      evImg.style.visibility = "hidden";
    }
  }

  // 초기화면: 개정 선언 + 시작 버튼
  const bubble = document.getElementById("judge-bubble");
  const beginBtn = document.getElementById("btn-begin-trial");
  const area = document.getElementById("question-area");
  bubble.textContent = (state.trial && state.trial.opening) || "개정하오.";
  area.hidden = true;
  beginBtn.hidden = false;
  updateGauge();
  showScreen("courtroom");

  // opening 낭독은 시작 버튼 클릭(사용자 제스처)에서 — 자동재생 정책 준수
  beginBtn.onclick = () => {
    beginBtn.hidden = true;
    area.hidden = false;
    speak((state.trial && state.trial.opening) || "");
    // opening을 이미 읽었으니 첫 질문으로
    presentNext();
  };
}

/* 다음 질문 제시 (askIf 건너뛰기 반영) */
function presentNext() {
  trial.locked = false;
  const reactionEl = document.getElementById("judge-reaction");
  if (reactionEl) reactionEl.hidden = true;

  // askIf를 만족하는 다음 질문을 찾는다
  while (trial.index < trial.questions.length && !shouldAsk(trial.questions[trial.index])) {
    trial.index += 1;
  }
  if (trial.index >= trial.questions.length) {
    goToPlea();
    return;
  }

  const q = trial.questions[trial.index];
  const bubble = document.getElementById("judge-bubble");
  bubble.textContent = q.text;
  speak(q.text); // 질문만 낭독, 선택지는 낭독 안 함

  renderChoices(q);
  updateProgress();
}

function renderChoices(q) {
  const list = document.getElementById("choice-list");
  list.innerHTML = "";
  q.choices.forEach((c, i) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "choice";
    btn.textContent = c.label;
    btn.addEventListener("click", () => selectChoice(q, i));
    list.appendChild(btn);
  });
}

function selectChoice(q, choiceIndex) {
  if (trial.locked) return;
  trial.locked = true;

  // 선택지 잠금
  document.querySelectorAll("#choice-list .choice").forEach((el, i) => {
    el.disabled = true;
    if (i === choiceIndex) el.classList.add("selected");
  });

  // 답 누적
  state.answers.push({ questionId: q.id, choiceIndex: choiceIndex });
  updateGauge();

  // 판사 리액션 0.8초 후 다음
  const reactionEl = document.getElementById("judge-reaction");
  if (reactionEl) {
    reactionEl.textContent = pickReaction();
    reactionEl.hidden = false;
  }
  trial.index += 1;
  setTimeout(presentNext, 800);
}

const REACTIONS = ["…기록하겠소.", "그렇군. 기록하겠소.", "…흥미롭소. 기록하겠소.", "본 법정, 이를 접수하오."];
function pickReaction() {
  return REACTIONS[Math.floor(Math.random() * REACTIONS.length)];
}

function updateProgress() {
  const el = document.getElementById("trial-progress");
  if (!el) return;
  const answered = state.answers.length;
  el.textContent = `${answered + 1}번째 질문`;
}

/* 심증 게이지: 확정 축 수(합≠0) → 15/35/55/75/95% + 유력 유형명 */
function updateGauge() {
  const sums = axisSums();
  const decided = AXIS_ORDER.filter((ax) => sums[ax] !== 0).length;
  const pct = GAUGE_STEPS[decided];

  const fill = document.getElementById("gauge-fill");
  const label = document.getElementById("gauge-label");
  const suspect = document.getElementById("gauge-suspect");
  if (fill) fill.style.width = pct + "%";
  if (label) {
    label.textContent = decided >= 4 ? "판사의 심증이 섰소." : "심증이 굳어가고 있소…";
  }

  // 확정 축 2개부터 유력 유형명 노출 (미확정 축은 앞 글자로 채워 조회)
  if (suspect) {
    if (decided >= 2) {
      let code = "";
      for (const ax of AXIS_ORDER) {
        const s = sums[ax];
        code += s >= 0 ? AXIS_POLES[ax].front : AXIS_POLES[ax].back;
      }
      const t = CONSUMER_TYPES[code];
      suspect.textContent = t ? `유력 용의 유형: ${t.emoji} ${t.name}` : "";
      suspect.hidden = !t;
    } else {
      suspect.hidden = true;
    }
  }
}

/* ── 최후 변론 → 판결 ─────────────────────────────────── */
function goToPlea() {
  stopSpeaking();
  const ta = document.getElementById("plea-text");
  const count = document.getElementById("plea-count");
  if (ta) ta.value = "";
  if (count) count.textContent = "0";
  showScreen("plea");
}

const pleaText = document.getElementById("plea-text");
if (pleaText) {
  pleaText.addEventListener("input", () => {
    const c = document.getElementById("plea-count");
    if (c) c.textContent = String(pleaText.value.length);
  });
}

async function submitVerdict(plea) {
  await withBusy(null, "판결문 작성 중...", async () => {
    try {
      const payload = {
        email: state.email,
        dossier: state.dossier,
        answers: state.answers,
      };
      if (plea) payload.plea = plea;
      const data = await api("/api/trial/verdict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      state.verdict = data;
      // 판결 렌더는 F305. 훅이 있으면 넘기고, 없으면 최소 표시.
      if (window.tribunal && typeof window.tribunal.onVerdict === "function") {
        window.tribunal.onVerdict();
      } else {
        renderVerdictMinimal(data);
      }
    } catch (err) {
      handleError(err);
    }
  });
}

/* F305 전까지 최소 렌더 (완전 렌더는 F305) */
function renderVerdictMinimal(v) {
  showScreen("verdict");
  const set = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  };
  set("verdict-label", v.guiltLabel || "");
  set("verdict-text", v.verdictText || "");
  set("verdict-sentence", v.sentence || "");
  set("type-emoji", v.typeEmoji || "");
  set("type-name", v.typeName || "");
  set("type-code", v.axisCode || "");
  const stamp = document.getElementById("verdict-stamp");
  if (stamp) {
    const map = { GUILTY: "guilty", PROBATION: "probation", INNOCENT: "innocent" };
    stamp.src = `/static/assets/stamp-${map[v.guilt] || "guilty"}.svg`;
    stamp.hidden = false;
  }
}

document.getElementById("btn-plea-done").addEventListener("click", () => {
  const raw = (pleaText && pleaText.value.trim()) || "";
  if (raw.length > 200) {
    toast("최후 변론은 200자 이내로 하시오.");
    return;
  }
  state.plea = raw || null;
  submitVerdict(state.plea);
});
document.getElementById("btn-plea-skip").addEventListener("click", () => {
  state.plea = null;
  submitVerdict(null);
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

// 외부(F305) 연결용으로 최소한만 노출
window.tribunal = {
  state, api, showScreen, showLoading, hideLoading, withBusy, toast, handleError,
  won, escapeHtml, loadRecords, fillCategorySelect, tts, speak,
  onTrialStarted, // F303 → 법정 진입
};

boot();
