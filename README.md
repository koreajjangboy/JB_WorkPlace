# JB WorkPlace

내 AI 작업을 한 페이지에서 보고, Claude Code에 작업을 지시하는 로컬 웹앱.
설계: [docs/MVP-design.md](docs/MVP-design.md)

## 현재 단계: M1 (보기)

- `C:\dev` 바로 아래의 git 저장소를 프로젝트로 등록 (브랜치, 저장 안 된 변경, 마지막 커밋)
- git이 아니어도 그 폴더에서 Claude Code 세션을 열었으면 프로젝트로 등록
- Claude Code 세션 기록(`~/.claude/projects`)을 읽어 프로젝트별 세션, 토큰, 비용, 대화 내용 보기
- 서버 시작 시 자동 스캔, 화면 오른쪽 위 [다시 스캔]으로 수동 스캔

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
