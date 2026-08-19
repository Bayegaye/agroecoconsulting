# Déployer Agro Eco Consulting sur Namecheap (Stellar Plus)

Ce guide explique comment mettre le site en ligne sur l'hébergement partagé Namecheap (plan **Stellar Plus**, qui inclut PostgreSQL), et connecter le nom de domaine `agroecoconsult.com` déjà acheté.

Contrairement à Render, l'hébergement Namecheap avec une base **PostgreSQL** correctement configurée est **persistant** : les formations, inscriptions et comptes ne disparaissent pas après un redéploiement ou une reconnexion.

---

## 1. Activer l'hébergement Stellar Plus

1. Connectez-vous à votre compte Namecheap.
2. Achetez/activez le plan **Stellar Plus** (~2,98 $/mois) si ce n'est pas déjà fait.
3. Une fois actif, ouvrez **cPanel** depuis votre tableau de bord Namecheap (bouton "Go to cPanel" ou "Manage").

## 2. Créer la base de données PostgreSQL

1. Dans cPanel, cherchez la section **Databases** → **PostgreSQL Databases**.
2. Créez une nouvelle base, par exemple `agroeco_formation`.
3. Créez un utilisateur PostgreSQL dédié (ex. `agroeco_admin`) avec un mot de passe fort — notez-le précieusement.
4. Associez cet utilisateur à la base avec **tous les privilèges** (ALL PRIVILEGES).
5. Notez le **nom d'hôte** de connexion PostgreSQL (souvent `localhost` sur le même serveur, mais cPanel l'indique précisément — parfois un port différent de 5432 est utilisé sur du mutualisé, vérifiez l'écran de gestion PostgreSQL).

Le nom de la base et de l'utilisateur seront probablement préfixés automatiquement par votre nom de compte cPanel (ex. `cpaneluser_agroeco_formation`) — copiez le nom exact affiché par cPanel.

## 3. Créer l'application Python

1. Dans cPanel, ouvrez **Setup Python App** (section Software).
2. Cliquez sur **Create Application**.
3. Renseignez :
   - **Python version** : 3.12 (ou la version la plus proche disponible)
   - **Application root** : par exemple `agroeco_formation` (dossier qui contiendra le code)
   - **Application URL** : le domaine ou sous-domaine où le site sera accessible (ex. `agroecoconsult.com`)
   - **Application startup file** : `passenger_wsgi.py`
   - **Application Entry point** : `application`
4. Cliquez sur **Create**. cPanel crée un environnement virtuel Python dédié et vous donne une commande d'activation (à utiliser si vous passez par SSH).

## 4. Envoyer les fichiers du projet

Deux façons de faire :

**Option A — Gestionnaire de fichiers cPanel (simple, sans terminal)**
1. Ouvrez **File Manager** dans cPanel.
2. Allez dans le dossier "Application root" créé à l'étape précédente.
3. Uploadez tous les fichiers du projet (vous pouvez zipper le dossier localement, l'uploader, puis "Extract" dans cPanel).

**Option B — SSH + Git (si l'accès SSH est activé sur votre plan)**
```bash
cd ~/agroeco_formation
git clone https://github.com/Bayegaye/agroeco-formation-2026.git .
```

Fichiers à inclure : tout le contenu du dépôt, y compris `passenger_wsgi.py` (nouvellement ajouté), `templates/`, `static/`, `requirements.txt`, `requirements-postgres.txt`, `models.py`, `app.py`, `seed.py`.

## 5. Installer les dépendances Python

Dans **Setup Python App**, sur la ligne de votre application, cliquez sur le lien pour ouvrir un terminal dans l'environnement virtuel (ou connectez-vous en SSH puis activez l'environnement avec la commande fournie par cPanel), puis :

```bash
pip install -r requirements.txt
pip install -r requirements-postgres.txt
```

Alternativement, dans l'interface **Setup Python App**, la section "Configuration files" permet d'ajouter chaque module et de cliquer sur **Run Pip Install** sans terminal.

## 6. Configurer les variables d'environnement

Toujours dans **Setup Python App**, section **Environment variables**, ajoutez :

| Variable | Valeur |
|---|---|
| `SECRET_KEY` | Une chaîne aléatoire longue et secrète (générez-en une, ex. via `python -c "import secrets; print(secrets.token_hex(32))"`) |
| `DATABASE_URL` | `postgresql://UTILISATEUR:MOTDEPASSE@HOTE:PORT/NOMBASE` (remplacez avec les infos de l'étape 2) |
| `ADMIN_PASSWORD` | Le mot de passe que vous voulez pour le compte admin par défaut (`admin@agroecoconsult.sn`) |

Le code convertit déjà automatiquement `postgresql://` vers le driver `psycopg` — vous n'avez rien à adapter dans `app.py`.

## 7. Démarrer et tester l'application

1. Retournez dans **Setup Python App** et cliquez sur **Restart** pour votre application.
2. Consultez le fichier `stderr.log` (visible dans le dossier de l'application) en cas d'erreur.
3. Visitez l'URL configurée à l'étape 3 pour vérifier que le site répond.
4. Connectez-vous avec le compte admin (`admin@agroecoconsult.sn` / le mot de passe défini dans `ADMIN_PASSWORD`) et vérifiez que tout fonctionne : créer une formation, une leçon, un quiz.
5. **Test de persistance** : redémarrez l'application depuis cPanel, puis revérifiez que la formation créée est toujours là — c'est la preuve que PostgreSQL est bien utilisé et non plus SQLite.

## 8. Connecter le domaine agroecoconsult.com

Si le domaine est déjà chez Namecheap et que l'hébergement Stellar Plus est aussi chez Namecheap, la connexion est automatique une fois le domaine pointé sur cet hébergement (Namecheap propose en général de le faire directement lors de l'achat de l'hébergement, ou via **Domain List → Manage → Nameservers**, en s'assurant qu'ils pointent vers les serveurs de noms Namecheap par défaut).

Si le domaine doit servir uniquement ce site (pas de sous-dossier), configurez-le comme **domaine principal** de l'hébergement dans cPanel (**Domains**), plutôt que comme addon domain, pour que `agroecoconsult.com` pointe directement vers l'application Python.

## 9. Fichiers statiques (images, éventuels PDF/vidéos hébergés localement)

Le dossier `static/` est servi automatiquement par Flask. Si vous stockez de gros fichiers vidéo directement sur l'hébergement (plutôt que via des liens YouTube/Drive comme conçu à l'origine), gardez à l'esprit que l'espace disque du plan Stellar Plus est limité — mieux vaut garder le système de liens externes déjà en place dans l'app pour les vidéos et PDF volumineux.

---

## Résumé des changements apportés au code pour cette migration

- **`passenger_wsgi.py`** (nouveau) : point d'entrée requis par Passenger/cPanel, expose `application` au lieu de `app`.
- Aucun changement dans `app.py`, `models.py` ou les templates — le code était déjà compatible PostgreSQL via `DATABASE_URL`.
