---
inclusion: always
---

# 프론트 ↔ 백엔드 계약 (v3 소비 재판소)

이 문서가 계약의 단일 출처다. 여기 없는 필드를 만들지 말고, 어긋나면 멈추고 알릴 것.

## 응답 봉투 (모든 API 공통)
```
성공: {"success": true, "data": ...}
실패: {"success": false, "error": {"code": "...", "message": "..."}}
```
- 프론트는 항상 `.data`를 벗겨 쓴다. `error.message`는 한국어 그대로 화면에 띄운다.
- 상태 코드: 성공 200 (**판결 확정 POST /api/trial/verdict만 201**) / 검증 실패 400 / 없음 404.
  `res.ok`로 판정하고 `status === 200` 비교 금지.

## 엔드포인트 5 + 1
| 메서드 | 경로 | 보내는 것 | 받는 것(data) |
|---|---|---|---|
| GET | /api/health | — | {message} |
| POST | /api/intake | multipart: **file** (사진 1장, jpg/png/webp ≤5MB) | {dossier, candidates, photoUrl, source} |
| POST | /api/trial/start | JSON {dossier} | {opening, questions, source} |
| POST | /api/trial/verdict | JSON {email, dossier, answers, plea?} | 판결(아래) (201) |
| GET | /api/records?email= | — | RecordSummary 배열 (최신순) |
| GET | /api/records/{id} | — | Record 상세 |

라우트 등록: `/api/records/{id}`는 `/api/records`보다 **뒤에** 등록한다.

## dossier (조서) — 재판 내내 들고 다니는 객체
```
{"itemName": "무선 이어폰", "price": 219000, "boughtAt": "2026-08-14" | null,
 "merchant": "쿠팡" | null, "category": "DIGITAL_APPLIANCE",
 "usage": "unopened" | "rare" | "often" | null, "story": "할인해서" | null,
 "photoKey": "evidence/....jpg" | null}
```
- **수동 입력은 서버를 거치지 않는다.** 프론트가 폼 값으로 dossier를 직접 만든다(photoKey null).
- POST /api/intake의 `candidates`: 결제내역 캡처에서 거래가 여러 건 보이면
  `[{itemName, price, boughtAt, merchant}]` 배열이 온다(1건이면 빈 배열).
  프론트는 "어느 건으로 기소하시겠소?" 선택 UI를 띄우고, 고른 것을 dossier에 병합한다.
- 비전은 품목명을 오독할 수 있다 — **조서 확인 화면에서 전 필드를 수정 가능하게** 한 뒤 재판에 쓴다.
- `photoUrl`: S3 presigned URL(12시간). S3 실패 시 null — 그때는 업로드한 파일의 로컬
  objectURL로 증거물 액자를 채운다(전과 기록에는 사진이 안 남는다고 안내).

## category 6종 (constants.py 단일 출처, 화면엔 한글)
```
FASHION_BEAUTY     패션·뷰티
FOOD_DINING        식음료·외식
DIGITAL_APPLIANCE  가전·디지털
HOBBY_LEISURE      취미·여가
LIVING_GROCERY     생활·식료품
OTHER              기타
```

## questions (POST /api/trial/start 응답) — 심문은 클라이언트가 진행한다
```
"opening": "피고인은 출석하시오. 사건번호 2026-tribunal, 무선 이어폰 21만 9천원 건이오.",
"questions": [
  {"id": "USE",  "axis": "GUILT", "askIf": null,
   "text": "지금 그 물건은 어디서 무엇을 하고 있소?",
   "choices": [{"label": "거의 매일 씁니다", "pole": null, "guilt": 0},
               {"label": "가끔… 생각나면 씁니다", "pole": null, "guilt": 1},
               {"label": "…아직 포장도 안 뜯었습니다", "pole": null, "guilt": 3}]},
  {"id": "EG2", "axis": "EG", "askIf": {"axis": "EG", "whenScore": 0}, ...}
], "source": "bedrock" | "fallback"
```
- id 순서 고정: `USE, EG1, RI1, FS1, QD1, EG2, RI2, RETURN` (8개 전부 항상 내려온다).
- **askIf**: null이면 무조건 질문. `{"axis":"EG","whenScore":0}`이면 그 시점까지 해당 축
  pole 합이 0일 때만 질문(EG2·RI2만 해당). → 실제 질문 수 6~8개.
- `pole`: "E"|"G"|"R"|"I"|"F"|"S"|"Q"|"D"|null. 프론트는 심증 게이지·askIf 판정에만 쓴다.
- **판정은 서버가 한다.** 판결 시 서버는 클라이언트가 보낸 pole/guilt를 무시하고
  constants.py의 원본 질문 뱅크 태그로 `answers`를 다시 채점한다(id+choiceIndex 기준).
- `source: "fallback"`이면 기본 질문 뱅크 그대로다(물건 맞춤 문구 아님). 화면 차이는 없다.

## answers (POST /api/trial/verdict 요청)
```
{"email": "pjs@jbnu.ac.kr", "dossier": {...},
 "answers": [{"questionId": "USE", "choiceIndex": 2}, ...],
 "plea": "월급날이었단 말입니다" | 생략}
```
- email: 필수. trim+소문자 정규화, `아이디@도메인.tld` 형태, 254자 이내. 위반 400 `INVALID_EMAIL`.
- answers: 최소 6건, questionId는 정의된 8개 중, choiceIndex 범위 검사. 위반 400 `INVALID_ANSWERS`.
- plea: 선택, **200자 이내**, 초과 400 `INVALID_PLEA`. 판결문에 정상참작으로 인용된다.

## 판결 (POST /api/trial/verdict 응답 data, 201)
```
{"recordId": 7, "axisCode": "GISD", "typeName": "패션과 낭만 감성을 중시하는 외향형의 활동가",
 "typeEmoji": "🕺", "guilt": "GUILTY" | "PROBATION" | "INNOCENT",
 "guiltLabel": "유죄" | "집행유예" | "무죄", "guiltScore": 8,
 "sentence": "선고한다. 피고인은 7일 이내 위 물건을 1회 이상 사용하거나 중고 장터에 등록할 것.",
 "verdictText": "판결문 산문 (Bedrock 생성, 실패 시 템플릿)",
 "evidence": ["구매 후 사용 0회", "회당 단가 219,000원", "가격 비교 없이 즉시 결제"],
 "costPerUse": 219000 | null}
```
- 프론트는 재계산 금지 — guiltScore·axisCode를 다시 구하지 않는다.
- 유형 카드: axisCode + typeName + typeEmoji로 렌더. 카드 하단에 유형 분류 출처 표기:
  "유형 분류: 소비 MBTI 16 (MPiA · blog.naver.com/ezpbill)".

## 전과 기록
- `GET /api/records?email=` — email 없거나 형식 위반 400. data = 배열:
  `{id, itemName, price, category, axisCode, typeName, typeEmoji, guilt, guiltLabel,
    sentence, createdAt, photoUrl(null 가능)}`
- `GET /api/records/{id}` — 위 + `verdictText, plea, guiltScore, evidence`. 없으면 404.
- 다른 사람 이메일을 치면 그 사람 기록이 보인다 — 데모 수준 식별이며 보안이 아니다.
  화면 문구도 "본 법정은 피고인의 양심을 믿소" 정도로 정직하게 간다.

## 값 규칙
- 날짜 `YYYY-MM-DD` 문자열 그대로(Date 변환 금지). 금액은 숫자(콤마·"원"은 표시에서만).
- 필드명 camelCase 고정.

## 응답 지연 — 로딩 연출 필수 (연출 문구까지 계약)
```
POST /api/intake        6~9초   "증거물 감식 중..."
POST /api/trial/start   5~8초   "판사님 입장 중..."
POST /api/trial/verdict 5~7초   "판결문 작성 중..."
```
심문 자체(질문 넘기기)는 서버 호출이 없어 **0초**다. 버튼 비활성화로 중복 요청 방지.

## 프론트가 하면 안 되는 것
- 판정·점수 재계산 금지(심증 게이지 표시용 합산만 예외).
- 필드명 변경 금지. 응답 봉투 무시 금지.
