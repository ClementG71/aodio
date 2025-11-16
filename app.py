"""
Application Flask principale pour aodio
Transcription audio et préparation de comptes rendus de réunions
"""
import os
import json
import uuid
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, session
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
import logging
from dotenv import load_dotenv

# Chargement des variables d'environnement
# Charge .env.local en priorité pour le développement local, puis .env
if Path('.env.local').exists():
    load_dotenv('.env.local')
else:
    load_dotenv()

# Configuration
# Utiliser le volume Railway si disponible, sinon utiliser le dossier local
# Le volume Railway peut être monté via la variable d'environnement RAILWAY_VOLUME_MOUNT_PATH
VOLUME_PATH = os.getenv('RAILWAY_VOLUME_MOUNT_PATH')
if VOLUME_PATH and Path(VOLUME_PATH).exists():
    # Utiliser le volume Railway pour le stockage persistant
    UPLOAD_FOLDER = str(Path(VOLUME_PATH) / 'uploads')
    PROCESSED_FOLDER = str(Path(VOLUME_PATH) / 'processed')
    LOGS_FOLDER = str(Path(VOLUME_PATH) / 'logs')
else:
    # Fallback sur le système de fichiers local
    UPLOAD_FOLDER = 'uploads'
    PROCESSED_FOLDER = 'processed'
    LOGS_FOLDER = 'logs'

ALLOWED_EXTENSIONS = {'wav', 'mp3', 'm4a', 'flac', 'ogg', 'webm'}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB

# Création des dossiers nécessaires
for folder in [UPLOAD_FOLDER, PROCESSED_FOLDER, LOGS_FOLDER]:
    Path(folder).mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE
app.config['PROCESSED_FOLDER'] = PROCESSED_FOLDER
app.config['LOGS_FOLDER'] = LOGS_FOLDER

# Configuration des APIs
app.config['ANTHROPIC_API_KEY'] = os.getenv('ANTHROPIC_API_KEY')
app.config['RUNPOD_API_KEY'] = os.getenv('RUNPOD_API_KEY')
app.config['RUNPOD_ENDPOINT_ID'] = os.getenv('RUNPOD_ENDPOINT_ID')
app.config['MISTRAL_API_KEY'] = os.getenv('MISTRAL_API_KEY')
app.config['MISTRAL_ENDPOINT'] = os.getenv('MISTRAL_ENDPOINT', 'https://api.mistral.ai/v1')

# Logging
# Créer le dossier logs s'il n'existe pas
Path(LOGS_FOLDER).mkdir(parents=True, exist_ok=True)

# Configuration du logging avec gestion d'erreur pour le fichier
# Utilise LOGS_FOLDER qui peut être sur le volume Railway
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
    # Si l'écriture dans le fichier échoue, utiliser seulement StreamHandler
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    print(f"Warning: Impossible d'écrire dans le fichier de log: {e}")

logger = logging.getLogger(__name__)

# Import des modules
from services.audio_processor import AudioProcessor
from services.runpod_worker import RunPodWorker
from services.mistral_voxtral import MistralVoxtralClient
from services.llm_processor import LLMProcessor
from services.document_generator import DocumentGenerator
from services.log_manager import LogManager

# Initialisation des services (sera fait dans les routes si nécessaire)
# Pour éviter les erreurs si les clés API ne sont pas configurées au démarrage


def allowed_file(filename):
    """Vérifie si le fichier a une extension autorisée"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/')
def index():
    """Page d'accueil avec formulaire d'upload"""
    return render_template('index.html')


@app.route('/health')
def health():
    """Route de santé pour vérifier que l'application fonctionne"""
    return jsonify({
        'status': 'ok',
        'message': 'Application Aodio is running'
    }), 200


@app.route('/files/<session_id>/<filename>', methods=['GET', 'HEAD', 'OPTIONS'])
def serve_file(session_id, filename):
    """
    Route pour servir les fichiers audio temporairement
    Permet à RunPod de télécharger les fichiers via URL
    """
    # Gérer les requêtes OPTIONS pour CORS
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response
    
    try:
        # Sécuriser le nom de fichier pour éviter les path traversal
        safe_filename = secure_filename(filename)
        safe_session_id = secure_filename(session_id)
        
        if safe_filename != filename or safe_session_id != session_id:
            logger.warning(f"Tentative d'accès non sécurisé: session_id={session_id}, filename={filename}")
            return jsonify({'error': 'Nom de fichier ou session invalide'}), 400
        
        file_path = Path(UPLOAD_FOLDER) / safe_session_id / safe_filename
        
        # Vérifier que le fichier existe
        if not file_path.exists():
            logger.warning(f"Fichier introuvable: {file_path}")
            return jsonify({'error': 'Fichier introuvable'}), 404
        
        # Vérifier que le fichier est bien dans le dossier uploads
        # Utiliser une vérification simple avec les chemins normalisés
        upload_folder_resolved = Path(UPLOAD_FOLDER).resolve()
        file_path_resolved = file_path.resolve()
        
        # Vérifier que le chemin du fichier commence par le chemin du dossier uploads
        # Utiliser str() pour éviter les problèmes de comparaison de Path
        if not str(file_path_resolved).startswith(str(upload_folder_resolved)):
            logger.warning(f"Tentative d'accès hors du dossier uploads: {file_path_resolved} (uploads: {upload_folder_resolved})")
            return jsonify({'error': 'Accès non autorisé'}), 403
        
        logger.info(f"Serving file: {file_path} (size: {file_path.stat().st_size} bytes)")
        
        # Servir le fichier avec les headers appropriés pour permettre le téléchargement
        response = send_file(
            file_path,
            as_attachment=False,
            mimetype='application/octet-stream'
        )
        
        # Ajouter des headers CORS si nécessaire (pour RunPod)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        
        return response
        
    except Exception as e:
        logger.error(f"Erreur lors du service du fichier {session_id}/{filename}: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/upload', methods=['POST'])
def upload_files():
    """Endpoint pour l'upload des fichiers audio et documents contextuels"""
    try:
        # Génération d'un ID de session unique
        session_id = str(uuid.uuid4())
        session['processing_id'] = session_id
        
        # Création du dossier de session
        session_folder = Path(UPLOAD_FOLDER) / session_id
        session_folder.mkdir(exist_ok=True)
        
        # Récupération des fichiers
        audio_file = request.files.get('audio_file')
        ordre_du_jour = request.files.get('ordre_du_jour')
        liste_participants = request.files.get('liste_participants')
        releves_votes = request.files.get('releves_votes')
        
        # Récupération des informations contextuelles
        president_seance = request.form.get('president_seance', '')
        date_seance = request.form.get('date_seance', '')
        
        if not audio_file or audio_file.filename == '':
            return jsonify({'error': 'Aucun fichier audio fourni'}), 400
        
        if not allowed_file(audio_file.filename):
            return jsonify({'error': 'Format de fichier audio non autorisé'}), 400
        
        # Sauvegarde du fichier audio
        audio_filename = secure_filename(audio_file.filename)
        audio_path = session_folder / audio_filename
        audio_file.save(audio_path)
        
        # Sauvegarde des documents contextuels
        context_files = {}
        if ordre_du_jour and ordre_du_jour.filename:
            context_files['ordre_du_jour'] = session_folder / secure_filename(ordre_du_jour.filename)
            ordre_du_jour.save(context_files['ordre_du_jour'])
        
        if liste_participants and liste_participants.filename:
            context_files['liste_participants'] = session_folder / secure_filename(liste_participants.filename)
            liste_participants.save(context_files['liste_participants'])
        
        if releves_votes and releves_votes.filename:
            context_files['releves_votes'] = session_folder / secure_filename(releves_votes.filename)
            releves_votes.save(context_files['releves_votes'])
        
        # Sauvegarde des métadonnées initiales
        metadata = {
            'session_id': session_id,
            'date_upload': datetime.now().isoformat(),
            'president_seance': president_seance,
            'date_seance': date_seance,
            'audio_file': str(audio_path),
            'processed_audio': None,  # Sera rempli après traitement audio
            'context_files': {k: str(v) for k, v in context_files.items()},
            'status': 'uploaded'
        }
        
        metadata_path = session_folder / 'metadata.json'
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        # Démarrage du traitement audio asynchrone (pour fichiers longs jusqu'à 4h15)
        # Le traitement audio est maintenant asynchrone pour éviter de bloquer la requête HTTP
        from threading import Thread
        thread = Thread(target=process_audio_and_pipeline, args=(session_id, metadata, str(audio_path)))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'session_id': session_id,
            'message': 'Fichiers uploadés avec succès. Traitement audio en cours...'
        })
        
    except RequestEntityTooLarge:
        return jsonify({'error': 'Fichier trop volumineux (max 500 MB)'}), 413
    except Exception as e:
        logger.error(f"Erreur lors de l'upload: {str(e)}", exc_info=True)
        return jsonify({'error': f'Erreur lors de l\'upload: {str(e)}'}), 500


def process_audio_and_pipeline(session_id, metadata, audio_path):
    """
    Traite l'audio puis lance le pipeline complet
    Cette fonction est exécutée de manière asynchrone pour éviter de bloquer la requête HTTP
    """
    try:
        # Initialisation du service audio
        audio_processor = AudioProcessor()
        
        # Traitement de l'audio (normalisation et compression)
        logger.info(f"Début du traitement audio pour la session {session_id}")
        processed_audio_path = audio_processor.process_audio(
            audio_path,
            str(Path(UPLOAD_FOLDER) / session_id / 'audio_processed.wav')
        )
        
        # Mise à jour des métadonnées avec le chemin du fichier traité
        metadata['processed_audio'] = processed_audio_path
        metadata['status'] = 'audio_processed'
        metadata_path = Path(UPLOAD_FOLDER) / session_id / 'metadata.json'
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Traitement audio terminé pour la session {session_id}, démarrage du pipeline...")
        
        # Maintenant on peut lancer le pipeline complet
        process_audio_pipeline(session_id, metadata)
        
    except Exception as e:
        logger.error(f"Erreur lors du traitement audio pour {session_id}: {str(e)}", exc_info=True)
        # Mettre à jour le statut en cas d'erreur
        try:
            log_manager = LogManager(LOGS_FOLDER)
            log_manager.log_status(session_id, 'error', f'Erreur lors du traitement audio: {str(e)}')
        except:
            pass


def process_audio_pipeline(session_id, metadata):
    """Pipeline complet de traitement audio"""
    # Initialisation des services
    log_manager = LogManager(LOGS_FOLDER)
    
    # Déterminer l'URL de base de l'application
    # Railway fournit RAILWAY_PUBLIC_DOMAIN, sinon utiliser request.host_url
    app_base_url = os.getenv('RAILWAY_PUBLIC_DOMAIN')
    if app_base_url:
        # Ajouter le protocole si absent
        if not app_base_url.startswith('http'):
            app_base_url = f"https://{app_base_url}"
    else:
        # Fallback pour développement local
        app_base_url = os.getenv('APP_BASE_URL', 'http://localhost:5000')
    
    # Vérification des clés API avant initialisation
    if not app.config.get('RUNPOD_API_KEY'):
        raise ValueError("RUNPOD_API_KEY n'est pas configurée dans les variables d'environnement")
    if not app.config.get('RUNPOD_ENDPOINT_ID'):
        raise ValueError("RUNPOD_ENDPOINT_ID n'est pas configurée dans les variables d'environnement")
    
    logger.info(f"Initialisation RunPod avec Endpoint ID: {app.config['RUNPOD_ENDPOINT_ID']}")
    
    # RunPod uniquement pour Pyannote (diarisation)
    runpod_worker = RunPodWorker(
        api_key=app.config['RUNPOD_API_KEY'],
        endpoint_id=app.config['RUNPOD_ENDPOINT_ID'],
        base_url=app_base_url
    )
    
    # API Mistral AI directement pour Voxtral (transcription)
    mistral_client = MistralVoxtralClient(api_key=app.config.get('MISTRAL_API_KEY'))
    
    llm_processor = LLMProcessor(api_key=app.config['ANTHROPIC_API_KEY'])
    document_generator = DocumentGenerator()
    
    try:
        log_manager.log_status(session_id, 'processing', 'Démarrage du traitement')
        
        # 1. Diarisation avec Pyannote (via RunPod)
        log_manager.log_status(session_id, 'diarization', 'Démarrage de la diarisation')
        diarization_result = runpod_worker.diarize_audio(metadata['processed_audio'])
        log_manager.log_status(session_id, 'diarization', 'Diarisation terminée', diarization_result)
        
        # 2. Transcription avec Voxtral (directement via API Mistral AI)
        log_manager.log_status(session_id, 'transcription', 'Démarrage de la transcription')
        diarization_segments = diarization_result.get('segments', [])
        transcription_result = mistral_client.transcribe_audio(
            audio_path=metadata['processed_audio'],
            diarization_segments=diarization_segments,
            language="fr"
        )
        log_manager.log_status(session_id, 'transcription', 'Transcription terminée', transcription_result)
        
        # 3. Traitement LLM
        log_manager.log_status(session_id, 'llm_processing', 'Démarrage du traitement LLM')
        
        # Mapping des locuteurs
        speaker_mapping = llm_processor.map_speakers(
            transcription_result,
            metadata.get('context_files', {}).get('liste_participants'),
            metadata.get('president_seance')
        )
        log_manager.log_status(session_id, 'llm_processing', 'Mapping des locuteurs terminé', speaker_mapping)
        
        # Génération du pré-compte rendu
        pre_cr = llm_processor.generate_pre_cr(
            transcription_result,
            speaker_mapping,
            metadata.get('president_seance')
        )
        log_manager.log_status(session_id, 'llm_processing', 'Pré-compte rendu généré')
        
        # Extraction des décisions
        decisions = llm_processor.extract_decisions(
            transcription_result,
            metadata.get('context_files', {}).get('releves_votes')
        )
        log_manager.log_status(session_id, 'llm_processing', 'Décisions extraites', decisions)
        
        # 4. Génération des documents
        log_manager.log_status(session_id, 'document_generation', 'Génération des documents')
        date_seance = metadata.get('date_seance', datetime.now().strftime('%Y-%m-%d'))
        
        documents = document_generator.generate_all_documents(
            session_id=session_id,
            transcription=transcription_result,
            speaker_mapping=speaker_mapping,
            pre_cr=pre_cr,
            decisions=decisions,
            date_seance=date_seance,
            output_folder=PROCESSED_FOLDER
        )
        
        log_manager.log_status(session_id, 'completed', 'Traitement terminé avec succès', documents)
        
        # Mise à jour des métadonnées
        metadata['status'] = 'completed'
        metadata['documents'] = documents
        metadata_path = Path(UPLOAD_FOLDER) / session_id / 'metadata.json'
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
            
    except Exception as e:
        logger.error(f"Erreur dans le pipeline pour {session_id}: {str(e)}", exc_info=True)
        log_manager.log_status(session_id, 'error', f'Erreur: {str(e)}')


@app.route('/status/<session_id>')
def get_status(session_id):
    """Récupère le statut du traitement"""
    try:
        log_manager = LogManager(LOGS_FOLDER)
        status = log_manager.get_status(session_id)
        return jsonify(status)
    except Exception as e:
        logger.error(f"Erreur lors de la récupération du statut: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/download/<session_id>/<document_type>')
def download_document(session_id, document_type):
    """Télécharge un document généré"""
    try:
        metadata_path = Path(UPLOAD_FOLDER) / session_id / 'metadata.json'
        if not metadata_path.exists():
            return jsonify({'error': 'Session introuvable'}), 404
        
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        if metadata.get('status') != 'completed':
            return jsonify({'error': 'Traitement non terminé'}), 400
        
        documents = metadata.get('documents', {})
        file_path = documents.get(document_type)
        
        if not file_path or not Path(file_path).exists():
            return jsonify({'error': 'Document introuvable'}), 404
        
        return send_file(file_path, as_attachment=True)
        
    except Exception as e:
        logger.error(f"Erreur lors du téléchargement: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/history')
def history():
    """Page d'historique des traitements"""
    try:
        log_manager = LogManager(LOGS_FOLDER)
        history_data = log_manager.get_history()
        return render_template('history.html', history=history_data)
    except Exception as e:
        logger.error(f"Erreur lors de la récupération de l'historique: {str(e)}")
        return render_template('history.html', history=[], error=str(e))


@app.route('/confidentialite')
def confidentialite():
    """Page de déclaration de confidentialité"""
    return render_template('confidentialite.html')


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

