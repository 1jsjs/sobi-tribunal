---
inclusion: always
---

# 스택·환경 제약 + 실측으로 당한 함정 (v3 — 변경 제안 금지)

## 확정 스택
- Frontend: 순수 HTML + CSS + JS (프레임워크·빌드 없음, FastAPI가 static/ 서빙)
- Backend: FastAPI + SQLite(내장 sqlite3) — 테이블은 `verdicts` 하나
- AI: Bedrock Claude — **호출 지점 3곳뿐. 새로 늘리지 말 것.**
  1. 사진 → 조서 추출 (비전, services/intake_service.py)
  2. 질문 뱅크를 그 물건 맞춤으로 일괄 재작성 (services/trial_service.py, 재판 시작 시 1회)
  3. 판결문 산문 생성 (services/verdict_service.py)
  축 판정·유죄 점수·유형 확정은 전부 룰이다. 3곳 모두 실패 시 폴백이 있어 재판은 끝까지 간다.
- 음성: **브라우저 Web Speech API만 사용** (아래 §TTS/STT). AWS Polly·Transcribe는 권한 차단.
- 배포: EC2 18.135.105.80 + nohup + 포트 8501 (`appenv/bin/python -m uvicorn`)

## 환경 제약 (실측 확인)
- 외부 포트는 **8501 하나** (+ SG에 80/443은 열려 있으나 미사용이 기본)
- AWS는 **Bedrock과 S3만** 사용 가능. Polly/Transcribe/DynamoDB/Lambda/Textract 등 제안 금지
- Bedrock 모델 ID: `global.anthropic.claude-sonnet-5` (global. 접두사 필수)
- region_name 하드코딩 금지(서버 env AWS_DEFAULT_REGION=eu-west-2), Access Key 발급 금지
- 로컬에는 AWS 자격증명이 없다. 로컬 확인은 `MOCK_AI=1` (Bedrock 로컬 실패가 정상)
- S3 presigned URL은 `endpoint_url="https://s3.eu-west-2.amazonaws.com"` 지정 필수(안 하면 403)

## TTS / STT (음성)
- **TTS(판사 음성) = `speechSynthesis` (Web Speech API), P0.**
  - ko-KR 보이스 선택, rate 0.95 / pitch 0.7 (낮고 근엄하게). 로봇 티가 나는 건 컨셉으로 안는다.
  - 보이스 목록은 비동기 로드 → `voiceschanged` 이벤트 후 고를 것. 음소거 토글 필수.
  - 자동재생 정책: 첫 사용자 제스처(버튼 클릭) 이후에만 speak 호출.
- **STT(음성 답변) = P1, 기본은 선택지 탭.**
  - `SpeechRecognition`은 마이크라서 **secure context 필수** → `http://18.135.105.80:8501`에서는
    브라우저가 차단한다(로컬 localhost는 됨). HTTP 배포에서 STT를 P0로 잡지 말 것.
  - 구현은 최후 변론(plea) 입력에만 붙이고, `window.isSecureContext` false면 버튼 자체를 숨긴다.

## 실측으로 당한 함정 (같은 실수 반복 금지)

### 1. Bedrock 응답에서 `content[0]["text"]`를 꺼내지 말 것
Claude Sonnet 5는 content 첫 블록으로 **thinking**을 반환할 수 있다. KeyError → 조용히 폴백
→ AI 실종(화면은 멀쩡). 반드시 `type == "text"` 블록을 찾아 쓸 것. max_tokens은 2048 이상.

### 2. Bedrock 요청에 `temperature`·`top_p`를 넣지 말 것
Sonnet 5가 거부한다(`ValidationException: deprecated for this model`). 파라미터 없음만 OK.

### 3. FastAPI가 400 대신 422를 내는 경로를 만들지 말 것
검증 실패는 항상 **400 + `{"success": false, "error": {code, message}}`**.
`body: dict = Body(...)`·`Query(...)`·경로 변수 타입 지정은 FastAPI가 선검증해 422를 낸다.
어노테이션 없이 `Body(None)`/`Query(None)`/`File(None)`로 받아 직접 검증할 것.
main.py에 전역 RequestValidationError 핸들러(422→400 변환)를 처음부터 넣는다.

### 4. 라우트 등록 순서
경로 변수 라우트는 고정 경로보다 뒤에. 업로드류 경로는 하위에 두지 말고 `/api/intake`처럼 평평하게.

### 5. 로컬 MOCK 통과를 신뢰하지 말 것
MOCK은 Bedrock 요청 형식 오류도, Bedrock의 판단도 흉내 못 낸다(temperature 사건·분류 불일치 실증).
Bedrock 관여 기능은 배포 후 `app.log`의 "Bedrock 호출 실패" 카운트까지 확인해야 완료다.

### 6. 비전 오독을 전제로 설계할 것
영수증 실측에서 금액·날짜는 정확했지만 **품목명 오독**이 있었다(브로콜리→보로커피).
조서는 반드시 사용자 확인·수정 단계를 거친 뒤에만 재판에 쓴다.

### 7. curl로 한글 쿼리를 보낼 땐 `--data-urlencode`
안 쓰면 uvicorn이 `Invalid HTTP request`로 뱉는다. 검증 스크립트에서 주의.

## 작업 규칙
- 설계 원본은 docs/ + steering. 여기 없는 기능을 임의로 추가하지 말 것
- 필드명은 camelCase 계약 그대로. 16유형·질문 뱅크·점수표는 **constants.py가 단일 출처**
- task 한 번에 하나, 항상 실행 가능한 상태 유지
- 서버 재기동 전 이전 프로세스 정리(`lsof -ti:8501 | xargs kill -SIGTERM`)
- 데모 시드(전과 기록 5건)는 시연의 핵심 — 테스트 행만 지우고 시드는 훼손 금지
