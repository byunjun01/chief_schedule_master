@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   의국 스케줄 마스터 실행 중...
echo   브라우저가 자동으로 열립니다.
echo   종료하려면 이 검은 창을 닫으세요.
echo ============================================
"%~dp0venv\Scripts\streamlit.exe" run "%~dp0app.py"
pause
