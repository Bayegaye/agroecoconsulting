@echo off
setlocal
cd /d "%~dp0"

if not exist requirements.txt (
  echo.
  echo ERREUR : requirements.txt introuvable.
  echo Vous lancez probablement ce script depuis l'interieur d'une archive ZIP.
  echo Extrayez d'abord TOUT le contenu du zip dans un dossier, puis relancez start.bat depuis ce dossier extrait.
  echo.
  pause
  exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
  echo Python n'est pas installe ou pas dans le PATH. Installez Python 3.10+ depuis python.org puis reessayez.
  pause
  exit /b 1
)

if not exist venv (
  echo Creation de l'environnement virtuel...
  python -m venv venv
)

call venv\Scripts\activate.bat

echo Installation des dependances...
pip install -r requirements.txt

if not exist instance\agroeco_formation.db (
  echo Initialisation de la base de donnees...
  python init_db.py
)

start "" cmd /c "timeout /t 4 >nul & start http://127.0.0.1:5001"

echo.
echo ============================================
echo   AgroEcoConsult Formation demarre sur :
echo   http://127.0.0.1:5001
echo   Compte admin : admin@agroecoconsult.sn / agroeco2026
echo ============================================
echo.

python app.py

pause
