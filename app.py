import os
import secrets
from datetime import datetime
from functools import wraps

import requests
from flask import (
    Flask, render_template, redirect, url_for, request, flash, abort, Response
)
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user
)
from sqlalchemy import inspect, text

from models import db, User, Course, Lesson, Enrollment, Quiz, Question, Choice, QuizAttempt

DOCUMENT_MAX_SIZE_MO = 20

APP_NAME = os.environ.get("APP_NAME", "Agro Eco Consulting")
CABINET_NAME = "Cabinet AgroEcoConsult"

PAYMENT_METHODS = [
    ("wave", "Wave"),
    ("orange_money", "Orange Money"),
    ("free_money", "Free Money"),
    ("virement", "Virement bancaire"),
    ("autre", "Autre"),
]

# ---------- Paiement automatique CinetPay ----------
# CinetPay permet d'encaisser Wave, Orange Money, Free Money et carte
# bancaire via une page de paiement hébergée, avec confirmation automatique
# côté serveur par webhook (voir /paiement/cinetpay/notify plus bas) — sans
# validation manuelle par un administrateur. Le circuit manuel historique
# (formulaire "j'ai déjà payé, voici ma référence") reste disponible en
# secours, notamment pour le virement bancaire que CinetPay ne couvre pas.
#
# Pour activer ce circuit : créer un compte marchand sur https://cinetpay.com,
# récupérer la clé API et le SITE ID dans le tableau de bord ("Intégrations"),
# puis définir les variables d'environnement CINETPAY_API_KEY et
# CINETPAY_SITE_ID (voir .env.example). Tant qu'elles ne sont pas définies,
# le bouton de paiement automatique reste masqué et seul le circuit manuel
# est proposé — le site fonctionne donc normalement avant toute config.
CINETPAY_API_KEY = os.environ.get("CINETPAY_API_KEY", "")
CINETPAY_SITE_ID = os.environ.get("CINETPAY_SITE_ID", "")
CINETPAY_API_BASE = "https://api-checkout.cinetpay.com/v2"
CINETPAY_ENABLED = bool(CINETPAY_API_KEY and CINETPAY_SITE_ID)

# ---------- Paiement automatique PayDunya ----------
# Même principe que CinetPay ci-dessus (confirmation automatique par webhook,
# sans validation manuelle), via PayDunya — opérationnel au Sénégal, Bénin,
# Burkina Faso, Côte d'Ivoire, Mali et Togo. C'est le circuit automatique
# actif par défaut sur ce site (CinetPay est conservé en réserve, voir plus
# haut, en attendant le rétablissement de son service au Sénégal).
#
# Pour activer : créer un compte marchand sur https://paydunya.com, récupérer
# les 3 clés (master key, private key, token) dans le tableau de bord
# ("Compte > API"), puis définir PAYDUNYA_MASTER_KEY, PAYDUNYA_PRIVATE_KEY et
# PAYDUNYA_TOKEN (voir .env.example et PAYDUNYA.md). Tant qu'elles ne sont pas
# définies, le bouton de paiement automatique reste masqué.
#
# PAYDUNYA_MODE contrôle l'environnement : "test" (par défaut, aucun vrai
# paiement) ou "live" (paiements réels). Il faut le mettre explicitement à
# "live" pour encaisser de l'argent réel — ce choix volontaire évite
# d'accepter des paiements réels par erreur avant d'avoir testé le circuit.
PAYDUNYA_MASTER_KEY = os.environ.get("PAYDUNYA_MASTER_KEY", "")
PAYDUNYA_PRIVATE_KEY = os.environ.get("PAYDUNYA_PRIVATE_KEY", "")
PAYDUNYA_TOKEN = os.environ.get("PAYDUNYA_TOKEN", "")
PAYDUNYA_MODE = os.environ.get("PAYDUNYA_MODE", "test").strip().lower()
PAYDUNYA_API_BASE = (
    "https://app.paydunya.com/api/v1" if PAYDUNYA_MODE == "live"
    else "https://app.paydunya.com/sandbox-api/v1"
)
PAYDUNYA_ENABLED = bool(PAYDUNYA_MASTER_KEY and PAYDUNYA_PRIVATE_KEY and PAYDUNYA_TOKEN)


def _paydunya_headers():
    return {
        "Content-Type": "application/json",
        "PAYDUNYA-MASTER-KEY": PAYDUNYA_MASTER_KEY,
        "PAYDUNYA-PRIVATE-KEY": PAYDUNYA_PRIVATE_KEY,
        "PAYDUNYA-TOKEN": PAYDUNYA_TOKEN,
    }


def _database_uri():
    """Lit DATABASE_URL (fourni par la plupart des hébergeurs pour Postgres).
    À défaut, utilise un fichier SQLite local. Convertit 'postgres://' /
    'postgresql://' vers 'postgresql+psycopg://' pour utiliser psycopg (v3,
    voir requirements-postgres.txt)."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        return "sqlite:///agroeco_formation.db"
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


IS_PRODUCTION = os.environ.get("DATABASE_URL") is not None

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "agroeco-formation-secret-key-change-en-production")
app.config["SQLALCHEMY_DATABASE_URI"] = _database_uri()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_COOKIE_SECURE"] = IS_PRODUCTION
app.config["MAX_CONTENT_LENGTH"] = DOCUMENT_MAX_SIZE_MO * 1024 * 1024

if IS_PRODUCTION and app.config["SECRET_KEY"] == "agroeco-formation-secret-key-change-en-production":
    raise RuntimeError(
        "SECRET_KEY par défaut détectée en production ! "
        "Définissez la variable d'environnement SECRET_KEY avant de déployer "
        "(voir DEPLOIEMENT.md)."
    )

db.init_app(app)


def _ensure_column(inspector, table, column, ddl_type="TEXT"):
    """Ajoute une colonne à une table existante si elle manque encore —
    db.create_all() ne crée que les tables absentes, il ne modifie jamais une
    table déjà présente en base. Sans effet (et sûr à ré-exécuter) si la
    colonne existe déjà."""
    if table not in inspector.get_table_names():
        return
    colonnes = {c["name"] for c in inspector.get_columns(table)}
    if column not in colonnes:
        with db.engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))


def _ensure_schema_upgrades():
    """Applique en base les petites évolutions de schéma qui ne sont pas gérées par
    db.create_all() (compatible SQLite en local et PostgreSQL en production) :
    ajoute les colonnes permettant de stocker un PDF uploadé directement sur
    une leçon (en plus du lien externe déjà existant), ainsi que les colonnes
    liées aux paiements automatiques (CinetPay, PayDunya) sur les
    inscriptions."""
    inspector = inspect(db.engine)
    _ensure_column(inspector, "lessons", "document_data", "BYTEA" if IS_PRODUCTION else "BLOB")
    _ensure_column(inspector, "lessons", "document_filename", "VARCHAR(255)")
    _ensure_column(inspector, "lessons", "document_mimetype", "VARCHAR(100)")
    _ensure_column(inspector, "enrollments", "payment_source", "VARCHAR(10) DEFAULT 'manuel'")
    _ensure_column(inspector, "enrollments", "cinetpay_transaction_id", "VARCHAR(64)")
    _ensure_column(inspector, "enrollments", "paydunya_token", "VARCHAR(80)")


with app.app_context():
    db.create_all()
    _ensure_schema_upgrades()
    from seed import ensure_seed_data
    ensure_seed_data(verbose=False)


@app.errorhandler(413)
def _fichier_trop_volumineux(e):
    flash(f"Le fichier est trop volumineux (maximum {DOCUMENT_MAX_SIZE_MO} Mo).", "danger")
    return redirect(request.referrer or url_for("admin_formations")), 302

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message = "Veuillez vous connecter pour accéder à cette page."
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("Accès réservé à l'administrateur.", "danger")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return wrapper


@app.context_processor
def inject_globals():
    return {"app_name": APP_NAME, "cabinet_name": CABINET_NAME, "now": datetime.utcnow()}


# ---------- Pages publiques ----------

@app.route("/")
def accueil():
    """Page d'accueil vitrine du cabinet Agro Eco Consulting."""
    formations = Course.query.filter_by(published=True).order_by(Course.created_at.desc()).limit(3).all()
    return render_template("accueil.html", formations_apercu=formations)


@app.route("/formations")
def index():
    formations = Course.query.filter_by(published=True).order_by(Course.created_at.asc()).all()
    mes_statuts = {}
    if current_user.is_authenticated and not current_user.is_admin:
        for e in Enrollment.query.filter_by(student_id=current_user.id).all():
            mes_statuts[e.course_id] = e.status
    return render_template("index.html", formations=formations, mes_statuts=mes_statuts)


@app.route("/formations/<int:cid>")
def formation_detail(cid):
    formation = db.session.get(Course, cid)
    if not formation or (not formation.published and not (current_user.is_authenticated and current_user.is_admin)):
        abort(404)
    lecons = formation.lessons.order_by(Lesson.position).all()
    mon_inscription = None
    if current_user.is_authenticated and not current_user.is_admin:
        mon_inscription = Enrollment.query.filter_by(
            student_id=current_user.id, course_id=cid
        ).order_by(Enrollment.created_at.desc()).first()
    return render_template(
        "formation_detail.html", formation=formation, lecons=lecons,
        mon_inscription=mon_inscription, payment_methods=PAYMENT_METHODS,
        cinetpay_enabled=CINETPAY_ENABLED, paydunya_enabled=PAYDUNYA_ENABLED,
    )


# ---------- Authentification ----------

@app.route("/inscription", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")

        if not full_name or not email or not password:
            flash("Nom, email et mot de passe sont obligatoires.", "danger")
        elif password != password2:
            flash("Les mots de passe ne correspondent pas.", "danger")
        elif len(password) < 6:
            flash("Le mot de passe doit contenir au moins 6 caractères.", "danger")
        elif User.query.filter_by(email=email).first():
            flash("Un compte existe déjà avec cet email.", "danger")
        else:
            u = User(full_name=full_name, email=email, phone=phone, role="etudiant", active=True)
            u.set_password(password)
            db.session.add(u)
            db.session.commit()
            login_user(u)
            flash(f"Bienvenue, {u.full_name} ! Votre compte a été créé.", "success")
            return redirect(url_for("index"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and user.active and user.check_password(password):
            login_user(user)
            flash(f"Bienvenue, {user.full_name}.", "success")
            return redirect(url_for("admin_formations") if user.is_admin else url_for("index"))
        flash("Email ou mot de passe incorrect.", "danger")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Vous êtes déconnecté(e).", "info")
    return redirect(url_for("index"))


# ---------- Inscription à une formation (paiement) ----------

@app.route("/formations/<int:cid>/inscription", methods=["POST"])
@login_required
def inscrire(cid):
    if current_user.is_admin:
        flash("Un compte administrateur ne peut pas s'inscrire à une formation.", "danger")
        return redirect(url_for("formation_detail", cid=cid))

    formation = db.session.get(Course, cid)
    if not formation or not formation.published:
        abort(404)

    existante = Enrollment.query.filter(
        Enrollment.student_id == current_user.id,
        Enrollment.course_id == cid,
        Enrollment.status.in_(["en_attente", "validee"]),
    ).first()
    if existante:
        flash("Vous avez déjà une inscription en cours ou validée pour cette formation.", "info")
        return redirect(url_for("formation_detail", cid=cid))

    payment_method = request.form.get("payment_method", "")
    payment_reference = request.form.get("payment_reference", "").strip()
    payment_phone = request.form.get("payment_phone", "").strip()

    if payment_method not in dict(PAYMENT_METHODS):
        flash("Mode de paiement invalide.", "danger")
        return redirect(url_for("formation_detail", cid=cid))
    if not payment_reference:
        flash("Merci d'indiquer la référence de votre paiement.", "danger")
        return redirect(url_for("formation_detail", cid=cid))

    e = Enrollment(
        student_id=current_user.id,
        course_id=formation.id,
        amount=formation.price,
        payment_method=payment_method,
        payment_reference=payment_reference,
        payment_phone=payment_phone,
        payment_source="manuel",
        status="en_attente",
    )
    db.session.add(e)
    db.session.commit()
    flash(
        "Votre inscription a été enregistrée. L'accès à la formation sera débloqué "
        "dès que votre paiement aura été vérifié par notre équipe.",
        "success",
    )
    return redirect(url_for("mes_formations"))


# ---------- Paiement automatique (CinetPay) ----------
#
# Circuit qui remplace la vérification manuelle par une confirmation
# automatique côté serveur : /formations/<cid>/payer-cinetpay initie le
# paiement et redirige l'étudiant vers la page CinetPay hébergée ; CinetPay
# rappelle ensuite /paiement/cinetpay/notify (webhook) pour confirmer, ce qui
# valide l'inscription sans action d'un administrateur. /paiement/cinetpay/
# retour affiche un retour immédiat à l'étudiant après son passage sur la
# page de paiement (au cas où le webhook mettrait quelques secondes à
# arriver).

def _cinetpay_check_transaction(transaction_id):
    """Interroge l'API CinetPay pour connaître le statut réel d'une
    transaction. Ne jamais se fier au seul appel webhook entrant (CinetPay
    recommande explicitement de revérifier via cet endpoint pour éviter toute
    notification falsifiée). Retourne 'ACCEPTED', 'REFUSED', ou None si le
    statut n'est pas encore déterminé ou en cas d'erreur réseau."""
    try:
        resp = requests.post(
            f"{CINETPAY_API_BASE}/payment/check",
            json={
                "apikey": CINETPAY_API_KEY,
                "site_id": CINETPAY_SITE_ID,
                "transaction_id": transaction_id,
            },
            timeout=15,
        )
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        app.logger.error("CinetPay: échec de vérification de %s : %s", transaction_id, exc)
        return None
    if data.get("code") != "00":
        return None
    return data.get("data", {}).get("status")  # ACCEPTED | REFUSED | ...


def _cinetpay_apply_status(enrollment, cp_status):
    """Met à jour une inscription selon le statut renvoyé par CinetPay.
    Idempotent : ne fait rien si l'inscription a déjà été traitée (statut
    différent de 'en_attente'), pour supporter sans risque un webhook reçu
    plusieurs fois et un appel depuis /retour en plus de /notify."""
    if enrollment.status != "en_attente":
        return
    if cp_status == "ACCEPTED":
        enrollment.status = "validee"
        enrollment.validated_at = datetime.utcnow()
        enrollment.note_admin = "Paiement confirmé automatiquement via CinetPay."
        db.session.commit()
    elif cp_status == "REFUSED":
        enrollment.status = "rejetee"
        enrollment.note_admin = "Paiement refusé ou annulé (CinetPay)."
        db.session.commit()
    # Tout autre statut (en attente côté CinetPay, etc.) : on ne touche à
    # rien, un prochain appel (webhook suivant ou nouveau /retour) retentera.


@app.route("/formations/<int:cid>/payer-cinetpay", methods=["POST"])
@login_required
def payer_cinetpay(cid):
    if current_user.is_admin:
        flash("Un compte administrateur ne peut pas s'inscrire à une formation.", "danger")
        return redirect(url_for("formation_detail", cid=cid))
    if not CINETPAY_ENABLED:
        flash("Le paiement en ligne automatique n'est pas encore activé sur ce site.", "danger")
        return redirect(url_for("formation_detail", cid=cid))

    formation = db.session.get(Course, cid)
    if not formation or not formation.published:
        abort(404)

    existante = Enrollment.query.filter(
        Enrollment.student_id == current_user.id,
        Enrollment.course_id == cid,
        Enrollment.status.in_(["en_attente", "validee"]),
    ).first()
    if existante:
        flash("Vous avez déjà une inscription en cours ou validée pour cette formation.", "info")
        return redirect(url_for("formation_detail", cid=cid))

    # CinetPay exige un montant multiple de 5 (XOF) ; les prix du catalogue
    # le sont déjà normalement, mais on arrondit par sécurité.
    amount = int(round(formation.price / 5.0) * 5)

    e = Enrollment(
        student_id=current_user.id,
        course_id=formation.id,
        amount=formation.price,
        payment_method="cinetpay",
        payment_source="cinetpay",
        status="en_attente",
    )
    db.session.add(e)
    db.session.flush()  # attribue e.id sans clôturer la transaction

    transaction_id = f"ENR{e.id}-{secrets.token_hex(4)}"
    prenom, _, nom = current_user.full_name.partition(" ")

    try:
        resp = requests.post(
            f"{CINETPAY_API_BASE}/payment",
            json={
                "apikey": CINETPAY_API_KEY,
                "site_id": CINETPAY_SITE_ID,
                "transaction_id": transaction_id,
                "amount": amount,
                "currency": "XOF",
                "description": f"Formation : {formation.title}"[:255],
                "notify_url": url_for("cinetpay_notify", _external=True),
                "return_url": url_for("cinetpay_retour", eid=e.id, _external=True),
                "channels": "ALL",
                "customer_name": prenom or current_user.full_name,
                "customer_surname": nom,
                "customer_email": current_user.email,
                "customer_phone_number": current_user.phone or "",
            },
            timeout=20,
        )
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        db.session.rollback()
        app.logger.error("CinetPay: échec d'initialisation du paiement : %s", exc)
        flash(
            "Le paiement en ligne n'a pas pu être initié pour le moment. "
            "Vous pouvez réessayer, ou utiliser le paiement manuel ci-dessous.",
            "danger",
        )
        return redirect(url_for("formation_detail", cid=cid))

    payment_url = data.get("data", {}).get("payment_url")
    if data.get("code") != "201" or not payment_url:
        db.session.rollback()
        app.logger.error("CinetPay: réponse inattendue à l'initialisation : %s", data)
        flash(
            "Le paiement en ligne n'a pas pu être initié (" + str(data.get("message", "erreur inconnue")) + "). "
            "Vous pouvez réessayer, ou utiliser le paiement manuel ci-dessous.",
            "danger",
        )
        return redirect(url_for("formation_detail", cid=cid))

    e.cinetpay_transaction_id = transaction_id
    e.payment_reference = transaction_id
    db.session.commit()
    return redirect(payment_url)


@app.route("/paiement/cinetpay/notify", methods=["GET", "POST"])
def cinetpay_notify():
    """Webhook appelé par CinetPay pour confirmer un paiement. Doit répondre
    200 dans tous les cas pour accuser réception (CinetPay retentera sinon).
    On ne fait jamais confiance au contenu de la notification elle-même : on
    revérifie systématiquement via l'API /payment/check, comme recommandé
    par CinetPay pour éviter toute notification falsifiée."""
    transaction_id = request.values.get("cpm_trans_id") or request.values.get("transaction_id")
    if not transaction_id:
        return "", 200
    enrollment = Enrollment.query.filter_by(cinetpay_transaction_id=transaction_id).first()
    if not enrollment:
        return "", 200
    cp_status = _cinetpay_check_transaction(transaction_id)
    if cp_status:
        _cinetpay_apply_status(enrollment, cp_status)
    return "", 200


@app.route("/paiement/cinetpay/retour/<int:eid>")
@login_required
def cinetpay_retour(eid):
    """Page de retour après le passage de l'étudiant sur la page de paiement
    CinetPay (succès, échec ou abandon). Revérifie une fois le statut tout de
    suite pour un retour immédiat, au cas où le webhook mettrait quelques
    secondes à arriver — sans effet si /notify a déjà traité l'inscription."""
    enrollment = db.session.get(Enrollment, eid)
    if not enrollment or enrollment.student_id != current_user.id:
        abort(404)
    if enrollment.status == "en_attente" and enrollment.cinetpay_transaction_id:
        cp_status = _cinetpay_check_transaction(enrollment.cinetpay_transaction_id)
        if cp_status:
            _cinetpay_apply_status(enrollment, cp_status)

    if enrollment.status == "validee":
        flash("Paiement confirmé, bienvenue dans la formation !", "success")
    elif enrollment.status == "rejetee":
        flash(
            "Le paiement n'a pas abouti (refusé ou annulé). Vous pouvez réessayer.",
            "danger",
        )
    else:
        flash(
            "Paiement en cours de confirmation. L'accès à la formation sera débloqué "
            "automatiquement dès sa validation (généralement en quelques instants).",
            "info",
        )
    return redirect(url_for("mes_formations"))


# ---------- Paiement automatique (PayDunya) ----------
#
# Même principe que le circuit CinetPay ci-dessus : /formations/<cid>/payer-
# paydunya crée une facture PayDunya et redirige l'étudiant vers la page de
# paiement hébergée ; PayDunya rappelle ensuite /paiement/paydunya/notify
# (callback IPN) pour confirmer, ce qui valide l'inscription sans action d'un
# administrateur. /paiement/paydunya/retour affiche un retour immédiat à
# l'étudiant après son passage sur la page de paiement.

def _paydunya_check_status(token):
    """Interroge l'API PayDunya pour connaître le statut réel d'une facture,
    par son token. Comme pour CinetPay, on ne fait jamais confiance au seul
    contenu du callback IPN entrant (qui peut être falsifié) : on revérifie
    systématiquement ici. Retourne 'completed', 'cancelled', 'failed', ou
    None si le statut n'a pas pu être déterminé (ex. erreur réseau)."""
    try:
        resp = requests.get(
            f"{PAYDUNYA_API_BASE}/checkout-invoice/confirm/{token}",
            headers=_paydunya_headers(),
            timeout=15,
        )
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        app.logger.error("PayDunya: échec de vérification de %s : %s", token, exc)
        return None
    if data.get("response_code") != "00":
        return None
    status = data.get("status")
    return status.lower() if isinstance(status, str) else status


def _paydunya_apply_status(enrollment, pd_status):
    """Met à jour une inscription selon le statut renvoyé par PayDunya.
    Idempotent : ne fait rien si l'inscription a déjà été traitée (statut
    différent de 'en_attente'), pour supporter sans risque un callback reçu
    plusieurs fois et un appel depuis /retour en plus de /notify."""
    if enrollment.status != "en_attente":
        return
    if pd_status == "completed":
        enrollment.status = "validee"
        enrollment.validated_at = datetime.utcnow()
        enrollment.note_admin = "Paiement confirmé automatiquement via PayDunya."
        db.session.commit()
    elif pd_status in ("cancelled", "failed"):
        enrollment.status = "rejetee"
        enrollment.note_admin = "Paiement refusé ou annulé (PayDunya)."
        db.session.commit()
    # 'pending' ou statut inconnu : on ne touche à rien, un prochain appel
    # (callback suivant ou nouveau /retour) retentera.


@app.route("/formations/<int:cid>/payer-paydunya", methods=["POST"])
@login_required
def payer_paydunya(cid):
    if current_user.is_admin:
        flash("Un compte administrateur ne peut pas s'inscrire à une formation.", "danger")
        return redirect(url_for("formation_detail", cid=cid))
    if not PAYDUNYA_ENABLED:
        flash("Le paiement en ligne automatique n'est pas encore activé sur ce site.", "danger")
        return redirect(url_for("formation_detail", cid=cid))

    formation = db.session.get(Course, cid)
    if not formation or not formation.published:
        abort(404)

    existante = Enrollment.query.filter(
        Enrollment.student_id == current_user.id,
        Enrollment.course_id == cid,
        Enrollment.status.in_(["en_attente", "validee"]),
    ).first()
    if existante:
        flash("Vous avez déjà une inscription en cours ou validée pour cette formation.", "info")
        return redirect(url_for("formation_detail", cid=cid))

    e = Enrollment(
        student_id=current_user.id,
        course_id=formation.id,
        amount=formation.price,
        payment_method="paydunya",
        payment_source="paydunya",
        status="en_attente",
    )
    db.session.add(e)
    db.session.flush()  # attribue e.id sans clôturer la transaction

    try:
        resp = requests.post(
            f"{PAYDUNYA_API_BASE}/checkout-invoice/create",
            headers=_paydunya_headers(),
            json={
                "invoice": {
                    "total_amount": int(round(formation.price)),
                    "description": f"Formation : {formation.title}"[:255],
                    "customer": {
                        "name": current_user.full_name,
                        "email": current_user.email,
                        "phone": current_user.phone or "",
                    },
                },
                "store": {"name": CABINET_NAME},
                "custom_data": {"enrollment_id": e.id},
                "actions": {
                    "cancel_url": url_for("formation_detail", cid=cid, _external=True),
                    "return_url": url_for("paydunya_retour", eid=e.id, _external=True),
                    "callback_url": url_for("paydunya_notify", _external=True),
                },
            },
            timeout=20,
        )
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        db.session.rollback()
        app.logger.error("PayDunya: échec d'initialisation du paiement : %s", exc)
        flash(
            "Le paiement en ligne n'a pas pu être initié pour le moment. "
            "Vous pouvez réessayer, ou utiliser le paiement manuel ci-dessous.",
            "danger",
        )
        return redirect(url_for("formation_detail", cid=cid))

    payment_url = data.get("response_text")
    token = data.get("token")
    if data.get("response_code") != "00" or not payment_url or not token:
        db.session.rollback()
        app.logger.error("PayDunya: réponse inattendue à l'initialisation : %s", data)
        flash(
            "Le paiement en ligne n'a pas pu être initié. "
            "Vous pouvez réessayer, ou utiliser le paiement manuel ci-dessous.",
            "danger",
        )
        return redirect(url_for("formation_detail", cid=cid))

    e.paydunya_token = token
    e.payment_reference = token
    db.session.commit()
    return redirect(payment_url)


@app.route("/paiement/paydunya/notify", methods=["GET", "POST"])
def paydunya_notify():
    """Callback IPN appelé par PayDunya pour confirmer un paiement. Doit
    répondre 200 (avec un corps "OK", comme demandé par la documentation
    PayDunya) dans tous les cas pour accuser réception. On ne fait jamais
    confiance au contenu du callback lui-même : on revérifie systématiquement
    via l'API /checkout-invoice/confirm, comme pour CinetPay, afin d'éviter
    toute notification falsifiée."""
    token = (
        request.values.get("data[invoice][token]")
        or request.values.get("token")
        or request.values.get("invoice_token")
    )
    if not token:
        return "OK", 200
    enrollment = Enrollment.query.filter_by(paydunya_token=token).first()
    if not enrollment:
        return "OK", 200
    pd_status = _paydunya_check_status(token)
    if pd_status:
        _paydunya_apply_status(enrollment, pd_status)
    return "OK", 200


@app.route("/paiement/paydunya/retour/<int:eid>")
@login_required
def paydunya_retour(eid):
    """Page de retour après le passage de l'étudiant sur la page de paiement
    PayDunya (succès, échec ou abandon). Revérifie une fois le statut tout de
    suite pour un retour immédiat, au cas où le callback mettrait quelques
    secondes à arriver — sans effet si /notify a déjà traité l'inscription."""
    enrollment = db.session.get(Enrollment, eid)
    if not enrollment or enrollment.student_id != current_user.id:
        abort(404)
    if enrollment.status == "en_attente" and enrollment.paydunya_token:
        pd_status = _paydunya_check_status(enrollment.paydunya_token)
        if pd_status:
            _paydunya_apply_status(enrollment, pd_status)

    if enrollment.status == "validee":
        flash("Paiement confirmé, bienvenue dans la formation !", "success")
    elif enrollment.status == "rejetee":
        flash(
            "Le paiement n'a pas abouti (refusé ou annulé). Vous pouvez réessayer.",
            "danger",
        )
    else:
        flash(
            "Paiement en cours de confirmation. L'accès à la formation sera débloqué "
            "automatiquement dès sa validation (généralement en quelques instants).",
            "info",
        )
    return redirect(url_for("mes_formations"))


# ---------- Espace étudiant ----------

@app.route("/mes-formations")
@login_required
def mes_formations():
    if current_user.is_admin:
        return redirect(url_for("admin_formations"))
    inscriptions = (
        Enrollment.query.filter_by(student_id=current_user.id)
        .order_by(Enrollment.created_at.desc())
        .all()
    )

    quiz_stats = {}  # course_id -> {"reussis": int, "total": int}
    for e in inscriptions:
        if e.status != "validee" or not e.course:
            continue
        total = 0
        reussis = 0
        for l in e.course.lessons:
            if l.quiz:
                total += 1
                meilleure = (
                    QuizAttempt.query.filter_by(quiz_id=l.quiz.id, student_id=current_user.id)
                    .order_by(QuizAttempt.score.desc()).first()
                )
                if meilleure and meilleure.passed:
                    reussis += 1
        if total:
            quiz_stats[e.course_id] = {"reussis": reussis, "total": total}

    return render_template("mes_formations.html", inscriptions=inscriptions, quiz_stats=quiz_stats)


@app.route("/formations/<int:cid>/apprendre")
@login_required
def apprendre(cid):
    formation = db.session.get(Course, cid)
    if not formation:
        abort(404)
    if not current_user.is_admin:
        acces = Enrollment.query.filter_by(
            student_id=current_user.id, course_id=cid, status="validee"
        ).first()
        if not acces:
            flash("Vous n'avez pas (encore) accès à cette formation.", "danger")
            return redirect(url_for("formation_detail", cid=cid))
    lecons = formation.lessons.order_by(Lesson.position).all()

    meilleurs_scores = {}
    if not current_user.is_admin:
        for l in lecons:
            if l.quiz:
                meilleure = (
                    QuizAttempt.query.filter_by(quiz_id=l.quiz.id, student_id=current_user.id)
                    .order_by(QuizAttempt.score.desc()).first()
                )
                if meilleure:
                    meilleurs_scores[l.id] = meilleure

    return render_template(
        "apprendre.html", formation=formation, lecons=lecons,
        meilleurs_scores=meilleurs_scores,
    )


# ---------- Espace étudiant : quiz d'évaluation ----------

def _acces_lecon_ok(lesson):
    """Vérifie que l'utilisateur courant a accès à la leçon (admin, ou inscription validée)."""
    if current_user.is_admin:
        return True
    return Enrollment.query.filter_by(
        student_id=current_user.id, course_id=lesson.course_id, status="validee"
    ).first() is not None


@app.route("/lecons/<int:lid>/quiz", methods=["GET", "POST"])
@login_required
def passer_quiz(lid):
    lesson = db.session.get(Lesson, lid)
    if not lesson or not lesson.quiz:
        abort(404)
    if not _acces_lecon_ok(lesson):
        flash("Vous n'avez pas (encore) accès à cette formation.", "danger")
        return redirect(url_for("formation_detail", cid=lesson.course_id))

    quiz = lesson.quiz
    questions = quiz.questions.order_by(Question.position).all()

    if request.method == "POST" and not current_user.is_admin:
        correct_count = 0
        for q in questions:
            reponse = request.form.get(f"question_{q.id}")
            if reponse is not None:
                choix = db.session.get(Choice, int(reponse)) if reponse.isdigit() else None
                if choix and choix.question_id == q.id and choix.is_correct:
                    correct_count += 1
        total = len(questions)
        score = round((correct_count / total) * 100) if total else 0
        attempt = QuizAttempt(
            quiz_id=quiz.id, student_id=current_user.id, score=score,
            correct_count=correct_count, total_count=total,
            passed=score >= quiz.pass_score,
        )
        db.session.add(attempt)
        db.session.commit()
        return render_template(
            "quiz_resultat.html", formation=lesson.course, lesson=lesson,
            quiz=quiz, attempt=attempt,
        )

    dernieres_tentatives = []
    if not current_user.is_admin:
        dernieres_tentatives = (
            QuizAttempt.query.filter_by(quiz_id=quiz.id, student_id=current_user.id)
            .order_by(QuizAttempt.created_at.desc()).all()
        )
    return render_template(
        "quiz.html", formation=lesson.course, lesson=lesson,
        quiz=quiz, questions=questions, tentatives=dernieres_tentatives,
    )


# ---------- Administration : formations et leçons ----------

@app.route("/admin/formations", methods=["GET", "POST"])
@login_required
@admin_required
def admin_formations():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        image_url = request.form.get("image_url", "").strip()
        try:
            price = float(request.form.get("price") or 0)
        except ValueError:
            flash("Prix invalide.", "danger")
            return redirect(url_for("admin_formations"))
        if not title:
            flash("Le titre est obligatoire.", "danger")
        else:
            c = Course(title=title, description=description, price=price, image_url=image_url, published=True)
            db.session.add(c)
            db.session.commit()
            flash(f"Formation « {title} » créée.", "success")
        return redirect(url_for("admin_formations"))

    liste = Course.query.order_by(Course.created_at.desc()).all()
    return render_template("admin_formations.html", liste=liste)


def _appliquer_document_upload(lesson):
    """Lit le fichier PDF envoyé (champ 'document_file') et le stocke sur la
    leçon. Retourne un message d'erreur (str) si le fichier n'est pas un PDF,
    sinon None. N'a aucun effet si aucun fichier n'a été sélectionné."""
    fichier = request.files.get("document_file")
    if not fichier or not fichier.filename:
        return None
    nom = fichier.filename
    type_mime = fichier.mimetype or "application/pdf"
    if type_mime != "application/pdf" and not nom.lower().endswith(".pdf"):
        return "Seuls les fichiers PDF sont acceptés pour le document d'une leçon."
    lesson.document_data = fichier.read()
    lesson.document_filename = nom
    lesson.document_mimetype = "application/pdf"
    return None


@app.route("/admin/formations/<int:cid>", methods=["GET", "POST"])
@login_required
@admin_required
def admin_formation_detail(cid):
    formation = db.session.get(Course, cid)
    if not formation:
        abort(404)

    if request.method == "POST":
        # Ajout d'une nouvelle leçon
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        video_url = request.form.get("video_url", "").strip()
        document_url = request.form.get("document_url", "").strip()
        document_label = request.form.get("document_label", "").strip()
        if not title:
            flash("Le titre de la leçon est obligatoire.", "danger")
        else:
            position = (formation.lessons.count() or 0) + 1
            lesson = Lesson(
                course_id=formation.id, title=title, content=content,
                video_url=video_url, document_url=document_url,
                document_label=document_label, position=position,
            )
            erreur = _appliquer_document_upload(lesson)
            if erreur:
                flash(erreur, "danger")
                return redirect(url_for("admin_formation_detail", cid=cid))
            db.session.add(lesson)
            db.session.commit()
            flash("Leçon ajoutée.", "success")
        return redirect(url_for("admin_formation_detail", cid=cid))

    lecons = formation.lessons.order_by(Lesson.position).all()
    return render_template("admin_formation_detail.html", formation=formation, lecons=lecons)


@app.route("/admin/formations/<int:cid>/modifier", methods=["POST"])
@login_required
@admin_required
def admin_modifier_formation(cid):
    c = db.session.get(Course, cid)
    if not c:
        abort(404)
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    image_url = request.form.get("image_url", "").strip()
    try:
        price = float(request.form.get("price") or 0)
    except ValueError:
        flash("Prix invalide.", "danger")
        return redirect(url_for("admin_formation_detail", cid=cid))
    if title:
        c.title = title
    c.description = description
    c.image_url = image_url
    c.price = price
    c.published = request.form.get("published") == "on"
    db.session.commit()
    flash("Formation mise à jour.", "success")
    return redirect(url_for("admin_formation_detail", cid=cid))


@app.route("/admin/formations/<int:cid>/supprimer", methods=["POST"])
@login_required
@admin_required
def admin_supprimer_formation(cid):
    c = db.session.get(Course, cid)
    if c:
        if c.enrollments.count() > 0:
            flash("Impossible de supprimer : des étudiants sont inscrits à cette formation.", "danger")
        else:
            db.session.delete(c)
            db.session.commit()
            flash("Formation supprimée.", "info")
    return redirect(url_for("admin_formations"))


@app.route("/admin/lecons/<int:lid>/modifier", methods=["POST"])
@login_required
@admin_required
def admin_modifier_lecon(lid):
    lesson = db.session.get(Lesson, lid)
    if not lesson:
        abort(404)
    title = request.form.get("title", "").strip()
    if title:
        lesson.title = title
    lesson.content = request.form.get("content", "").strip()
    lesson.video_url = request.form.get("video_url", "").strip()
    lesson.document_url = request.form.get("document_url", "").strip()
    lesson.document_label = request.form.get("document_label", "").strip()
    if request.form.get("remove_document") == "on":
        lesson.document_data = None
        lesson.document_filename = None
        lesson.document_mimetype = None
    erreur = _appliquer_document_upload(lesson)
    if erreur:
        flash(erreur, "danger")
        return redirect(url_for("admin_formation_detail", cid=lesson.course_id))
    db.session.commit()
    flash("Leçon mise à jour.", "success")
    return redirect(url_for("admin_formation_detail", cid=lesson.course_id))


@app.route("/lecons/<int:lid>/document")
@login_required
def telecharger_document_lecon(lid):
    lesson = db.session.get(Lesson, lid)
    if not lesson or not lesson.document_data:
        abort(404)
    if not _acces_lecon_ok(lesson):
        flash("Vous n'avez pas (encore) accès à cette formation.", "danger")
        return redirect(url_for("formation_detail", cid=lesson.course_id))
    nom = lesson.document_filename or "document.pdf"
    return Response(
        lesson.document_data,
        mimetype=lesson.document_mimetype or "application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nom}"'},
    )


@app.route("/admin/lecons/<int:lid>/supprimer", methods=["POST"])
@login_required
@admin_required
def admin_supprimer_lecon(lid):
    lesson = db.session.get(Lesson, lid)
    if lesson:
        cid = lesson.course_id
        db.session.delete(lesson)
        db.session.commit()
        flash("Leçon supprimée.", "info")
        return redirect(url_for("admin_formation_detail", cid=cid))
    return redirect(url_for("admin_formations"))


# ---------- Administration : quiz d'évaluation ----------

@app.route("/admin/lecons/<int:lid>/quiz", methods=["GET", "POST"])
@login_required
@admin_required
def admin_quiz(lid):
    lesson = db.session.get(Lesson, lid)
    if not lesson:
        abort(404)

    if request.method == "POST":
        title = request.form.get("title", "").strip() or "Quiz"
        try:
            pass_score = int(request.form.get("pass_score") or 70)
        except ValueError:
            pass_score = 70
        pass_score = max(0, min(100, pass_score))

        if lesson.quiz:
            lesson.quiz.title = title
            lesson.quiz.pass_score = pass_score
        else:
            db.session.add(Quiz(lesson_id=lesson.id, title=title, pass_score=pass_score))
        db.session.commit()
        flash("Quiz enregistré.", "success")
        return redirect(url_for("admin_quiz", lid=lid))

    questions = lesson.quiz.questions.order_by(Question.position).all() if lesson.quiz else []
    return render_template("admin_quiz.html", lesson=lesson, formation=lesson.course, questions=questions)


@app.route("/admin/lecons/<int:lid>/quiz/supprimer", methods=["POST"])
@login_required
@admin_required
def admin_supprimer_quiz(lid):
    lesson = db.session.get(Lesson, lid)
    if not lesson:
        abort(404)
    if lesson.quiz:
        db.session.delete(lesson.quiz)
        db.session.commit()
        flash("Quiz supprimé.", "info")
    return redirect(url_for("admin_formation_detail", cid=lesson.course_id))


@app.route("/admin/quiz/<int:qid>/questions", methods=["POST"])
@login_required
@admin_required
def admin_ajouter_question(qid):
    quiz = db.session.get(Quiz, qid)
    if not quiz:
        abort(404)
    text = request.form.get("text", "").strip()
    if not text:
        flash("L'énoncé de la question est obligatoire.", "danger")
        return redirect(url_for("admin_quiz", lid=quiz.lesson_id))

    choix_textes = request.form.getlist("choice_text")
    bonne_reponse = request.form.get("correct_choice")  # index (str) du choix correct

    choix_valides = [(i, t.strip()) for i, t in enumerate(choix_textes) if t.strip()]
    if len(choix_valides) < 2:
        flash("Il faut au moins deux choix de réponse.", "danger")
        return redirect(url_for("admin_quiz", lid=quiz.lesson_id))
    if bonne_reponse is None or not any(str(i) == bonne_reponse for i, _ in choix_valides):
        flash("Merci d'indiquer quelle réponse est correcte.", "danger")
        return redirect(url_for("admin_quiz", lid=quiz.lesson_id))

    position = (quiz.questions.count() or 0) + 1
    question = Question(quiz_id=quiz.id, text=text, position=position)
    db.session.add(question)
    db.session.flush()  # pour obtenir question.id

    for pos, (i, choice_text) in enumerate(choix_valides, start=1):
        db.session.add(Choice(
            question_id=question.id, text=choice_text,
            is_correct=(str(i) == bonne_reponse), position=pos,
        ))
    db.session.commit()
    flash("Question ajoutée.", "success")
    return redirect(url_for("admin_quiz", lid=quiz.lesson_id))


@app.route("/admin/questions/<int:qid>/supprimer", methods=["POST"])
@login_required
@admin_required
def admin_supprimer_question(qid):
    question = db.session.get(Question, qid)
    if question:
        lid = question.quiz.lesson_id
        db.session.delete(question)
        db.session.commit()
        flash("Question supprimée.", "info")
        return redirect(url_for("admin_quiz", lid=lid))
    return redirect(url_for("admin_formations"))


# ---------- Administration : inscriptions / paiements ----------

@app.route("/admin/inscriptions")
@login_required
@admin_required
def admin_inscriptions():
    statut_filtre = request.args.get("statut", "en_attente")
    q = Enrollment.query
    if statut_filtre in ("en_attente", "validee", "rejetee"):
        q = q.filter_by(status=statut_filtre)
    liste = q.order_by(Enrollment.created_at.desc()).all()
    payment_methods_display = dict(PAYMENT_METHODS)
    payment_methods_display["cinetpay"] = "Paiement en ligne (CinetPay)"
    payment_methods_display["paydunya"] = "Paiement en ligne (PayDunya)"
    return render_template(
        "admin_inscriptions.html", liste=liste, statut_filtre=statut_filtre,
        payment_methods=payment_methods_display,
    )


@app.route("/admin/inscriptions/<int:eid>/valider", methods=["POST"])
@login_required
@admin_required
def admin_valider_inscription(eid):
    e = db.session.get(Enrollment, eid)
    if not e or e.status != "en_attente":
        flash("Inscription introuvable ou déjà traitée.", "danger")
        return redirect(url_for("admin_inscriptions"))
    e.status = "validee"
    e.validated_at = datetime.utcnow()
    e.validated_by_id = current_user.id
    db.session.commit()
    flash(f"Inscription validée : {e.student.full_name} → {e.course.title}.", "success")
    return redirect(url_for("admin_inscriptions"))


@app.route("/admin/inscriptions/<int:eid>/rejeter", methods=["POST"])
@login_required
@admin_required
def admin_rejeter_inscription(eid):
    e = db.session.get(Enrollment, eid)
    if not e or e.status != "en_attente":
        flash("Inscription introuvable ou déjà traitée.", "danger")
        return redirect(url_for("admin_inscriptions"))
    e.status = "rejetee"
    e.note_admin = request.form.get("note_admin", "").strip()
    e.validated_at = datetime.utcnow()
    e.validated_by_id = current_user.id
    db.session.commit()
    flash("Inscription rejetée.", "info")
    return redirect(url_for("admin_inscriptions"))


@app.route("/admin/etudiants")
@login_required
@admin_required
def admin_etudiants():
    liste = User.query.filter_by(role="etudiant").order_by(User.created_at.desc()).all()
    return render_template("admin_etudiants.html", liste=liste)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug, host="0.0.0.0", port=port)
