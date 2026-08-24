@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PORT=8501"
set "URL=http://localhost:%PORT%"

echo ============================================
echo   의국 스케줄 마스터 실행 중...
echo   Chrome 시크릿 창으로 열립니다.
echo   (시크릿 = 확장 프로그램 꺼짐 + 캐시 깨끗)
echo   종료하려면 이 검은 창을 닫으세요.
echo ============================================
echo.

rem --- Chrome 실행 파일 찾기 ---
set "CHROME="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"

rem --- 서버 시작 (headless: 일반 브라우저 자동 열기 끔) ---
start "" /b "%~dp0venv\Scripts\streamlit.exe" run "%~dp0app.py" --server.port %PORT% --server.headless true

rem --- 서버가 실제로 응답할 때까지 대기 (최대 90초) ---
echo 서버 시작을 기다리는 중...
powershell -NoProfile -Command "$sw=[Diagnostics.Stopwatch]::StartNew(); while($sw.Elapsed.TotalSeconds -lt 90){ try{ $c=New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1',%PORT%); $c.Close(); exit 0 }catch{ Start-Sleep -Milliseconds 400 } }; exit 1"

if errorlevel 1 goto NOSERVER

if defined CHROME (
    echo 시크릿 창을 여는 중...
    start "" "%CHROME%" --incognito "%URL%"
) else (
    echo [!] Chrome을 찾지 못했습니다. 기본 브라우저로 엽니다.
    echo     주소: %URL%
    start "" "%URL%"
)
goto RUNNING

:NOSERVER
echo.
echo [!] 서버가 시간 내에 뜨지 않았습니다. 위 로그를 확인하세요.
echo     수동으로 접속: %URL%

:RUNNING
echo.
echo --------------------------------------------
echo  실행 중입니다. 이 창을 닫으면 종료됩니다.
echo --------------------------------------------
pause >nul
