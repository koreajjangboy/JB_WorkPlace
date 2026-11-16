# JB WorkPlace 전용 PostgreSQL 계정(jb_workplace)과 DB(jb_workplace)를 만든다.
# - backend\.env 가 없으면 무작위 비밀번호로 새로 만든다.
# - postgres 관리자 비밀번호는 psql 이 직접 물어본다 (이 스크립트는 저장하지 않음).
# 사용법:  powershell -ExecutionPolicy Bypass -File scripts\setup_db.ps1

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root 'backend\.env'
$psql = 'C:\Program Files\PostgreSQL\18\bin\psql.exe'
if (-not (Test-Path $psql)) { $psql = (Get-Command psql -ErrorAction Stop).Source }

if (-not (Test-Path $envFile)) {
    $chars = [char[]]'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    $password = -join (1..24 | ForEach-Object { $chars | Get-Random })
    $example = Get-Content (Join-Path $root 'backend\.env.example') -Raw -Encoding UTF8
    $content = $example -replace 'CHANGE_ME', $password
    [System.IO.File]::WriteAllText($envFile, $content, (New-Object System.Text.UTF8Encoding $false))
    Write-Host "backend\.env 를 만들었습니다."
}

$line = Get-Content $envFile -Encoding UTF8 | Where-Object { $_ -match '^DATABASE_URL=' } | Select-Object -First 1
if ($line -notmatch '//([^:]+):([^@]+)@[^/]+/(\w+)') { throw "backend\.env 의 DATABASE_URL 형식을 읽을 수 없습니다." }
$user = $Matches[1]; $password = $Matches[2]; $db = $Matches[3]

$sql = @"
DO `$`$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$user') THEN
    CREATE ROLE $user LOGIN PASSWORD '$password';
  ELSE
    ALTER ROLE $user LOGIN PASSWORD '$password';
  END IF;
END
`$`$;
SELECT 'CREATE DATABASE $db OWNER $user ENCODING ''UTF8'''
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$db')\gexec
"@

$tmp = New-TemporaryFile
try {
    [System.IO.File]::WriteAllText($tmp.FullName, $sql, (New-Object System.Text.UTF8Encoding $false))
    Write-Host "postgres 관리자 계정으로 접속합니다. 비밀번호를 입력하세요."
    & $psql -h localhost -U postgres -d postgres -v ON_ERROR_STOP=1 -f $tmp.FullName
    if ($LASTEXITCODE -ne 0) { throw "psql 실행 실패 (종료 코드 $LASTEXITCODE)" }
} finally {
    Remove-Item $tmp.FullName -Force
}
Write-Host "완료: 계정 '$user', DB '$db' 준비됨. 이제 backend 폴더에서 'uv run alembic upgrade head' 를 실행하세요."
