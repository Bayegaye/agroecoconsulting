from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(db.Model, UserMixin):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(128), nullable=False)
    email = db.Column(db.String(128), unique=True, nullable=False)
    phone = db.Column(db.String(32))
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="etudiant")  # admin | etudiant
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    enrollments = db.relationship(
        "Enrollment", foreign_keys="Enrollment.student_id", backref="student", lazy="dynamic"
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == "admin"

    def get_id(self):
        return str(self.id)


class Course(db.Model):
    """Une formation payante proposée par le cabinet."""
    __tablename__ = "courses"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False, default=0)
    image_url = db.Column(db.String(500))  # lien vers une image de couverture (optionnel)
    published = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    lessons = db.relationship(
        "Lesson", backref="course", lazy="dynamic",
        order_by="Lesson.position", cascade="all, delete-orphan"
    )
    enrollments = db.relationship("Enrollment", backref="course", lazy="dynamic")


class Lesson(db.Model):
    """Une leçon d'une formation : vidéo (lien) et/ou document (lien) et/ou texte."""
    __tablename__ = "lessons"
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    content = db.Column(db.Text)  # texte / instructions (optionnel)
    video_url = db.Column(db.String(500))  # ex: lien YouTube non répertorié / Vimeo (optionnel)
    document_url = db.Column(db.String(500))  # ex: lien Google Drive / Dropbox vers un PDF (optionnel)
    document_label = db.Column(db.String(160))  # ex: "Support de cours (PDF)"
    position = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Enrollment(db.Model):
    """Inscription d'un étudiant à une formation, avec suivi du paiement.

    Le paiement est confirmé manuellement : l'étudiant indique comment et
    avec quelle référence il a payé (Wave, Orange Money, Free Money,
    virement...), puis un administrateur vérifie et valide (ou rejette)
    l'inscription depuis l'espace admin. L'accès au contenu de la formation
    n'est débloqué qu'une fois le statut passé à 'validee'."""
    __tablename__ = "enrollments"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)  # prix au moment de l'inscription
    payment_method = db.Column(db.String(30), nullable=False)  # wave | orange_money | free_money | virement | autre
    payment_reference = db.Column(db.String(120))  # référence / n° de transaction communiqué par l'étudiant
    payment_phone = db.Column(db.String(32))  # numéro utilisé pour le paiement
    status = db.Column(db.String(20), nullable=False, default="en_attente")  # en_attente | validee | rejetee
    note_admin = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    validated_at = db.Column(db.DateTime)
    validated_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    validated_by = db.relationship("User", foreign_keys=[validated_by_id])
