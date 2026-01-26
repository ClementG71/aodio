"""
Application Flask principale pour aodio
Point d'entrée simplifié après refactoring
"""
import os
from pathlib import Path
from dotenv import load_dotenv
import logging

# Chargement des variables d'environnement
if Path('.env.local').exists():
    load_dotenv('.env.local')
else:
    load_dotenv()

# Import de la configuration centralisée
from config import UPLOAD_FOLDER, PROCESSED_FOLDER, LOGS_FOLDER, BASE_DIR

# Configuration du logging
Path(LOGS_FOLDER).mkdir(parents=True, exist_ok=True)
try:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(f'{LOGS_FOLDER}/app.log'),
            logging.StreamHandler()
        ]
    )
    from config import VOLUME_PATH
    if VOLUME_PATH and Path(VOLUME_PATH).exists():
        logging.info(f"Utilisation du volume Railway: {VOLUME_PATH}")
except Exception as e:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    print(f"Warning: Impossible d'écrire dans le fichier de log: {e}")

logger = logging.getLogger(__name__)

# Les variables d'environnement sont déjà configurées dans config.py

# Import et création de l'application
def create_app():
    """Crée et configure l'application Flask"""
    from routes.main_routes import create_app
    return create_app()

# Point d'entrée principal
if __name__ == '__main__':
    app = create_app()
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode, host='0.0.0.0', port=5000)