import os
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, redirect, url_for, request, flash, abort
)
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user
)

from models import db, User, Course, Lesson, Enrollment

APP_NAME = os.environ.get("APP_NAME", "Agro Eco Consulting")
CABINET_NAME = "Cabinet AgroEcoConsult"

PAYMENT_METHODS = [
    ("wave", "Wave"),
    ("orange_money", "Orange Money"),
    ("free_money", "Free Money"),
    ("virement", "Virement bancaire"),
    ("autre", "Autre"),
]


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

if IS_PRODUCTION and app.config["SECRET_KEY"] == "agroeco-formation-secret-key-change-en-production":
    raise RuntimeError(
        "SECRET_KEY par défaut détectée en production ! "
        "Définissez la variable d'environnement SECRET_KEY avant de déployer "
        "(voir DEPLOIEMENT.md)."
    )

db.init_app(app)

with app.app_context():
    db.create_all()
    from seed import ensure_seed_data
    ensure_seed_data(verbose=False)

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
    formations = Course.query.filter_by(published=True).order_by(Course.created_at.desc()).all()
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
    return render_template("mes_formations.html", inscriptions=inscriptions)


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
    return render_template("apprendre.html", formation=formation, lecons=lecons)


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
    db.session.commit()
    flash("Leçon mise à jour.", "success")
    return redirect(url_for("admin_formation_detail", cid=lesson.course_id))


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
    return render_template(
        "admin_inscriptions.html", liste=liste, statut_filtre=statut_filtre,
        payment_methods=dict(PAYMENT_METHODS),
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
