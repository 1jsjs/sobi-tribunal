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
  // 배경 2단계: 재판(법정~판결) 동안은 판사가 판사석에 앉은 배경으로 (팀 피드백 8/29)
  document.body.classList.toggle("with-judge", ["courtroom", "plea", "verdict"].includes(name));
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
    applyBgmMute(); // BGM도 함께 온오프
  });
}

/* ══════════════════════════════════════════════════════════
 *  법정 BGM — 팀 제공 음원(The_Weighted_Scale.mp3) 루프 재생
 *  첫 사용자 제스처 후 시작 · 음소거 키(MUTE_KEY) 공유 · 판결 도장 덕킹
 * ══════════════════════════════════════════════════════════ */
const bgm = { el: null, started: false };
const BGM_BASE_VOL = 0.32;
const BGM_DUCK_VOL = 0.08;

function startBgm() {
  if (bgm.started || tts.muted) return;
  try {
    if (!bgm.el) {
      bgm.el = new Audio("/static/assets/The_Weighted_Scale.mp3");
      bgm.el.loop = true;
      bgm.el.preload = "auto";
    }
    bgm.el.volume = BGM_BASE_VOL;
    const p = bgm.el.play();
    if (p && p.catch) p.catch(() => {
      // 자동재생 거부 → 다음 사용자 클릭에서 재시도
      bgm.started = false;
      document.addEventListener("click", bgmFirstGesture, { once: true });
    });
    bgm.started = true;
  } catch (_e) {
    /* BGM 실패는 조용히 무시 — 앱 동작에 영향 없음 */
  }
}

/* 음소거 상태를 BGM에 반영 */
function applyBgmMute() {
  if (!bgm.el || !bgm.started) {
    if (!tts.muted) startBgm();
    return;
  }
  try {
    if (tts.muted) bgm.el.pause();
    else { bgm.el.volume = BGM_BASE_VOL; bgm.el.play().catch(() => {}); }
  } catch (_e) { /* 무시 */ }
}

/* 판결 도장 순간: 1.5초 덕킹 후 복귀 (판사봉·TTS가 안 묻히게) */
function duckBgm() {
  if (!bgm.el || !bgm.started || tts.muted) return;
  try {
    bgm.el.volume = BGM_DUCK_VOL;
    setTimeout(() => { if (bgm.el && !tts.muted) bgm.el.volume = BGM_BASE_VOL; }, 1500);
  } catch (_e) { /* 무시 */ }
}

/* 첫 사용자 제스처(아무 클릭) 후에만 AudioContext resume + BGM 시작 */
function bgmFirstGesture() {
  if (bgm.ctx && bgm.ctx.state === "suspended") {
    bgm.ctx.resume().catch(() => {});
  }
  startBgm();
  if (bgm.ctx && bgm.ctx.state === "suspended") {
    bgm.ctx.resume().catch(() => {});
  }
}
document.addEventListener("click", bgmFirstGesture, { once: true });

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

/* ── 전과 기록 로드 ────────────────────────────────────── */
async function loadRecords() {
  showScreen("records");
  const listEl = document.getElementById("record-list");
  const emptyEl = document.getElementById("records-empty");
  const summaryEl = document.getElementById("records-summary");
  listEl.innerHTML = "";
  emptyEl.hidden = true;
  summaryEl.textContent = "";
  try {
    const rows = await api("/api/records?email=" + encodeURIComponent(state.email));
    if (!rows.length) {
      emptyEl.hidden = false;
      return;
    }
    // 요약: 개수 세기만 (금액 합산·재계산 금지)
    const guiltyCount = rows.filter((r) => r.guilt === "GUILTY").length;
    summaryEl.textContent = `전과 ${rows.length}건 · 유죄 ${guiltyCount}건`;
    rows.forEach((r) => listEl.appendChild(renderRecordItem(r)));
  } catch (err) {
    handleError(err);
  }
}

/* 카테고리 이모지 폴백은 CATEGORY_EMOJI 재사용 (F303에서 정의) */
function recordThumb(r) {
  if (r.photoUrl) {
    return `<img class="r-thumb" src="${escapeHtml(r.photoUrl)}" alt="" />`;
  }
  const emo = (typeof CATEGORY_EMOJI !== "undefined" && CATEGORY_EMOJI[r.category]) || "📦";
  return `<span class="r-thumb r-thumb-emoji">${emo}</span>`;
}

function renderRecordItem(r) {
  const li = document.createElement("li");
  li.className = "record-item";
  const date = (r.createdAt || "").slice(0, 10);
  li.innerHTML = `
    ${recordThumb(r)}
    <span class="r-main">
      <div class="r-item">${escapeHtml(r.itemName || "물건")} · ${won(r.price)}</div>
      <div class="r-sub">${escapeHtml(r.typeName || "")}${date ? " · " + date : ""}</div>
    </span>
    <span class="mini-stamp ${r.guilt}">${escapeHtml(r.guiltLabel || "")}</span>`;
  li.addEventListener("click", () => openRecordModal(r.id));
  return li;
}

/* ── 전과 상세 모달 ────────────────────────────────────── */
async function openRecordModal(id) {
  try {
    const d = await api("/api/records/" + encodeURIComponent(id));
    const stamp = document.getElementById("modal-stamp");
    stamp.src = `/static/assets/stamp-${STAMP_FILE[d.guilt] || "guilty"}.svg`;
    document.getElementById("modal-item").textContent = `${d.itemName || "물건"} · ${won(d.price)}`;
    const date = (d.createdAt || "").slice(0, 10);
    document.getElementById("modal-meta").textContent =
      `${d.guiltLabel || ""}${date ? " · " + date : ""}`;
    document.getElementById("modal-type").textContent =
      `${d.typeEmoji || ""} ${d.typeName || ""} (${d.axisCode || ""})`;

    const vt = document.getElementById("modal-verdict-text");
    vt.innerHTML = "";
    String(d.verdictText || "")
      .split(/\n{1,}|(?<=[.。])\s{2,}/)
      .map((s) => s.trim())
      .filter(Boolean)
      .forEach((para) => {
        const p = document.createElement("p");
        p.textContent = para;
        vt.appendChild(p);
      });

    document.getElementById("modal-sentence").textContent = d.sentence || "";
    const pleaEl = document.getElementById("modal-plea");
    if (d.plea) {
      pleaEl.textContent = `최후 변론: "${d.plea}"`;
      pleaEl.hidden = false;
    } else {
      pleaEl.hidden = true;
    }

    // 심문 기록: 있으면 접이식 섹션, 빈 배열(구버전·시드)이면 숨김
    const intr = Array.isArray(d.interrogation) ? d.interrogation : [];
    const intrEl = document.getElementById("modal-interrogation");
    const qaList = document.getElementById("modal-qa-list");
    qaList.innerHTML = "";
    if (intr.length) {
      document.getElementById("modal-interrogation-summary").textContent =
        `심문 기록 ${intr.length}문`;
      intr.forEach((qa) => {
        const li = document.createElement("li");
        li.className = "qa-item";
        li.innerHTML = `
          <div class="qa-q">${escapeHtml(qa.q || "")}</div>
          <div class="qa-a">${escapeHtml(qa.a || "")}</div>`;
        qaList.appendChild(li);
      });
      intrEl.open = false; // 접힌 상태로 시작
      intrEl.hidden = false;
    } else {
      intrEl.hidden = true;
    }

    document.getElementById("record-modal").hidden = false;
  } catch (err) {
    handleError(err);
  }
}

function closeRecordModal() {
  document.getElementById("record-modal").hidden = true;
}
document.getElementById("modal-close").addEventListener("click", closeRecordModal);
document.getElementById("modal-backdrop").addEventListener("click", closeRecordModal);
document.getElementById("btn-records-empty-go").addEventListener("click", () => {
  resetTrialState();
  showScreen("intake");
});

/* ── 퇴정(로그아웃) — 피고인 교체 ──────────────────────── */
document.getElementById("btn-logout").addEventListener("click", () => {
  stopSpeaking();
  resetTrialState();
  state.email = null;
  state.photoUrl = null;
  try {
    localStorage.removeItem(EMAIL_KEY);
  } catch (_e) {
    /* 무시 */
  }
  closeRecordModal();
  const emailInput = document.getElementById("summon-email");
  if (emailInput) emailInput.value = "";
  showScreen("summon");
  toast("퇴정하였소. 다음 피고인은 출석하시오.", { judge: false });
});

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
      fireSpeculativeTrial(); // dossier 통째로 바뀜 → 재발사
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

/* 조서 확인 화면으로: 폼 채우고 전환 + 투기 발사 */
function goToDossier(dossier) {
  fillCategorySelect();
  fillDossierForm(dossier);
  showScreen("dossier");
  fireSpeculativeTrial(); // 조서 보는 동안 재판 미리 준비
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

/* ── 투기적 재판 준비 (speculative /api/trial/start) ──────────────
 * 조서를 보는 동안 미리 trial/start를 발사해 "판사님 입장 중..." 체감 제거.
 * 세대 번호(gen)로 최신 요청만 채택. 낡은 응답은 늦게 와도 절대 안 쓴다.
 * 폼 스냅샷(key)으로 확정 시점 폼과 발사 시점 dossier가 일치하는지 검증. */
const spec = { gen: 0, latest: null, debounceTimer: null };

/* dossier를 비교용 안정 문자열로 (trial/start에 영향 주는 필드 전부) */
function dossierKey(d) {
  return JSON.stringify([
    d.itemName, d.price, d.boughtAt, d.merchant, d.category, d.usage, d.story, d.photoKey,
  ]);
}

/* 유효한 dossier인지 (품목명·정수 금액) — 무효면 발사 안 함 */
function dossierFireable(d) {
  return !!d.itemName && Number.isInteger(d.price) && d.price >= 0;
}

/* 투기 발사: 현재 폼 값으로 trial/start를 백그라운드 fetch. await 하지 않는다. */
function fireSpeculativeTrial() {
  const dossier = buildDossierFromForm();
  if (!dossierFireable(dossier)) return; // 아직 확정 못 할 조서면 발사 보류
  const key = dossierKey(dossier);
  // 이미 같은 조서로 유효 발사가 떠 있으면 재발사 안 함 (연타·중복 방지)
  if (spec.latest && spec.latest.key === key && spec.latest.status !== "error") return;

  const myGen = ++spec.gen;
  const record = { gen: myGen, key: key, dossier: dossier, status: "pending", promise: null };
  record.promise = api("/api/trial/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dossier: dossier }),
  })
    .then((data) => { record.status = "done"; return data; })
    .catch((err) => { record.status = "error"; throw err; });
  spec.latest = record;
}

/* debounce 400ms 재발사 (폼 수정 시) */
function scheduleSpeculative() {
  clearTimeout(spec.debounceTimer);
  spec.debounceTimer = setTimeout(fireSpeculativeTrial, 400);
}

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
  const key = dossierKey(dossier);

  // 보관된 투기 Promise가 현재 폼과 같은 조서면 그걸 재사용, 아니면 새로 발사
  let record = spec.latest;
  const reusable =
    record && record.key === key && record.status !== "error";
  if (!reusable) {
    fireSpeculativeTrial();      // 최신 폼 기준으로 새로 발사
    record = spec.latest;
    // 발사 자체가 불가(무효 조서)면 record가 갱신 안 됐을 수 있음 → 직접 호출로 폴백
    if (!record || record.key !== key) {
      return startTrialDirect(dossier);
    }
  }

  const useGen = record.gen;
  // 이미 끝난 응답이면 오버레이 없이 즉시, 아직이면 오버레이 표시
  const showOverlay = record.status === "pending";
  try {
    const runner = async () => {
      const data = await record.promise;
      // 채택 가드: 그 사이 더 최신 발사가 없었고, 폼도 안 바뀌었을 때만 채택
      if (record.gen !== spec.gen) throw new Error("STALE");
      return data;
    };
    let data;
    if (showOverlay) {
      data = await withBusy(openTrialBtn, "판사님 입장 중...", runner);
    } else {
      // 이미 응답이 와 있음: 오버레이 없이 즉시, 그래도 버튼은 잠가 이중 클릭 방지
      openTrialBtn.disabled = true;
      try {
        data = await runner();
      } finally {
        openTrialBtn.disabled = false;
      }
    }
    adoptTrial(data);
  } catch (err) {
    if (err && err.message === "STALE") {
      // 낡은 세대 — 최신 폼으로 새로 시작
      return startTrialDirect(buildDossierFromForm());
    }
    handleError(err);
    showRetryStart();
  }
}

/* 폼 최종 값으로 직접 새 호출 (투기 폴백·재시도용) */
async function startTrialDirect(dossier) {
  state.dossier = dossier;
  await withBusy(openTrialBtn, "판사님 입장 중...", async () => {
    try {
      const data = await api("/api/trial/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dossier: dossier }),
      });
      adoptTrial(data);
    } catch (err) {
      handleError(err);
      showRetryStart();
    }
  });
}

/* 받은 trial 데이터를 상태에 싣고 법정 진입 */
function adoptTrial(data) {
  state.trial = data; // {opening, questions, source}
  state.answers = [];
  if (window.tribunal && typeof window.tribunal.onTrialStarted === "function") {
    window.tribunal.onTrialStarted();
  } else {
    showScreen("courtroom");
    const op = document.getElementById("trial-opening");
    if (op) op.textContent = data.opening || "";
  }
}

openTrialBtn.addEventListener("click", confirmIndictment);

/* 조서 폼 수정 → debounce 재발사 (모든 입력 필드) */
["d-itemName", "d-price", "d-boughtAt", "d-merchant", "d-category", "d-usage", "d-story"]
  .forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    const evt = el.tagName === "SELECT" ? "change" : "input";
    el.addEventListener(evt, scheduleSpeculative);
  });

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

/* 투기 상태 초기화 — 새 사건으로 넘어갈 때 낡은 record 재사용 방지 */
function resetSpec() {
  clearTimeout(spec.debounceTimer);
  spec.gen += 1;      // 진행 중 발사가 있어도 STALE 처리되게 세대 올림
  spec.latest = null;
}

/* 증거를 다시 제출하겠소 → 기소 화면으로, 조서 상태 초기화 */
document.getElementById("btn-retry-intake").addEventListener("click", () => {
  state.dossier = null;
  state.intakeDossier = null;
  state.trial = null;
  state.answers = [];
  resetSpec();
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
  ERSD: { name: "절제하며 패션과 스타일을 중시하는 활동가", emoji: "👔" },
  EIFQ: { name: "변화와 도전을 꿈꾸는 차분한 관리자", emoji: "🌱" },
  EIFD: { name: "절제가 쉽지 않아 고민 중인 활동가", emoji: "🎢" },
  EISQ: { name: "절제가 쉽지 않지만 노력 중인 멋쟁이", emoji: "💄" },
  EISD: { name: "패션과 스타일을 중시하는 외향형 활동가", emoji: "🕶️" },
  GRFQ: { name: "절제하며 만남을 즐기는 차분한 스타일", emoji: "🍵" },
  GRFD: { name: "절제하며 만남을 즐기는 활동가", emoji: "🍻" },
  GRSQ: { name: "자유로운 성향의 쇼핑 멋쟁이", emoji: "🎁" },
  GRSD: { name: "자유로운 영혼의 패션 활동가", emoji: "👗" },
  GIFQ: { name: "낭만과 감성을 아는 자유로운 영혼", emoji: "🌙" },
  GIFD: { name: "낭만과 감성을 아는 기분파 활동가", emoji: "🎪" },
  GISQ: { name: "차분하고 조용한 자유로운 영혼", emoji: "🎧" },
  GISD: { name: "패션과 낭만을 중시하는 외향형 활동가", emoji: "🕺" },
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
      playVerdict(data);
    } catch (err) {
      handleError(err);
    }
  });
}

/* ══════════════════════════════════════════════════════════
 *  판결 연출 (순서 + 스킵)
 * ══════════════════════════════════════════════════════════ */
const STAMP_FILE = { GUILTY: "guilty", PROBATION: "probation", INNOCENT: "innocent" };
let verdictTimers = [];

function clearVerdictTimers() {
  verdictTimers.forEach((t) => clearTimeout(t));
  verdictTimers = [];
}

function playVerdict(v) {
  clearVerdictTimers();
  duckBgm(); // 도장·낭독이 묻히지 않게 BGM 1.5초 덕킹
  showScreen("verdict");

  const gavel = document.getElementById("verdict-gavel");
  const stamp = document.getElementById("verdict-stamp");
  const label = document.getElementById("verdict-label");
  const paper = document.getElementById("verdict-paper");
  const typeCard = document.getElementById("type-card");
  const costStrip = document.getElementById("cost-strip");
  const actions = document.getElementById("verdict-actions");
  const skipBtn = document.getElementById("btn-skip-verdict");

  // 초기 상태: 전부 숨김
  [gavel, stamp, label, paper, typeCard, costStrip, actions].forEach((el) => {
    if (el) el.hidden = true;
  });
  skipBtn.hidden = false;

  // 도장/유형 준비
  stamp.src = `/static/assets/stamp-${STAMP_FILE[v.guilt] || "guilty"}.svg`;
  label.textContent = v.guiltLabel || "";

  const at = (ms, fn) => verdictTimers.push(setTimeout(fn, ms));

  // ① 의사봉 쿵쿵쿵 (효과음: 팀 제공 판사봉 3.2초, 음소거 시 무음)
  gavel.hidden = false;
  gavel.classList.remove("go"); void gavel.offsetWidth; gavel.classList.add("go");
  if (!tts.muted) {
    try {
      const knock = new Audio("/static/assets/gavel-knock.m4a");
      knock.volume = 0.8;
      knock.play().catch(() => { /* 자동재생 거부 등은 조용히 무시 */ });
    } catch (_e) { /* 효과음 실패해도 연출은 계속 */ }
  }

  // ② 도장 쾅 (1.1s 후)
  at(1100, () => {
    gavel.hidden = true;
    stamp.hidden = false;
    stamp.classList.remove("go"); void stamp.offsetWidth; stamp.classList.add("go");
    label.hidden = false;
  });

  // ③ 판결문 라벨 섹션 (2.0s) + TTS(전문 낭독)
  at(2000, () => {
    fillVerdictDoc(v);
    paper.hidden = false;
    speak(v.verdictText || "");
  });

  // ④ 유형 카드 (2.5s)
  at(2500, () => {
    fillTypeCard(v);
    typeCard.hidden = false;
  });

  // ⑤ 회당 단가 + 액션 (3.0s)
  at(3000, () => {
    fillCostStrip(v);
    actions.hidden = false;
    skipBtn.hidden = true;
  });
}

/* 판결문 라벨 섹션 채우기 (계약 6개 섹션 순서) */
function fillVerdictDoc(v) {
  const set = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  };
  // 피고인: 이메일 @ 앞부분
  const who = (state.email || "").split("@")[0] || "피고인";
  set("v-defendant", who);
  set("v-crime", v.crime || "죄명 없음");

  const evUl = document.getElementById("v-evidence");
  evUl.innerHTML = "";
  (Array.isArray(v.evidence) ? v.evidence : []).forEach((e) => {
    const li = document.createElement("li");
    li.textContent = e;
    evUl.appendChild(li);
  });

  set("v-reasoning", v.reasoning || "");
  set("v-guilt", v.guiltLabel || "");
  set("v-sentence", v.sentence || "");
  set("v-typename", v.typeName || "");
}

/* 유형 카드: 한글명 한 줄, 길이 기반 폰트 자동 축소 (줄바꿈 금지) */
function fillTypeCard(v) {
  document.getElementById("type-emoji").textContent = v.typeEmoji || "";
  const nameEl = document.getElementById("type-name");
  nameEl.textContent = v.typeName || "";
  nameEl.style.fontSize = typeNameFontSize(v.typeName || "");
}

/* 길이 기반 축소 램프. 최장 "절제하며 패션과 스타일을 중시하는 활동가"(공백 포함 22자)가
 * 프레임 폭(≈86%) 안에서 nowrap 한 줄로 들어가도록 잡았다. */
function typeNameFontSize(name) {
  const n = (name || "").length;
  if (n <= 9) return "1.5rem";
  if (n <= 12) return "1.25rem";
  if (n <= 15) return "1.05rem";
  if (n <= 18) return "0.9rem";
  if (n <= 21) return "0.78rem";
  return "0.68rem";
}

function fillCostStrip(v) {
  const strip = document.getElementById("cost-strip");
  const tag = document.getElementById("cost-tag");
  if (v.costPerUse != null) {
    tag.textContent = `회당 단가 ${won(v.costPerUse)}`;
    strip.hidden = false;
  } else {
    strip.hidden = true;
  }
}

/* 연출 스킵: 모든 요소 즉시 표시 */
function skipVerdict() {
  clearVerdictTimers();
  stopSpeaking();
  const v = state.verdict || {};

  const gavel = document.getElementById("verdict-gavel");
  if (gavel) gavel.hidden = true;

  const stamp = document.getElementById("verdict-stamp");
  stamp.src = `/static/assets/stamp-${STAMP_FILE[v.guilt] || "guilty"}.svg`;
  stamp.hidden = false;
  document.getElementById("verdict-label").hidden = false;
  document.getElementById("verdict-label").textContent = v.guiltLabel || "";

  fillVerdictDoc(v);
  document.getElementById("verdict-paper").hidden = false;

  fillTypeCard(v);
  document.getElementById("type-card").hidden = false;

  fillCostStrip(v);
  document.getElementById("verdict-actions").hidden = false;
  document.getElementById("btn-skip-verdict").hidden = true;
}

document.getElementById("btn-skip-verdict").addEventListener("click", skipVerdict);
document.getElementById("btn-new-trial").addEventListener("click", () => {
  resetTrialState();
  showScreen("intake");
});

function resetTrialState() {
  state.dossier = null;
  state.intakeDossier = null;
  state.trial = null;
  state.answers = [];
  state.plea = null;
  state.verdict = null;
  if (typeof resetSpec === "function") resetSpec();
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
document.getElementById("btn-records-new").addEventListener("click", () => {
  resetTrialState();
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
