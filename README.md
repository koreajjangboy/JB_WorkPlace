# JB WorkPlace

내 AI 작업을 한 페이지에서 보고, Claude Code에 작업을 지시하는 로컬 웹앱.
설계: [docs/MVP-design.md](docs/MVP-design.md)

## 현재 단계: MVP 완료 (M1~M4)

**M1 보기**
- `C:\dev` 바로 아래의 git 저장소를 프로젝트로 등록 (브랜치, 저장 안 된 변경, 마지막 커밋)
- git이 아니어도 그 폴더에서 Claude Code 세션을 열었으면 프로젝트로 등록
- Claude Code 세션 기록(`~/.claude/projects`)을 읽어 프로젝트별 세션, 토큰, 비용, 대화 내용 보기
- 서버 시작 시 자동 스캔, 화면 오른쪽 위 [다시 스캔]으로 수동 스캔

**M2 지시**
- [새 작업]에서 프로젝트를 고르고 지시를 쓰면 Claude Code가 그 프로젝트 폴더에서 실행된다
- 작업 상세 화면에서 메시지, 도구 호출, 도구 결과, 거부된 동작을 실시간으로 본다 (SSE)
- [다시 지시]는 같은 Claude 세션을 이어서 실행한다 (`--resume`)
- [중단], 시간 제한, 비용 상한, 동시 실행 수 제한
- 서버가 실행 도중 꺼지면 다음 시작 때 그 실행을 실패로 표시하고 남은 프로세스를 끝낸다

**실행 한도**
- 새 작업 화면에서 작업마다 한도를 고른다: 짧은 작업(기본 $2·30분) / 긴 작업($10·120분) / 직접 입력(최대 $50·480분)
- 작업 상세 화면의 "실행 한도 · 변경"으로 다음 실행부터 바꿀 수 있다
- 비용·시간 한도에 걸리거나 서버 재시작으로 멈추면 [이어서 계속] 버튼이 나온다.
  같은 Claude 세션에서 "멈춘 지점부터 계속" 지시로 이어 간다 (바뀐 파일은 그대로 남아 있음)
- 비용 한도는 턴 사이에 확인하므로 조금 넘을 수 있다

**Claude 사용 한도**
- 실행 중에 Claude Code가 알려주는 구독 사용률(5시간·7일)과 초기화 시각을 저장해 홈 화면에 보여준다
- 터미널 등 다른 곳에서 쓴 사용량도 포함된 계정 전체 값이다

**검토와 커밋** (M3 일부)
- 첫 실행 직전의 저장 안 된 변경을 기록해 두고, 이 작업이 바꾼 파일만 골라 보여준다
  (작업 전부터 바뀌어 있던 파일을 또 고쳤으면 "작업 전부터 변경"으로 표시하고 기본 선택에서 뺀다)
- 파일별 diff 보기, 커밋할 파일 선택
- Claude가 남긴 커밋 메시지 초안을 미리 채워 주고, 고친 뒤 [승인하고 커밋]
- 커밋은 에이전트가 아니라 WorkPlace가 이 PC의 git 설정으로 한다. 고른 파일만 커밋하고
  미리 스테이징돼 있던 다른 파일은 섞지 않는다. push는 하지 않는다
- [커밋 없이 완료]: 직접 커밋했거나 바꾼 파일이 없는 작업
- [되돌리기…]: 고른 파일을 첫 실행 직전 상태로 되돌린다. 파일마다 어떻게 되는지(지워짐 / 마지막 커밋으로 /
  작업 전 내용으로) 보여주고 확인을 받는다. 작업 전부터 바꿔 둔 파일도 그때 내용으로 정확히 돌아간다
  (5MB 이하 파일은 첫 실행 때 내용 사본을 git 객체로 저장해 둔다. 더 큰 파일은 되돌릴 수 없다)

**작업 보드**
- 작업 화면 기본 보기는 칸반: 할 일 → 실행 중 → 리뷰·실패 → 완료. [목록]으로 바꾸면 상태별 필터

**프로젝트 변경 사항** (`/projects/:id/changes`)
- 프로젝트 목록이나 상세 화면의 "저장 안 된 변경 N"을 누르면, 작업과 상관없이 그 프로젝트의 저장 안 된 변경을 모두 본다
- 파일별 diff, 바이너리·큰 파일 표시, 커밋할 파일 선택
- [Claude에게 메시지 쓰게 하기]: 고른 파일의 내용과 저장소의 기존 커밋 스타일을 보고 메시지 초안을 쓴다
  (읽기 전용 실행, 세션 기록 안 남김, 기본 모델 `sonnet`, 1회 비용 상한 $0.5)
- 메시지를 확인·수정한 뒤 [승인하고 커밋·push]. 고른 파일만 커밋한다

**push**
- 커밋 화면(작업 검토, 프로젝트 변경 사항)의 "커밋 후 바로 push"가 기본으로 켜져 있다
- 프로젝트 화면에 원격 브랜치, push 안 된 커밋 수(↑), 원격에만 있는 커밋 수(↓)와 [push] 버튼
- [원격 확인]: `git fetch`로 원격의 최신 상태를 가져와 ↓ 숫자를 갱신한다 (내 파일은 바꾸지 않는다)
- push는 에이전트가 아니라 WorkPlace가 이 PC의 git 인증으로 한다. 강제 push는 하지 않는다
- 원격 브랜치가 아직 없으면 `origin`에 같은 이름으로 만들고 연결한다 (`push -u`)
- 원격에 내 PC에 없는 커밋이 있어 거부되거나 인증이 필요하면, 이유를 보여주고 멈춘다
  (WorkPlace는 비밀번호를 묻지 않는다. 인증이 안 돼 있으면 터미널에서 한 번 직접 push해 로그인해 둔다)
- 커밋이 성공하고 push만 실패하면 커밋은 그대로 남고, 나중에 [push] 버튼으로 다시 올릴 수 있다

### 실행 안전장치

Claude Code는 아래 옵션으로 실행된다 ([runner.py](backend/src/jb_workplace/runner.py)).

- `--restricted`: 사용자·프로젝트 설정 파일을 무시하고, 파일 도구를 프로젝트 폴더 안으로 제한
- `--strict-mcp-config`: MCP 서버를 쓰지 않음
- `--permission-prompts none` + `--allowedTools`: 허용 목록에 없는 동작은 묻지 않고 거부
- `--disallowedTools`: 커밋, push, reset, 삭제, 인터넷 접속은 항상 거부
- `--max-budget-usd`: 실행 1회당 비용 상한
- 지시는 명령줄이 아니라 표준 입력으로 전달

`git status`, `git diff` 같은 읽기 전용 명령은 Claude Code가 스스로 허용한다.

**M4 대시보드·사용량**
- 홈: 최근 7일/30일 AI 비용(환산, 지난 기간 대비), provider 수, 실행 중·리뷰 대기, 저장 안 된 변경·push 안 된 커밋
- AI 사용량: 일별 비용 누적 막대(상위 5개 provider + 기타), provider 순위와 추이, 전체/텍스트/미디어 필터
- 사용량 화면(`/usage`): 7·30·90일, provider별 고유 단위 사용량(토큰·문자·크레딧·초 …), 모델별·프로젝트별, 이름·종류·색 설정, 단가표
- provider는 고정 목록이 아니다. 처음 기록이 들어오면 자동 등록되고, 단가가 없으면 "단가 없음"으로 표시된다
- 비용 = 기록에 있는 실제 비용, 없으면 단가표(모델별 → provider 공통). 단가를 고치면 과거 기록도 다시 계산된다
- Claude: 세션 기록(하위 에이전트 포함)에서 날짜·모델별 토큰을 자동 수집. 기본 단가는 Anthropic 공식 단가로 넣어 두었다
  (Team 플랜이면 실제 청구가 아니라 사용 한도에서 차감되는 양을 API 단가로 환산한 값)
- 다른 provider: 각 프로젝트에 `clients/python/jb_usage.py`를 복사해 기록한다

```python
from jb_usage import record_usage, record_openai, record_gemini

record_usage("runway", unit="credit", quantity=50, model="gen4_turbo", kind="video")
record_usage("elevenlabs", unit="char", quantity=len(text), kind="audio")
record_openai(response)                       # OpenAI(또는 provider="upstage") 응답의 토큰 수
record_gemini(response)                       # google-genai 응답의 토큰 수
```

WorkPlace 서버가 꺼져 있어도 앱은 그대로 동작한다 (기록만 빠진다). 주소는 `JB_WORKPLACE_URL`, 프로젝트 이름은 `JB_WORKPLACE_PROJECT`로 바꿀 수 있다.

## 구성

```
backend/   FastAPI + SQLModel + PostgreSQL (uv)
frontend/  React + Vite + Tailwind
scripts/   setup_db.ps1 (전용 DB 계정 만들기)
clients/   python/jb_usage.py (다른 프로젝트에서 사용량 보내기)
docs/      설계 문서
```

## 처음 한 번

1. PostgreSQL에 전용 계정과 DB 만들기 (postgres 관리자 비밀번호를 물어봄)
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\setup_db.ps1
   ```
   `backend\.env`가 없으면 무작위 비밀번호로 만들어 준다. `.env`는 git에 올리지 않는다.
2. 테이블 만들기
   ```powershell
   cd backend; uv run alembic upgrade head
   ```
3. 프론트엔드 패키지 설치
   ```powershell
   cd frontend; npm install
   ```

## 실행

터미널 두 개에서 각각 실행한 뒤 http://localhost:5173 을 연다.

```powershell
cd backend; uv run jb-workplace
```

```powershell
cd frontend; npm run dev
```

- 백엔드: http://127.0.0.1:8000 (API는 `/api/...`, 문서는 `/docs`)
- 두 서버 모두 이 PC(127.0.0.1)에서만 접속할 수 있다.

## 설정 (`backend/.env`)

| 이름 | 기본값 | 설명 |
|---|---|---|
| `DATABASE_URL` | — | PostgreSQL 접속 주소 |
| `SCAN_ROOTS` | `C:\dev` | 프로젝트를 찾을 폴더. 쉼표로 여러 개 |
| `CLAUDE_PROJECTS_DIR` | `~\.claude\projects` | Claude Code 세션 기록 폴더 |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | CORS 허용 주소 |
| `CLAUDE_EXE` | (자동 탐색) | claude 실행 파일 경로. 비우면 npm 전역 설치 위치와 PATH에서 `claude.exe`를 찾음 |
| `RUNNER_TOOLS` | `Read,Edit,Write,Glob,Grep,Bash` | 실행에 노출할 도구 |
| `RUNNER_ALLOWED_TOOLS` | 읽기·수정·테스트·빌드·린트·git 읽기 | 묻지 않고 허용할 도구와 명령 |
| `RUNNER_DISALLOWED_TOOLS` | 커밋·push·reset·checkout·삭제·웹 | 항상 거부할 명령 |
| `RUNNER_MAX_CONCURRENT` | `1` | 동시에 실행할 수 있는 작업 수 |
| `RUNNER_MAX_MINUTES` | `30` | 실행 1회 최대 시간 (넘으면 중단) |
| `RUNNER_MAX_BUDGET_USD` | `2.0` | 실행 1회 비용 상한 |
| `RUNNER_MODEL` | (기본 모델) | 실행에 쓸 모델 (예: `sonnet`, `opus`) |
| `COMMIT_MESSAGE_MODEL` | `sonnet` | 커밋 메시지 초안을 쓸 모델 |
| `COMMIT_MESSAGE_BUDGET_USD` | `0.5` | 커밋 메시지 초안 1회 비용 상한 |
