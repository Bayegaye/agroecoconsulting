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

    evaluation = db.relationship(
        "Evaluation", backref="lesson", uselist=False,
        cascade="all, delete-orphan", single_parent=True,
    )


class Evaluation(db.Model):
    """Évaluation associée à une leçon : quiz à choix multiples (correction
    automatique du score) ou devoir à rendre (réponse libre + lien optionnel).

    Tant qu'un administrateur n'a pas validé la soumission d'un étudiant pour
    l'évaluation d'une leçon, les leçons suivantes de la formation restent
    verrouillées pour cet étudiant."""
    __tablename__ = "evaluations"
    id = db.Column(db.Integer, primary_key=True)
    lesson_id = db.Column(db.Integer, db.ForeignKey("lessons.id"), nullable=False, unique=True)
    type = db.Column(db.String(10), nullable=False)  # quiz | devoir
    title = db.Column(db.String(160), nullable=False)
    instructions = db.Column(db.Text)  # consigne du quiz, ou énoncé du devoir
    seuil_reussite = db.Column(db.Float, default=50)  # % indicatif pour un quiz (la validation reste manuelle)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    questions = db.relationship(
        "QuizQuestion", backref="evaluation", lazy="dynamic",
        order_by="QuizQuestion.position", cascade="all, delete-orphan",
    )
    submissions = db.relationship(
        "Submission", backref="evaluation", lazy="dynamic", cascade="all, delete-orphan"
    )


class QuizQuestion(db.Model):
    __tablename__ = "quiz_questions"
    id = db.Column(db.Integer, primary_key=True)
    evaluation_id = db.Column(db.Integer, db.ForeignKey("evaluations.id"), nullable=False)
    text = db.Column(db.Text, nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)

    options = db.relationship(
        "QuizOption", backref="question", lazy="dynamic",
        order_by="QuizOption.id", cascade="all, delete-orphan",
    )


class QuizOption(db.Model):
    __tablename__ = "quiz_options"
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey("quiz_questions.id"), nullable=False)
    text = db.Column(db.String(300), nullable=False)
    is_correct = db.Column(db.Boolean, default=False)


class Submission(db.Model):
    """Soumission d'un étudiant pour l'évaluation d'une leçon (réponses au
    quiz, ou devoir rendu). La note est calculée automatiquement pour un
    quiz (indicative) ou saisie par l'administrateur pour un devoir, mais la
    validation qui débloque la suite reste toujours une action manuelle de
    l'administrateur, comme pour la vérification des paiements."""
    __tablename__ = "submissions"
    id = db.Column(db.Integer, primary_key=True)
    evaluation_id = db.Column(db.Integer, db.ForeignKey("evaluations.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    devoir_reponse = db.Column(db.Text)  # réponse texte libre (type devoir)
    devoir_lien = db.Column(db.String(500))  # lien vers un fichier rendu (Drive, etc. — type devoir)
    score = db.Column(db.Float)  # note sur 100 : calculée pour un quiz, saisie par l'admin pour un devoir
    status = db.Column(db.String(20), nullable=False, default="en_attente")  # en_attente | validee | rejetee
    admin_feedback = db.Column(db.String(500))
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    graded_at = db.Column(db.DateTime)
    graded_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    student = db.relationship("User", foreign_keys=[student_id])
    graded_by = db.relationship("User", foreign_keys=[graded_by_id])
    reponses = db.relationship(
        "SubmissionAnswer", backref="submission", lazy="dynamic", cascade="all, delete-orphan"
    )


class SubmissionAnswer(db.Model):
    """Réponse choisie par l'étudiant pour une question de quiz, dans le
    cadre d'une soumission donnée."""
    __tablename__ = "submission_answers"
    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey("submissions.id"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("quiz_questions.id"), nullable=False)
    option_id = db.Column(db.Integer, db.ForeignKey("quiz_options.id"))

    question = db.relationship("QuizQuestion")
    option = db.relationship("QuizOption")


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
