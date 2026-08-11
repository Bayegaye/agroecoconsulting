import os
from models import db, User

DEFAULT_ADMIN_EMAIL = "admin@agroecoconsult.sn"
DEFAULT_ADMIN_PASSWORD = "agroeco2026"


def ensure_seed_data(verbose=False):
    admin = User.query.filter_by(email=DEFAULT_ADMIN_EMAIL).first()
    if not admin:
        admin_password = os.environ.get("ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD)
        admin = User(
            full_name="Administrateur AgroEcoConsult",
            email=DEFAULT_ADMIN_EMAIL,
            role="admin",
        )
        admin.set_password(admin_password)
        admin.active = True
        db.session.add(admin)
        if verbose:
            print(f"Compte admin créé : {DEFAULT_ADMIN_EMAIL} / {admin_password}")
    else:
        if os.environ.get("RESET_ADMIN_PASSWORD") == "1":
            new_password = os.environ.get("ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD)
            admin.set_password(new_password)
            admin.active = True
            if verbose:
                print("Mot de passe admin réinitialisé.")
    db.session.commit()
