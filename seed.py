import os
import secrets
from models import db, User
 
DEFAULT_ADMIN_EMAIL = "admin@agroecoconsult.sn"
 
 
def _mot_de_passe_genere():
    """Mot de passe aléatoire utilisé UNIQUEMENT si la variable d'environnement
    ADMIN_PASSWORD n'est pas définie (ex. exécution locale rapide). Il n'est
    jamais écrit dans le code : il est généré à chaque démarrage et affiché
    une seule fois dans les logs du serveur. En production, définissez
    toujours ADMIN_PASSWORD dans les variables d'environnement."""
    return secrets.token_urlsafe(12)
 
 
def ensure_seed_data(verbose=False):
    admin = User.query.filter_by(email=DEFAULT_ADMIN_EMAIL).first()
    admin_password_env = os.environ.get("ADMIN_PASSWORD")
 
    if not admin:
        admin_password = admin_password_env or _mot_de_passe_genere()
        admin = User(
            full_name="Administrateur AgroEcoConsult",
            email=DEFAULT_ADMIN_EMAIL,
            role="admin",
        )
        admin.set_password(admin_password)
        admin.active = True
        db.session.add(admin)
        if verbose or not admin_password_env:
            print(f"Compte admin créé : {DEFAULT_ADMIN_EMAIL} / {admin_password}")
            if not admin_password_env:
                print("ADMIN_PASSWORD n'est pas défini : ce mot de passe généré "
                      "ne sera plus jamais affiché. Définissez ADMIN_PASSWORD "
                      "dans vos variables d'environnement pour en choisir un vous-même.")
    else:
        if os.environ.get("RESET_ADMIN_PASSWORD") == "1":
            new_password = admin_password_env or _mot_de_passe_genere()
            admin.set_password(new_password)
            admin.active = True
            if verbose or not admin_password_env:
                print(f"Mot de passe admin réinitialisé : {new_password}")
    db.session.commit()
 
