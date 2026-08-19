"""Point d'entrée WSGI pour l'hébergement cPanel (Passenger) sur Namecheap.

Passenger exige que l'application WSGI soit exposée sous le nom `application`
(voir la doc Namecheap "Setup Python App"). Ce fichier fait simplement le
pont vers l'objet Flask `app` défini dans app.py, sans dupliquer la logique
de configuration.
"""
from app import app as application

if __name__ == "__main__":
    application.run()
