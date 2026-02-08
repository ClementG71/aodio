"""
Configuration centralisée de l'application Aodio
Gère les chemins de dossiers selon l'environnement (Dokploy, Railway, local)
"""
import os
from pathlib import Path

# Répertoire de base de l'application
BASE_DIR = Path(__file__).parent.resolve()

# Vérifier si nous sommes dans un environnement Dokploy
DOKPLOY_ENV = os.getenv('DOKPLOY_ENV', 'false').lower() == 'true'

# Mode Voxtral-only : transcription + diarisation via Voxtral Mini Transcribe V2 uniquement (pas de RunPod)
USE_VOXTRAL_ONLY = os.getenv('USE_VOXTRAL_ONLY', 'false').lower() == 'true'

# Configuration des dossiers selon l'environnement
if DOKPLOY_ENV:
    # Configuration pour Dokploy - chemins absolus
    UPLOAD_FOLDER = str(BASE_DIR / 'uploads')
    PROCESSED_FOLDER = str(BASE_DIR / 'processed')
    LOGS_FOLDER = str(BASE_DIR / 'logs')
else:
    # Configuration pour Railway ou développement local
    VOLUME_PATH = os.getenv('RAILWAY_VOLUME_MOUNT_PATH')
    if VOLUME_PATH and Path(VOLUME_PATH).exists():
        UPLOAD_FOLDER = str(Path(VOLUME_PATH) / 'uploads')
        PROCESSED_FOLDER = str(Path(VOLUME_PATH) / 'processed')
        LOGS_FOLDER = str(Path(VOLUME_PATH) / 'logs')
    else:
        UPLOAD_FOLDER = str(BASE_DIR / 'uploads')
        PROCESSED_FOLDER = str(BASE_DIR / 'processed')
        LOGS_FOLDER = str(BASE_DIR / 'logs')

# Création des dossiers nécessaires
for folder in [UPLOAD_FOLDER, PROCESSED_FOLDER, LOGS_FOLDER]:
    Path(folder).mkdir(parents=True, exist_ok=True)

# Configuration des variables d'environnement pour les modules
os.environ['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.environ['PROCESSED_FOLDER'] = PROCESSED_FOLDER
os.environ['LOGS_FOLDER'] = LOGS_FOLDER

# Autres constantes de configuration
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB
ALLOWED_EXTENSIONS = {'wav', 'mp3', 'm4a', 'flac', 'ogg', 'webm'}

# Variable pour compatibilité avec app.py
VOLUME_PATH = os.getenv('RAILWAY_VOLUME_MOUNT_PATH')
