# JB WorkPlace

내 AI 작업을 한 페이지에서 보고, Claude Code에 작업을 지시하는 로컬 웹앱.
설계: [docs/MVP-design.md](docs/MVP-design.md)

## 현재 단계: M2 (지시)

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

**검토와 커밋** (M3 일부)
- 첫 실행 직전의 저장 안 된 변경을 기록해 두고, 이 작업이 바꾼 파일만 골라 보여준다
  (작업 전부터 바뀌어 있던 파일을 또 고쳤으면 "작업 전부터 변경"으로 표시하고 기본 선택에서 뺀다)
- 파일별 diff 보기, 커밋할 파일 선택
- Claude가 남긴 커밋 메시지 초안을 미리 채워 주고, 고친 뒤 [승인하고 커밋]
- 커밋은 에이전트가 아니라 WorkPlace가 이 PC의 git 설정으로 한다. 고른 파일만 커밋하고
  미리 스테이징돼 있던 다른 파일은 섞지 않는다. push는 하지 않는다
- [커밋 없이 완료]: 직접 커밋했거나 바꾼 파일이 없는 작업

### 실행 안전장치

Claude Code는 아래 옵션으로 실행된다 ([runner.py](backend/src/jb_workplace/runner.py)).

- `--restricted`: 사용자·프로젝트 설정 파일을 무시하고, 파일 도구를 프로젝트 폴더 안으로 제한
- `--strict-mcp-config`: MCP 서버를 쓰지 않음
- `--permission-prompts none` + `--allowedTools`: 허용 목록에 없는 동작은 묻지 않고 거부
- `--disallowedTools`: 커밋, push, reset, 삭제, 인터넷 접속은 항상 거부
- `--max-budget-usd`: 실행 1회당 비용 상한
- 지시는 명령줄이 아니라 표준 입력으로 전달

`git status`, `git diff` 같은 읽기 전용 명령은 Claude Code가 스스로 허용한다.

## 구성

```
backend/   FastAPI + SQLModel + PostgreSQL (uv)
frontend/  React + Vite + Tailwind
scripts/   setup_db.ps1 (전용 DB 계정 만들기)
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
