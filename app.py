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

# Configuration des dossiers
VOLUME_PATH = os.getenv('RAILWAY_VOLUME_MOUNT_PATH')
if VOLUME_PATH and Path(VOLUME_PATH).exists():
    UPLOAD_FOLDER = str(Path(VOLUME_PATH) / 'uploads')
    PROCESSED_FOLDER = str(Path(VOLUME_PATH) / 'processed')
    LOGS_FOLDER = str(Path(VOLUME_PATH) / 'logs')
else:
    UPLOAD_FOLDER = 'uploads'
    PROCESSED_FOLDER = 'processed'
    LOGS_FOLDER = 'logs'

# Création des dossiers nécessaires
for folder in [UPLOAD_FOLDER, PROCESSED_FOLDER, LOGS_FOLDER]:
    Path(folder).mkdir(parents=True, exist_ok=True)

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

# Configuration des variables d'environnement pour les modules
os.environ['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.environ['PROCESSED_FOLDER'] = PROCESSED_FOLDER
os.environ['LOGS_FOLDER'] = LOGS_FOLDER

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