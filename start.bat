@echo off
REM ======================================================================
REM  Lance le bot + le panel sur ce PC.
REM  Si CLOUDFLARE_TUNNEL_TOKEN est rempli dans .env, le tunnel Cloudflare
REM  est lance aussi : le panel devient accessible sur ton domaine.
REM  Le bot ne marche que tant que ce PC est allume et cette fenetre ouverte.
REM  (Fichier volontairement SANS accents : cmd.exe les lit mal.)
REM ======================================================================
title Bot Discord
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 goto :nopython

if exist "venv\Scripts\python.exe" goto :venv_ok
echo Creation de l'environnement Python (premiere fois, 1 a 2 minutes)...
python -m venv venv
if errorlevel 1 goto :error
"venv\Scripts\python.exe" -m pip install --upgrade pip >nul
"venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error
:venv_ok
REM Installe les nouvelles dependances eventuelles (rapide si tout est deja a jour)
"venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :error

if exist ".env" goto :env_ok
if exist ".env.example" copy ".env.example" ".env" >nul
if not exist ".env" (
    echo DISCORD_TOKEN=> ".env"
    echo DISCORD_CLIENT_SECRET=>> ".env"
    echo PUBLIC_URL=>> ".env"
    echo CONTACT=>> ".env"
    echo PORT=8080>> ".env"
    echo DEV_GUILD_ID=>> ".env"
    echo CLOUDFLARE_TUNNEL_TOKEN=>> ".env"
)
echo.
echo Le fichier .env a ete cree. Remplis-le (voir DOCUMENTATION.md, section 4),
echo enregistre, puis relance start.bat.
start "" notepad ".env"
pause
exit /b
:env_ok

REM --- Lecture de CLOUDFLARE_TUNNEL_TOKEN dans .env ---
set "TUNNEL_TOKEN="
for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
    if /i "%%A"=="CLOUDFLARE_TUNNEL_TOKEN" set "TUNNEL_TOKEN=%%B"
)

if not defined TUNNEL_TOKEN goto :notunnel
where cloudflared >nul 2>nul
if errorlevel 1 goto :nocloudflared
echo Demarrage du tunnel Cloudflare dans une autre fenetre...
start "Tunnel Cloudflare - ne pas fermer" cmd /k cloudflared tunnel --no-autoupdate run --token %TUNNEL_TOKEN%
goto :runbot

:nocloudflared
echo.
echo [!] cloudflared n'est pas installe. Installe-le avec :
echo     winget install --id Cloudflare.cloudflared
echo     puis ferme et relance start.bat.
echo     Le bot demarre quand meme, mais le panel ne sera pas en ligne.
echo.
goto :runbot

:notunnel
echo Pas de CLOUDFLARE_TUNNEL_TOKEN dans .env : panel visible seulement sur http://localhost:8080

:runbot
echo.
echo Demarrage du bot... (ferme cette fenetre ou Ctrl+C pour l'arreter)
echo.
"venv\Scripts\python.exe" main.py
echo.
echo Le bot s'est arrete. Lis le message ci-dessus pour savoir pourquoi.
pause
exit /b

:nopython
echo [!] Python est introuvable. Installe Python 3.11 ou plus recent depuis python.org
echo     en cochant "Add python.exe to PATH", puis relance start.bat.
pause
exit /b

:error
echo.
echo [!] Une erreur est survenue pendant l'installation (voir le message ci-dessus).
pause
