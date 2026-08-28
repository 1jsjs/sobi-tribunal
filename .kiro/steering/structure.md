---
inclusion: always
---

# 리포 구조 (v3)

```
main.py                  # FastAPI 앱, 봉투 헬퍼, 전역 422→400 핸들러, static 마운트
constants.py             # 카테고리 6종 · 16유형 · 질문 뱅크(태그 포함) · 점수표 — 단일 출처
db.py                    # SQLite 연결 + verdicts 테이블 + 마이그레이션(ALTER 방식)
routes/
  intake.py              # POST /api/intake
  trial.py               # POST /api/trial/start, POST /api/trial/verdict
  records.py             # GET /api/records, GET /api/records/{id}
services/
  llm_service.py         # LLM 공통(텍스트+비전): bedrock(서버 기본)/gemini(로컬 전용)/mock 분기
  intake_service.py      # 사진→조서 (비전 프롬프트, S3 업로드)
  trial_service.py       # 질문 플랜·스타일링·축/유죄 채점 룰
  verdict_service.py     # 판정 확정 + 판결문 생성 + 저장
data/
  seed.py                # 데모 전과 기록 5건 (demo@tribunal.kr)
static/
  index.html  style.css  app.js
  assets/                # 판사·배경·도장 SVG (assets/draft에서 선정본 복사)
tests/                   # pytest (MOCK_AI=1)
docs/                    # 판정룰표·프롬프트·작업순서 (설계 원본)
kiro-prompts/            # 태스크별 프롬프트 원문 (사람이 Kiro에 붙여넣는 용)
starter/                 # 운영진 스타터 패키지 (참고용, 수정 금지)
```

- DB 파일은 `data/database.sqlite`(gitignore됨). 판결 저장 시 자동 생성.
- 판정 룰의 원본 설계는 `docs/01-판정룰표.md` — constants.py는 그걸 옮겨 적은 것이다.
  둘이 어긋나면 docs가 맞다.
