# JB_WorkPlace MVP 설계안

- 작성일: 2026-11-16
- 상태: M1(보기), M2(지시), M3(검토: diff·커밋·push·되돌리기·칸반) 완료 · 다음은 M4(대시보드·사용량)

---

## 1. 목표

PC 한 대에서 혼자 쓰는 **로컬 웹앱**이다. `C:\dev`에서 진행 중인 모든 AI 작업을 **한 페이지 대시보드**에서 보고, **WorkPlace**에서 프로젝트를 골라 Claude Code에 작업을 지시하고 결과를 검토한다.

### 1.1 진행 방향
- [Mission Control](https://github.com/builderz-labs/mission-control)을 **참고하되, 포크하지 않고 처음부터 작게 개발**한다.
  - Mission Control은 알파 버전이라 API와 DB 구조가 자주 바뀌어서, 포크하면 원본 업데이트를 따라가기 어렵다.
  - 역할·권한, 감사 로그 같은 팀 운영 기능이 대부분이라 개인용으로는 과하다.
  - `C:\dev`의 프로젝트와 세션 기록을 모으는 핵심 기능은 어차피 새로 만들어야 한다.
  - 주로 쓰는 스택(Python)과 맞춘다.
- Mission Control은 MIT 라이선스라서, 저작권 표시만 지키면 UI 구성이나 일부 코드를 참고하거나 가져와도 된다.

### 1.2 참고한 레퍼런스

| 분류 | 레퍼런스 | 참고할 점 |
|---|---|---|
| 전체 구조 | Mission Control (builderz-labs) | 작업 배정 → 실행 → 리뷰 → 승인 흐름, 비용 보기, 홈 대시보드 구성 |
| 지시 UX | KanBots | 실시간 실행 기록(도구 호출과 결과), 클릭으로 결정하는 방식 |
| 화면 레이아웃 | Vibe Kanban | 칸반 + 작업 공간 + diff 리뷰 구성 (서비스 종료 중이라 참고용으로만) |
| 실행 추적 | Langfuse, Opik | 직접 만들지 않고 나중에 연동 |

---

## 2. MVP 범위

| MVP에 포함 | MVP에서 제외 (나중에) |
|---|---|
| 프로젝트 목록 자동 수집 (`C:\dev` 안의 git 저장소) | 여러 사용자, 로그인, 권한 |
| 과거 Claude Code 세션 불러와서 보기 | Codex, Gemini CLI 등 다른 코딩 에이전트 실행 |
| 작업 등록 → Claude Code 실행 → 결과 확인 | 정기 실행(cron), 알림 |
| 4개 컬럼 칸반 | 메모리 브라우저, 지식 그래프 |
| 실행 로그를 실시간으로 보기 | Langfuse/Opik 연동 |
| 리뷰 단계 (사람이 승인해야 완료) | 자동 PR 생성, 머지 |
| provider 종류에 상관없는 AI 사용량·비용 집계 | provider 사용량 API로 청구액 대조 |

---

## 3. 화면

메뉴: **홈 · 작업 보드 · 프로젝트 · 사용량**, 오른쪽 위에 [새 작업] 버튼

### 3.1 홈 (대시보드)

```
┌──────────────────────────────────────────────────────────────────┐
│ JB WorkPlace            홈  작업 보드  프로젝트  사용량  [+ 새 작업] │
├──────────────────────────────────────────────────────────────────┤
│ [이번 기간 비용] [사용 중인 provider] [실행 중] [리뷰 대기]           │
├──────────────────────────────────────────────────────────────────┤
│ AI 사용량  (새 provider: Luma · 단가 미입력)                         │
│                       [전체|텍스트|미디어]  [7일|30일]               │
│ ┌ 일별 비용 누적 막대 ──────────┐ ┌ provider 순위 ──────────────┐   │
│ │ 상위 5개 + 기타 N개           │ │ 이름 · 추이 · 비용 · %       │   │
│ │                              │ │ (상위 5개, [나머지 보기])     │   │
│ └──────────────────────────────┘ └─────────────────────────────┘   │
├──────────────────────────────────────────────────────────────────┤
│ ┌ 주목할 작업 ─────────────────┐ ┌ 최근 활동 (Live) ───────────┐    │
│ │ 리뷰 / 실행 중 / 실패         │ │ 시간순 이벤트                 │    │
│ │ 프로젝트 · provider · 비용    │ │                              │    │
│ └──────────────────────────────┘ └─────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

- **지표 카드 4개**: 이번 기간 비용(지난 기간 대비 증감), 사용 중인 provider 수(신규 수), 실행 중인 작업, 리뷰 대기 작업
- **AI 사용량**
  - 비용(달러)을 공통 기준으로 쓴다. 영상·음성 provider는 토큰이 없기 때문이다.
  - 차트는 **상위 5개 provider만 각자 색**으로 보여주고, 나머지는 회색 **"기타 N개"**로 묶는다.
  - 기간이나 종류 필터를 바꾸면 상위 5개를 다시 계산한다.
  - 오른쪽 순위 목록은 기본적으로 상위 5개만 보여주고 [나머지 N개 보기]로 펼친다. 줄마다 작은 추이 그래프를 넣는다.
  - 처음 기록된 provider에는 "신규" 배지와 "단가 미입력" 안내를 표시한다.
- **주목할 작업**: 리뷰 대기, 실행 중, 실패한 작업만 모은다. 줄마다 프로젝트, 사용한 provider, 비용을 표시한다.
- **최근 활동**: 프로젝트를 가리지 않고 모든 이벤트를 시간순으로 보여준다.

### 3.2 작업 보드 (칸반)
- 컬럼: **할 일 → 실행 중 → 리뷰 → 완료**
- 카드: 프로젝트, 제목, 상태, 경과 시간 (리뷰 카드는 변경된 파일 수)
- 맨 위 입력줄: [프로젝트 선택] [지시 입력] [등록] [바로 실행]

### 3.3 작업 상세 (WorkPlace의 핵심)
- **왼쪽**: 실시간 실행 기록. 지시, 에이전트가 호출한 도구(Read, Edit, Bash 등), 도구 결과, 완료 메시지가 순서대로 올라온다.
- **오른쪽**: 바뀐 파일 목록과 diff (`git diff`)
- **아래**: 추가 지시 입력창. 같은 세션을 이어서 지시한다.
- **버튼**: [승인 → 완료] / [다시 지시] / [중단] / [변경 되돌리기]
- **상단**: 프로젝트, 실행 횟수, 토큰, 비용, 소요 시간

### 3.4 프로젝트
- 프로젝트 목록: 경로, 브랜치, 저장 안 된 변경, 마지막 세션
- 프로젝트를 누르면 과거 Claude Code 세션 목록이 나오고, 세션을 누르면 대화 내용을 볼 수 있다.

### 3.5 사용량
- provider별 상세: 원래 단위 사용량(토큰, 문자, 크레딧, 초, 건수), 모델별 사용량, 프로젝트별 사용량
- 토큰 / 비용 전환, 종류(텍스트 / 미디어) 필터
- 단가표 관리: provider·모델별 단가 입력과 적용 기간 설정

---

## 4. 기술 스택

| 영역 | 선택 | 이유 |
|---|---|---|
| 백엔드 | Python + FastAPI, `uv`로 관리 | 지금 쓰는 스택과 같음 |
| DB | **로컬 PostgreSQL 18** (이미 설치되어 자동 실행 중) | JSONB, 기간별 집계, 동시 기록, 나중에 pgvector나 서버 배포로 확장 가능 |
| ORM / 마이그레이션 | SQLModel + psycopg, Alembic | 테이블 구조 변경 이력 관리 |
| 프론트 | React (Vite) + Tailwind, Chart.js | 칸반 드래그, 실시간 로그, 차트 |
| 실시간 전달 | SSE | 서버에서 화면으로 보내는 한 방향이면 충분하고 WebSocket보다 단순함 |

- WorkPlace 전용 `jb_workplace` DB와 전용 계정을 만들어서 기존 DB와 분리한다.
- DB 접속 정보는 `.env`에 두고 git에 올리지 않는다.

---

## 5. 아키텍처

```
[브라우저 UI] ──HTTP/SSE──> [FastAPI 서버] ──> PostgreSQL (jb_workplace)
                                 │
                                 ├─ Scanner : C:\dev의 git 저장소와 ~/.claude/projects 세션 기록 읽기
                                 ├─ Runner  : 프로젝트 폴더에서 `claude -p` 실행
                                 │            stream-json 출력 → Event 저장 → SSE로 화면에 전달
                                 └─ Usage API : 각 프로젝트가 보내는 사용량 기록 받기 (record_usage)
```

---

## 6. 데이터 모델 (PostgreSQL)

```
Project     : id, name, path, branch, last_activity_at

Task        : id, project_id, title, prompt,
              status(todo|running|review|done|failed), created_at, updated_at

Run         : id, task_id, session_id, started_at, ended_at, exit_code

Event       : id, run_id, ts, type(text|tool_use|tool_result|error|system),
              payload JSONB

Provider    : id, name(UNIQUE), kind(text|image|video|audio|embedding|mixed),
              color, created_at          ← 고정 목록이 아니라 데이터로 관리

UsageRecord : id, provider_id, model, project_id, run_id(nullable),
              kind, unit(token|char|credit|second|image|request|…), quantity,
              input_tokens, output_tokens (텍스트일 때만),
              cost_usd (nullable), source(session_log|app_log|usage_api), ts,
              meta JSONB                 ← provider마다 다른 추가 정보

PriceRule   : id, provider_id, model(nullable = provider 전체), unit,
              price_per_unit, valid_from, valid_to
```

- 작업 하나에 실행(Run)이 여러 번 생길 수 있다. "다시 지시"할 때마다 Run이 하나씩 추가된다.
- 과거 세션 기록(JSONL)은 처음엔 DB로 옮기지 않고, 필요할 때 파일을 직접 읽어서 보여준다.
- Claude Code 실행 기록의 토큰 사용량도 `UsageRecord`에 함께 쌓는다.

### 6.1 provider를 고정하지 않는 원칙
- provider 목록을 코드에 박아 두지 않고 `Provider` 테이블로 관리한다.
- 처음 보는 provider 이름으로 기록이 들어오면 **자동으로 등록**하고, 홈에 "새 provider 감지" 알림을 띄운다.
- 사용량 단위가 provider마다 다르므로 **비용(cost_usd)을 공통 비교 기준**으로 쓰고, 원래 단위(`unit`, `quantity`)도 함께 저장한다.
- 비용은 `PriceRule`(단가표)로 계산한다. 적용 기간이 있어서 단가가 바뀌어도 과거 기록은 그 당시 단가로 계산된다.
- 단가가 없는 provider는 사용량만 보여주고, 비용은 "단가 미입력"으로 표시한다.
- provider마다 다른 정보(영상 해상도, 음성 ID 등)는 `meta JSONB`에 넣는다. 그래서 provider가 늘어나도 테이블 구조를 바꿀 필요가 없다.
- 화면 색상은 자동으로 배정하고, 차트에서는 상위 5개만 각자 색을 쓰고 나머지는 "기타"로 묶는다.

---

## 7. 사용량 수집

| 대상 | 수집 방법 |
|---|---|
| Claude Code 세션 | 세션 기록 파일(`~/.claude/projects/*.jsonl`)을 읽는다. 토큰 정보가 들어 있는지는 M1에서 확인한다 |
| WorkPlace에서 실행한 작업 | Runner가 `stream-json` 출력에서 사용량을 기록한다 |
| 각 프로젝트 앱의 API 호출 | 공용 기록 함수 `record_usage(...)`를 호출한다 |
| (나중에) 계정 전체 사용량 | 사용량 API를 제공하는 provider는 정기적으로 수집해서 청구액과 대조한다 |

```python
record_usage(provider="runway", model="…", unit="credit", quantity=50, project="ssulgae")
```
- provider 이름은 자유 문자열이라, 새 provider를 쓰더라도 WorkPlace 쪽 코드를 고칠 필요가 없다.
- 자주 쓰는 provider는 응답에서 사용량을 자동으로 꺼내 주는 **어댑터**를 선택적으로 붙일 수 있다. 어댑터가 없어도 직접 기록하면 된다.

### 7.1 현재 확인된 provider (2026-11-16, `C:\dev` 코드와 `.env.example` 기준)

| Provider | 종류 | 사용하는 프로젝트 (일부) |
|---|---|---|
| Claude (Anthropic) | 텍스트 | Claude Code 세션, `elis_with_AI` |
| Gemini (Google) | 텍스트·음성 | `SNS-Assistant`, `Advertisement-Video-Generator`, `ax2-integrated-platform`, `app/` |
| OpenAI | 텍스트·임베딩 | `party-rag`, `practice/my-ai-assistant`, `ssulgae`, `final_project` |
| Upstage | 텍스트 | `upstage_rag`, `elis_with_AI` (OpenAI SDK로 호출하지만 접속 주소가 다름) |
| Runway | 영상 | `ssulgae`, `Advertisement-Video-Generator` |
| ElevenLabs | 음성 | `ssulgae` |
| Luma | 영상 | `Advertisement-Video-Generator` |

목록은 고정하지 않으며, 새 provider는 첫 기록이 들어올 때 자동으로 추가된다.

---

## 8. 지시 실행 흐름

1. 작업을 등록하면 상태가 `todo`가 된다.
2. [실행]을 누르면 상태가 `running`이 되고, Runner가 프로젝트 폴더에서 Claude Code를 실행한다.
   `claude -p --output-format stream-json --verbose --restricted ...` (지시는 표준 입력으로 전달, 자세한 옵션은 README의 "실행 안전장치")
3. 출력이 한 줄씩 나올 때마다 Event로 저장하고 SSE로 화면에 보낸다.
4. 실행이 끝나면 상태가 `review`가 되고, `git diff`와 사용량을 함께 기록한다.
5. 사람이 결과를 보고 고른다.
   - [승인]: `done`
   - [다시 지시]: 같은 세션을 이어서 실행(`--resume <session_id>`)하고 다시 `running`
   - [되돌리기]: 변경 사항을 버린다

---

## 9. 안전장치 (MVP부터 적용)

- **도구 제한**: 처음에는 읽기, 수정, 테스트 실행 정도만 허용한다. push, 삭제, 네트워크는 막는다.
- **동시 실행 1~2개 제한**: 비용 폭주와 파일 충돌을 막는다.
- **실행 폴더 제한**: 등록된 프로젝트 폴더 밖에서는 실행하지 않는다.
- **커밋, push 없음**: 에이전트는 파일만 바꾸고, 커밋은 사람이 직접 한다.
- **최대 실행 시간 / 비용 상한**: 시간 제한을 넘으면 자동으로 중단하고, 실행 1회 비용은 `--max-budget-usd`로 막는다. (Claude Code CLI에 최대 턴 수 옵션이 없어 비용 상한으로 대신함)
- **로컬 전용**: 서버는 `127.0.0.1`에서만 열고 외부에서 접근하지 못하게 한다.

---

## 10. 개발 단계

| 단계 | 내용 | 끝나면 할 수 있는 것 |
|---|---|---|
| **M1. 보기** | PostgreSQL 연결, 프로젝트 스캔, 세션 기록 읽기, 프로젝트·세션 화면 | 지금까지의 AI 작업을 한곳에서 보기 |
| **M2. 지시** | Task/Run/Event 모델, Runner, 작업 상세 화면(실시간 로그) | 웹에서 Claude Code에 작업을 지시하고 지켜보기 |
| **M3. 검토** | diff 보기, 승인/다시 지시/되돌리기, 칸반 보드 | 리뷰 단계가 있는 작업 흐름 완성 |
| **M4. 대시보드·사용량** | Provider/UsageRecord/PriceRule, `record_usage`, 홈 화면, 사용량 화면 | 한 페이지 대시보드와 provider별 사용량 |

M1은 실행 기능이 없어서 위험 부담 없이 시작할 수 있다.

---

## 11. 개발 전에 정할 것

1. **관리 대상**: MVP에서는 Claude Code 작업만 실행할지, `app/`의 Python 에이전트 실행도 포함할지 (추천: Claude Code만)
2. **실행 위치**: 프로젝트 폴더에서 바로 실행할지, 작업마다 별도 git worktree를 만들지
3. **스캔 범위**: `C:\dev` 전체를 볼지, 고른 프로젝트만 볼지
4. **세션 기록의 토큰 정보**: JSONL 기록에 토큰 사용량이 있는지 M1에서 확인
5. **기존 프로젝트에 `record_usage` 적용 순서**: 비용이 큰 provider(Runway, Claude 등)를 쓰는 프로젝트부터 적용할지
6. **단가 입력**: 각 provider의 실제 요금제를 확인해서 단가표 초기값을 입력해야 함

---

## 부록: 참고 링크

- Mission Control — https://github.com/builderz-labs/mission-control
- KanBots — https://github.com/leodavinci1/kanbots
- Vibe Kanban — https://github.com/BloopAI/vibe-kanban
- Langfuse — https://github.com/langfuse/langfuse
- Opik — https://github.com/comet-ml/opik
