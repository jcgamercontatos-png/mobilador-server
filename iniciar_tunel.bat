@echo off
title MOBILADOR - TUNEL PUBLICO
cd /d "%~dp0"
cls
echo ============================================
echo        MOBILADOR - ACESSO PUBLICO
echo ============================================
echo.
echo [1] Iniciar servidor local...
start "" /B python main.py
timeout /t 3 /nobreak >nul
echo     OK - Servidor rodando na porta 8000
echo.
echo [2] Conectando ao Cloudflare Tunnel...
echo     (gratis, sem cadastro)
echo.
echo     URL sera exibida abaixo. Copie e cole no navegador.
echo.
"C:\Users\JCGAMER\AppData\Local\Temp\cloudflared.exe" tunnel --url http://localhost:8000
echo.
pause
