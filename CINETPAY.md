# Paiement en ligne automatique (CinetPay) — EN RÉSERVE

⚠️ **CinetPay a refusé la création du compte marchand en raison d'une panne
de service actuellement en cours au Sénégal** (message reçu de CinetPay :
service opérationnel en Côte d'Ivoire, au Burkina Faso, au Togo, au Cameroun
et en RDC, mais pas encore au Sénégal). Le circuit automatique réellement
actif sur le site aujourd'hui est **PayDunya** — voir PAYDUNYA.md.

Ce document est conservé tel quel : le code CinetPay décrit ci-dessous existe
toujours dans l'application et peut être activé à tout moment, sans aucune
modification de code, simplement en suivant les étapes plus bas — utile le
jour où CinetPay rétablira son service au Sénégal (ou pour une expansion vers
un des pays où CinetPay fonctionne déjà). Tant que ses variables
d'environnement ne sont pas définies, ce circuit reste inactif et n'interfère
pas avec PayDunya.

Ce document explique comment activer le paiement automatique des formations
sur agroecoconsulting.com, en plus du circuit manuel existant (paiement
déclaré par l'étudiant puis vérifié à la main par un administrateur).

## Ce qui change pour l'étudiant

Sur la page d'une formation, un nouveau bouton **« Payer maintenant »**
apparaît en plus du formulaire manuel existant (qui reste disponible, replié
sous « J'ai déjà payé autrement »). En cliquant dessus, l'étudiant est
redirigé vers une page de paiement sécurisée hébergée par CinetPay, où il
peut payer par Wave, Orange Money, Free Money ou carte bancaire. Une fois le
paiement effectué, son accès à la formation est débloqué **automatiquement**,
en général en quelques secondes — sans qu'un administrateur ait besoin
d'intervenir.

Le circuit manuel reste utile pour le virement bancaire (que CinetPay ne
couvre pas) ou en secours si un étudiant préfère cette méthode.

## Ce qui a changé côté technique (déjà fait dans le code)

- `models.py` : la table `enrollments` a deux nouvelles colonnes,
  `payment_source` (`manuel` ou `cinetpay`) et `cinetpay_transaction_id`.
  Elles sont ajoutées automatiquement à la base existante au prochain
  démarrage du site (mécanisme déjà en place dans `app.py`, aucune
  intervention manuelle sur la base n'est nécessaire).
- `app.py` : trois nouvelles routes —
  - `POST /formations/<id>/payer-cinetpay` : initie le paiement et redirige
    vers la page CinetPay.
  - `GET/POST /paiement/cinetpay/notify` : **webhook** appelé par CinetPay
    pour confirmer le paiement côté serveur. C'est cette route qui débloque
    automatiquement l'accès, sans validation humaine.
  - `GET /paiement/cinetpay/retour/<id>` : page affichée à l'étudiant juste
    après son passage sur CinetPay (retour immédiat, en secours du webhook).
- Tant que les variables d'environnement ci-dessous ne sont pas définies, le
  bouton « Payer maintenant » reste masqué et le site fonctionne exactement
  comme avant (aucun risque de casser quoi que ce soit en attendant).

## Ce qu'il reste à faire (côté cabinet)

1. **Créer un compte marchand CinetPay** sur https://cinetpay.com (gratuit à
   l'inscription). Prévoir les informations habituelles pour un compte
   marchand (identité, coordonnées, et selon les cas un justificatif pour
   activer les retraits — CinetPay précisera lors de l'inscription).

2. **Récupérer la clé API et le Site ID** depuis le tableau de bord CinetPay
   (section *Intégrations*).

3. **Définir deux variables d'environnement** sur l'hébergement Namecheap
   (là où `SECRET_KEY` et `ADMIN_PASSWORD` sont déjà configurés) :

   ```
   CINETPAY_API_KEY=la_cle_recuperee_dans_le_dashboard
   CINETPAY_SITE_ID=le_site_id_recupere_dans_le_dashboard
   ```

4. **Redémarrer l'application** après avoir défini ces variables — le bouton
   « Payer maintenant » apparaît alors automatiquement sur les pages de
   formation, sans autre changement de code.

5. **Tester avec un petit montant réel** (le compte CinetPay n'a pas
   systématiquement de mode « bac à sable » public) : s'inscrire à une
   formation avec un compte étudiant de test, payer via Wave ou Orange
   Money, et vérifier dans `/admin/inscriptions` que le statut passe à
   « Validée automatiquement » sans action de votre part.

## Sécurité

- Le webhook `/paiement/cinetpay/notify` ne fait jamais confiance directement
  au contenu reçu : il rappelle systématiquement l'API CinetPay
  (`/v2/payment/check`) pour vérifier le statut réel de la transaction avant
  de débloquer un accès — c'est la pratique recommandée par CinetPay pour
  éviter une notification falsifiée.
- La clé API et le Site ID ne sont jamais écrits en dur dans le code : ils ne
  vivent que dans les variables d'environnement du serveur.
