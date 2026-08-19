# Paiement en ligne automatique (PayDunya)

Ce document explique comment activer le paiement automatique des formations
sur agroecoconsulting.com via **PayDunya**, en plus du circuit manuel
existant (paiement déclaré par l'étudiant puis vérifié à la main par un
administrateur).

PayDunya a été choisi à la place de CinetPay parce que CinetPay traverse
actuellement une panne de service spécifique au Sénégal (voir CINETPAY.md,
conservé au cas où ce service serait rétabli plus tard). PayDunya, lui, est
pleinement opérationnel au Sénégal, ainsi qu'au Bénin, au Burkina Faso, en
Côte d'Ivoire, au Mali et au Togo.

## Ce qui change pour l'étudiant

Sur la page d'une formation, un nouveau bouton **« Payer maintenant »**
apparaît en plus du formulaire manuel existant (qui reste disponible, replié
sous « J'ai déjà payé autrement »). En cliquant dessus, l'étudiant est
redirigé vers une page de paiement sécurisée hébergée par PayDunya, où il
peut payer par Wave, Orange Money, Free Money ou carte bancaire. Une fois le
paiement effectué, son accès à la formation est débloqué **automatiquement**,
en général en quelques secondes — sans qu'un administrateur ait besoin
d'intervenir.

Le circuit manuel reste utile pour le virement bancaire (que PayDunya ne
couvre pas) ou en secours si un étudiant préfère cette méthode.

## Ce qui a changé côté technique (déjà fait dans le code)

- `models.py` : la table `enrollments` a une nouvelle colonne
  `paydunya_token` (en plus de `payment_source` et `cinetpay_transaction_id`
  déjà ajoutées pour CinetPay). Elle est ajoutée automatiquement à la base
  existante au prochain démarrage du site, aucune intervention manuelle sur
  la base n'est nécessaire.
- `app.py` : trois nouvelles routes —
  - `POST /formations/<id>/payer-paydunya` : crée une facture PayDunya et
    redirige vers la page de paiement.
  - `GET/POST /paiement/paydunya/notify` : **callback IPN** appelé par
    PayDunya pour confirmer le paiement côté serveur. C'est cette route qui
    débloque automatiquement l'accès, sans validation humaine.
  - `GET /paiement/paydunya/retour/<id>` : page affichée à l'étudiant juste
    après son passage sur PayDunya (retour immédiat, en secours du callback).
- Tant que les variables d'environnement ci-dessous ne sont pas définies, le
  bouton « Payer maintenant » reste masqué et le site fonctionne exactement
  comme avant (aucun risque de casser quoi que ce soit en attendant).

## Ce qu'il reste à faire (côté cabinet)

1. **Créer un compte marchand PayDunya** sur https://paydunya.com (gratuit à
   l'inscription). Prévoir les informations habituelles pour un compte
   marchand (identité, coordonnées de l'entreprise).

2. **Récupérer les 3 clés API** depuis le tableau de bord PayDunya, section
   *Compte > API* : la clé maître (*Master Key*), la clé privée (*Private
   Key*) et le *Token*.

3. **Définir les variables d'environnement** sur Render (le site est hébergé
   sur Render, pas sur Namecheap qui ne gère que le nom de domaine) : dans
   [dashboard.render.com](https://dashboard.render.com), ouvrez le service
   `agroeco-formation`, onglet **Environment** — là où `SECRET_KEY` et
   `ADMIN_PASSWORD` sont déjà configurés :

   ```
   PAYDUNYA_MASTER_KEY=la_cle_maitre_recuperee_dans_le_dashboard
   PAYDUNYA_PRIVATE_KEY=la_cle_privee_recuperee_dans_le_dashboard
   PAYDUNYA_TOKEN=le_token_recupere_dans_le_dashboard
   PAYDUNYA_MODE=test
   ```

   Laissez `PAYDUNYA_MODE=test` dans un premier temps : aucun vrai paiement
   n'est débité, ce qui permet de tester tranquillement tout le circuit.

4. **Redémarrer l'application** après avoir défini ces variables — le bouton
   « Payer maintenant » apparaît alors automatiquement sur les pages de
   formation.

5. **Tester en mode test** : inscrivez-vous à une formation avec un compte
   étudiant de test et suivez le parcours de paiement PayDunya (il propose
   généralement un mode simulateur en environnement de test). Vérifiez dans
   `/admin/inscriptions` que le statut passe à « Validée automatiquement »
   sans action de votre part.

6. **Passer en mode réel** : une fois le test concluant, changez
   `PAYDUNYA_MODE=live` et redémarrez à nouveau l'application. Faites un
   dernier test avec un petit montant réel avant de communiquer largement le
   nouveau bouton de paiement.

## Sécurité

- Le callback `/paiement/paydunya/notify` ne fait jamais confiance
  directement au contenu reçu : il rappelle systématiquement l'API PayDunya
  (`/checkout-invoice/confirm/<token>`) pour vérifier le statut réel de la
  transaction avant de débloquer un accès — même logique de précaution que
  pour l'intégration CinetPay déjà documentée dans CINETPAY.md.
- Les clés API ne sont jamais écrites en dur dans le code : elles ne vivent
  que dans les variables d'environnement du serveur.
