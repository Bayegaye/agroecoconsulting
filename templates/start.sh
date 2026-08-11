#!/bin/bash
cd "$(dirname "$0")"

if [ ! -f requirements.txt ]; then
  echo "ERREUR : requirements.txt introuvable. Extrayez tout le contenu du zip avant de lancer ce script."
  exit 1
fi

if ! command -v python3 &> /dev/null; then
  echo "Python 3 n'est pas installe. Installez-le puis reessayez."
  exit 1
fi

if [ ! -d venv ]; then
  echo "Creation de l'environnement virtuel..."
  python3 -m venv venv
fi

source venv/bin/activate

echo "Installation des dependances..."
pip install -r requirements.txt

if [ ! -f instance/agroeco_formation.db ]; then
  echo "Initialisation de la base de donnees..."
  python init_db.py
fi

( sleep 4 && (open http://127.0.0.1:5001 2>/dev/null || xdg-open http://127.0.0.1:5001 2>/dev/null) ) &

echo ""
echo "============================================"
echo "  AgroEcoConsult Formation demarre sur :"
echo "  http://127.0.0.1:5001"
echo "  Compte admin : admin@agroecoconsult.sn / agroeco2026"
echo "============================================"
echo ""

python app.py
