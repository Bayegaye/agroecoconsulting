# Déployer AgroEcoConsult Formation en ligne (Render)

Ce guide suit exactement la même méthode que celle utilisée pour SENAVIPRO :
dépôt GitHub + service web Docker sur Render.

## Étape préalable — mettre le code sur GitHub

1. Créez un nouveau dépôt sur https://github.com (ex: `agroeco-formation`),
   vide, sans README.
2. Sur la page du dépôt vide, utilisez **uploading an existing file** pour
   déposer tous les fichiers et dossiers de ce projet (en conservant la
   structure des dossiers `templates/` et `static/`).
   - Si l'upload web ne conserve pas les sous-dossiers, utilisez la méthode
     qui a fonctionné pour SENAVIPRO : uploadez d'abord tous les fichiers,
     puis ouvrez chaque fichier mal placé avec le crayon ✏️ et renommez-le en
     `templates/nom_du_fichier.html` (ou `static/img/...`) dans le champ du
     nom de fichier, puis Commit changes.
3. Vérifiez que `templates/` contient bien tous les fichiers `.html`.

## Créer les services sur Render

1. Allez sur https://dashboard.render.com
2. **New +** → **Blueprint** → connectez votre dépôt GitHub
   `agroeco-formation`. Render détecte `render.yaml` et propose de créer :
   - un service web `agroeco-formation` (Docker)
   - une base de données Postgres `agroeco-formation-db`
3. Render vous demandera de renseigner `ADMIN_PASSWORD` (mot de passe du
   compte administrateur) — choisissez un mot de passe fort.
4. Cliquez **Apply** / **Create**. Le premier déploiement prend quelques
   minutes.

## Variables d'environnement

| Variable | Rôle |
|---|---|
| `SECRET_KEY` | Générée automatiquement par Render (`generateValue: true`) |
| `DATABASE_URL` | Fournie automatiquement par la base Postgres liée |
| `ADMIN_PASSWORD` | Mot de passe du compte admin (email : `admin@agroecoconsult.sn`) |
| `RESET_ADMIN_PASSWORD` | Mettez `1` puis redéployez pour réinitialiser le mot de passe admin si vous l'avez oublié, puis repassez-la à `0` |

## Après le déploiement

1. Ouvrez l'URL fournie par Render (ex: `https://agroeco-formation.onrender.com`)
2. Connectez-vous avec `admin@agroecoconsult.sn` et le mot de passe choisi
3. Menu **Gérer les formations** → créez votre première formation, ajoutez
   des leçons (liens vidéo/document)
4. Testez le parcours étudiant : créez un compte étudiant test, inscrivez-le
   à une formation, puis validez le paiement depuis **Paiements /
   Inscriptions** pour vérifier que l'accès au contenu se débloque bien.

## Mettre à jour le site après une modification

Même méthode que pour SENAVIPRO : ouvrez le fichier modifié sur GitHub,
crayon ✏️, remplacez le contenu, **Commit changes**. Render redéploie
automatiquement. Si besoin, forcez un déploiement propre depuis Render :
**Manual Deploy → Deploy latest commit**.
