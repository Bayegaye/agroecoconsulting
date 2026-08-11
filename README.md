# AgroEcoConsult Formation

Plateforme de formation en ligne payante pour le **Cabinet AgroEcoConsult**.

Pour l'hébergement en ligne (Render), voir **DEPLOIEMENT.md**.

## Démarrage rapide (usage local)

- **Windows** : double-cliquez sur `start.bat`
- **Mac / Linux** : ouvrez un terminal dans ce dossier puis lancez `./start.sh`

Le site s'ouvre automatiquement sur http://127.0.0.1:5001

### Compte administrateur par défaut

- Email : `admin@agroecoconsult.sn`
- Mot de passe : `agroeco2026`

**Changez ce mot de passe dès la première connexion** (ou définissez la variable
d'environnement `ADMIN_PASSWORD` avant le premier lancement).

## Fonctionnalités

- Catalogue public des formations (titre, description, prix, image)
- Création de compte étudiant (inscription libre)
- Inscription à une formation avec déclaration de paiement (Wave, Orange
  Money, Free Money, virement) — l'étudiant indique la référence de sa
  transaction
- Validation manuelle des paiements par l'administrateur : c'est cette
  validation qui débloque l'accès au contenu de la formation pour
  l'étudiant
- Gestion des formations et des leçons (vidéo en lien, document en lien,
  texte) depuis l'espace admin
- Suivi des étudiants inscrits

### Pourquoi une confirmation manuelle du paiement ?

Cette première version ne nécessite aucun compte marchand ni clé API
(PayDunya, CinetPay...) : l'étudiant paie directement via son application
Wave / Orange Money / Free Money habituelle, indique la référence sur le
site, et vous validez depuis l'espace admin. Le site est donc déployable
immédiatement. Une passerelle de paiement automatique pourra être ajoutée
plus tard si besoin.

### Pourquoi les vidéos et documents sont des liens et non des fichiers uploadés ?

Sur un hébergeur comme Render (offre gratuite), les fichiers stockés sur le
serveur sont effacés à chaque redéploiement. Pour éviter de perdre vos
vidéos/documents, la plateforme utilise des **liens** (YouTube en non
répertorié, Vimeo, Google Drive, Dropbox...) plutôt que l'upload direct de
fichiers. C'est aussi ce qui permet de rester sur l'offre gratuite de
Render.

## Structure du projet

```
agroeco_formation/
├── app.py                  # Application Flask (routes)
├── models.py                # Modèles de données (SQLAlchemy)
├── seed.py                  # Création du compte admin par défaut
├── init_db.py                # Initialise la base de données
├── wsgi.py / Procfile        # Point d'entrée production (gunicorn)
├── requirements.txt          # Dépendances (installation locale)
├── requirements-postgres.txt # Pilote Postgres (production uniquement)
├── Dockerfile / render.yaml  # Déploiement Render (voir DEPLOIEMENT.md)
├── docker-compose.yml        # Option VPS avec Docker
├── templates/                 # Pages HTML
└── static/                    # Fichiers statiques
```
