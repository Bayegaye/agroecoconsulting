from app import app, db
from seed import ensure_seed_data

with app.app_context():
    db.create_all()
    ensure_seed_data(verbose=True)
    print("Base de données initialisée.")
