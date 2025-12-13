"""
Routes principales de l'application Flask
"""
import os
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from flask import Flask, render_template, request, jsonify, send_file, session
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
import logging
from threading import Thread

from services.audio_processor import AudioProcessor
from services.runpod_worker import RunPodWorker
from services.mistral_voxtral import MistralVoxtralClient
from services.mistral_processor import MistralProcessor
from services.document_generator import DocumentGenerator
from services.log_manager import LogManager
from orchestrator.pipeline_orchestrator import PipelineOrchestrator, AudioPipelineOrchestrator

# Configuration
UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', 'uploads')
PROCESSED_FOLDER = os.getenv('PROCESSED_FOLDER', 'processed')
LOGS_FOLDER = os.getenv('LOGS_FOLDER', 'logs')
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB
ALLOWED_EXTENSIONS = {'wav', 'mp3', 'm4a', 'flac', 'ogg', 'webm'}

logger = logging.getLogger(__name__)


def create_app():
    """Crée et configure l'application Flask"""
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE
    app.config['PROCESSED_FOLDER'] = PROCESSED_FOLDER
    app.config['LOGS_FOLDER'] = LOGS_FOLDER
    
    # Configuration des APIs
    app.config['RUNPOD_API_KEY'] = os.getenv('RUNPOD_API_KEY')
    app.config['RUNPOD_ENDPOINT_ID'] = os.getenv('RUNPOD_ENDPOINT_ID')
    app.config['MISTRAL_API_KEY'] = os.getenv('MISTRAL_API_KEY')
    app.config['MISTRAL_ENDPOINT'] = os.getenv('MISTRAL_ENDPOINT', 'https://api.mistral.ai/v1')
    
    # Initialisation des services
    audio_processor = AudioProcessor()
    log_manager = LogManager(LOGS_FOLDER)
    
    # Déterminer l'URL de base de l'application
    app_base_url = os.getenv('RAILWAY_PUBLIC_DOMAIN')
    if app_base_url:
        if not app_base_url.startswith('http'):
            app_base_url = f"https://{app_base_url}"
    else:
        app_base_url = os.getenv('APP_BASE_URL', 'http://localhost:5000')
    
    # Initialiser les services RunPod et Mistral
    runpod_worker = None
    mistral_client = None
    mistral_processor = None
    
    if app.config.get('RUNPOD_API_KEY') and app.config.get('RUNPOD_ENDPOINT_ID'):
        runpod_worker = RunPodWorker(
            api_key=app.config['RUNPOD_API_KEY'],
            endpoint_id=app.config['RUNPOD_ENDPOINT_ID'],
            base_url=app_base_url
        )
    
    if app.config.get('MISTRAL_API_KEY'):
        mistral_client = MistralVoxtralClient(api_key=app.config['MISTRAL_API_KEY'])
        mistral_processor = MistralProcessor(api_key=app.config['MISTRAL_API_KEY'])
    
    document_generator = DocumentGenerator()
    
    # Initialiser les orchestrateurs
    audio_orchestrator = AudioPipelineOrchestrator(audio_processor, log_manager)
    
    # Vérifier que tous les services nécessaires sont disponibles
    if not all([runpod_worker, mistral_client, mistral_processor]):
        missing_services = []
        if not runpod_worker:
            missing_services.append("RunPod")
        if not mistral_client:
            missing_services.append("Mistral Voxtral")
        if not mistral_processor:
            missing_services.append("Mistral Processor")
        
        logger.warning(f"Services manquants: {', '.join(missing_services)}. Certaines fonctionnalités seront limitées.")
    else:
        pipeline_orchestrator = PipelineOrchestrator(
            audio_processor=audio_processor,
            diarization_service=runpod_worker,
            transcription_service=mistral_client,
            llm_speaker_mapper=mistral_processor,
            document_generator=document_generator,
            log_manager=log_manager,
            app_base_url=app_base_url
        )
    
    # Handler pour les fichiers trop volumineux
    @app.errorhandler(RequestEntityTooLarge)
    def handle_file_too_large(error):
        """Gère l'erreur quand un fichier dépasse la taille maximale autorisée"""
        max_mb = MAX_FILE_SIZE / (1024 * 1024)
        logger.warning(f"Tentative d'upload d'un fichier trop volumineux (limite: {max_mb:.0f} MB)")
        return jsonify({
            'error': f'Fichier trop volumineux. La taille maximale autorisée est de {max_mb:.0f} MB'
        }), 413
    
    def allowed_file(filename):
        """Vérifie si le fichier a une extension autorisée"""
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
    
    def get_file_size(file_storage) -> int:
        """
        Obtient la taille réelle d'un fichier uploadé sans le charger entièrement en mémoire
        """
        current_position = file_storage.tell()
        file_storage.seek(0, os.SEEK_END)
        size = file_storage.tell()
        file_storage.seek(current_position)
        return size
    
    def validate_audio_file(file_storage, filename: str, max_size: int = MAX_FILE_SIZE) -> tuple:
        """
        Valide un fichier audio uploadé
        """
        if not file_storage or not filename:
            return False, "Aucun fichier fourni"
        
        if filename == '':
            return False, "Nom de fichier vide"
        
        if not allowed_file(filename):
            allowed_ext_str = ', '.join(sorted(ALLOWED_EXTENSIONS))
            return False, f"Extension non autorisée. Extensions acceptées: {allowed_ext_str}"
        
        file_size = get_file_size(file_storage)
        if file_size == 0:
            return False, "Le fichier est vide"
        
        if file_size > max_size:
            max_mb = max_size / (1024 * 1024)
            file_mb = file_size / (1024 * 1024)
            return False, f"Fichier trop volumineux ({file_mb:.1f} MB). Maximum autorisé: {max_mb:.0f} MB"
        
        # Vérification des magic bytes
        magic_signatures = {
            b'RIFF': 'wav',           # WAV
            b'ID3': 'mp3',            # MP3 avec tag ID3
            b'\xff\xfb': 'mp3',       # MP3 sans tag ID3
            b'\xff\xfa': 'mp3',       # MP3 sans tag ID3
            b'\xff\xf3': 'mp3',       # MP3 sans tag ID3
            b'\xff\xf2': 'mp3',       # MP3 sans tag ID3
            b'fLaC': 'flac',          # FLAC
            b'OggS': 'ogg',           # OGG/Vorbis
            b'\x1aE\xdf\xa3': 'webm', # WebM
            b'\x00\x00\x00': 'm4a',   # M4A (partiel, ftyp box)
        }
        
        file_storage.seek(0)
        header = file_storage.read(12)
        file_storage.seek(0)
        
        if len(header) < 4:
            return False, "Fichier trop petit pour être un fichier audio valide"
        
        is_valid_audio = False
        
        if len(header) >= 8 and header[4:8] == b'ftyp':
            is_valid_audio = True
        else:
            for signature in magic_signatures.keys():
                if header.startswith(signature):
                    is_valid_audio = True
                    break
        
        if not is_valid_audio:
            return False, "Le contenu du fichier ne correspond pas à un format audio reconnu"
        
        return True, None
    
    @app.route('/')
    def index():
        """Page d'accueil avec formulaire d'upload"""
        try:
            logger.info("Tentative de rendu du template index.html")
            logger.info(f"Dossier des templates: {app.template_folder}")
            logger.info(f"Fichiers dans templates: {os.listdir(app.template_folder) if os.path.exists(app.template_folder) else 'Dossier introuvable'}")
            
            # Vérifier les variables d'environnement critiques
            missing_env_vars = []
            required_vars = ['SECRET_KEY', 'UPLOAD_FOLDER', 'PROCESSED_FOLDER']
            for var in required_vars:
                if not os.getenv(var):
                    missing_env_vars.append(var)
            
            if missing_env_vars:
                logger.warning(f"Variables d'environnement manquantes: {', '.join(missing_env_vars)}")
            
            # Vérifier que les dossiers nécessaires existent
            folders_to_check = [UPLOAD_FOLDER, PROCESSED_FOLDER, LOGS_FOLDER]
            for folder in folders_to_check:
                if not os.path.exists(folder):
                    logger.error(f"Dossier manquant: {folder}")
                else:
                    logger.info(f"Dossier vérifié: {folder}")
            
            return render_template('index.html')
            
        except Exception as e:
            logger.error(f"Erreur critique lors du rendu du template index.html: {str(e)}", exc_info=True)
            logger.error(f"Type d'erreur: {type(e).__name__}")
            logger.error(f"Dossier de travail actuel: {os.getcwd()}")
            logger.error(f"Contenu du dossier actuel: {os.listdir()}")
            return f"Erreur interne du serveur: {str(e)}", 500
    
    @app.route('/health')
    def health():
        """Route de santé pour vérifier que l'application fonctionne"""
        try:
            health_info = {
                'status': 'ok',
                'message': 'Application Aodio is running',
                'timestamp': datetime.now().isoformat(),
                'environment': {
                    'FLASK_ENV': os.getenv('FLASK_ENV', 'production'),
                    'RAILWAY_ENVIRONMENT': os.getenv('RAILWAY_ENVIRONMENT', 'local'),
                    'PYTHON_VERSION': f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
                },
                'folders': {
                    'upload_folder': UPLOAD_FOLDER,
                    'upload_exists': os.path.exists(UPLOAD_FOLDER),
                    'processed_folder': PROCESSED_FOLDER,
                    'processed_exists': os.path.exists(PROCESSED_FOLDER),
                    'logs_folder': LOGS_FOLDER,
                    'logs_exists': os.path.exists(LOGS_FOLDER),
                    'template_folder': app.template_folder,
                    'template_exists': os.path.exists(app.template_folder)
                },
                'services': {
                    'runpod_available': bool(app.config.get('RUNPOD_API_KEY')),
                    'mistral_available': bool(app.config.get('MISTRAL_API_KEY')),
                    'audio_processor': 'initialized',
                    'log_manager': 'initialized'
                }
            }
            
            logger.info("Health check successful")
            return jsonify(health_info), 200
            
        except Exception as e:
            logger.error(f"Health check failed: {str(e)}", exc_info=True)
            return jsonify({
                'status': 'error',
                'message': f'Health check failed: {str(e)}',
                'error_type': type(e).__name__
            }), 500
    
    @app.route('/files/<session_id>/<filename>', methods=['GET', 'HEAD', 'OPTIONS'])
    def serve_file(session_id, filename):
        """
        Route pour servir les fichiers audio temporairement
        Permet à RunPod de télécharger les fichiers via URL
        """
        logger.info(f"Requête reçue pour /files/{session_id}/{filename} - Method: {request.method}, User-Agent: {request.headers.get('User-Agent', 'N/A')}, Remote: {request.remote_addr}")
        
        if request.method == 'OPTIONS':
            response = jsonify({'status': 'ok'})
            allowed_origins = os.getenv('ALLOWED_ORIGINS', '').split(',')
            origin = request.headers.get('Origin')
            if origin and origin.strip() in [o.strip() for o in allowed_origins if o.strip()]:
                response.headers['Access-Control-Allow-Origin'] = origin
            else:
                if not allowed_origins or not any(o.strip() for o in allowed_origins):
                    logger.warning("ALLOWED_ORIGINS non configuré, CORS ouvert à tous (non recommandé en production)")
                response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
            return response
        
        try:
            safe_filename = secure_filename(filename)
            safe_session_id = secure_filename(session_id)
            
            if safe_filename != filename or safe_session_id != session_id:
                logger.warning(f"secure_filename a modifié les valeurs: session_id={session_id}->{safe_session_id}, filename={filename}->{safe_filename}")
                return jsonify({'error': 'Nom de fichier ou session invalide'}), 400
            
            file_path = Path(UPLOAD_FOLDER) / safe_session_id / safe_filename
            
            if not file_path.exists():
                logger.warning(f"Fichier introuvable: {file_path}")
                return jsonify({'error': 'Fichier introuvable'}), 404
            
            upload_folder_resolved = Path(UPLOAD_FOLDER).resolve()
            file_path_resolved = file_path.resolve()
            
            if not str(file_path_resolved).startswith(str(upload_folder_resolved)):
                logger.warning(f"Tentative d'accès hors du dossier uploads: {file_path_resolved} (uploads: {upload_folder_resolved})")
                return jsonify({'error': 'Accès non autorisé'}), 403
            
            logger.info(f"Serving file: {file_path} (size: {file_path.stat().st_size} bytes)")
            
            response = send_file(
                file_path,
                as_attachment=False,
                mimetype='application/octet-stream'
            )
            
            allowed_origins = os.getenv('ALLOWED_ORIGINS', '').split(',')
            origin = request.headers.get('Origin')
            if origin and origin.strip() in [o.strip() for o in allowed_origins if o.strip()]:
                response.headers['Access-Control-Allow-Origin'] = origin
            else:
                if not allowed_origins or not any(o.strip() for o in allowed_origins):
                    logger.warning("ALLOWED_ORIGINS non configuré, CORS ouvert à tous (non recommandé en production)")
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
            session_id = str(uuid.uuid4())
            session['processing_id'] = session_id
            
            session_folder = Path(UPLOAD_FOLDER) / session_id
            session_folder.mkdir(exist_ok=True)
            
            audio_file = request.files.get('audio_file')
            ordre_du_jour = request.files.get('ordre_du_jour')
            liste_participants = request.files.get('liste_participants')
            releves_votes = request.files.get('releves_votes')
            
            president_seance = request.form.get('president_seance', '')
            date_seance = request.form.get('date_seance', '')
            
            is_valid, error_message = validate_audio_file(audio_file, audio_file.filename if audio_file else '')
            if not is_valid:
                import shutil
                if session_folder.exists():
                    shutil.rmtree(session_folder)
                return jsonify({'error': error_message}), 400
            
            audio_filename = secure_filename(audio_file.filename)
            audio_path = session_folder / audio_filename
            audio_file.save(audio_path)
            
            logger.info(f"[{session_id}] Fichier audio validé et sauvegardé: {audio_filename} ({get_file_size(audio_file) / (1024*1024):.1f} MB)")
            
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
            
            metadata = {
                'session_id': session_id,
                'date_upload': datetime.now().isoformat(),
                'president_seance': president_seance,
                'date_seance': date_seance,
                'audio_file': str(audio_path),
                'processed_audio': None,
                'context_files': {k: str(v) for k, v in context_files.items()},
                'status': 'uploaded'
            }
            
            metadata_path = session_folder / 'metadata.json'
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            
            # Démarrage du traitement audio asynchrone
            thread = Thread(target=process_audio_and_pipeline_wrapper, args=(session_id, metadata, str(audio_path)))
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
    
    def process_audio_and_pipeline_wrapper(session_id: str, metadata: Dict[str, Any], audio_path: str):
        """Wrapper pour appeler l'orchestrateur audio"""
        try:
            audio_orchestrator.process_audio_and_pipeline(session_id, metadata, audio_path)
            
            # Si tous les services sont disponibles, lancer le pipeline complet
            if 'pipeline_orchestrator' in globals():
                pipeline_orchestrator.process_audio_pipeline(session_id, metadata)
            else:
                logger.warning("Pipeline complet non disponible - certains services manquants")
                log_manager.log_status(session_id, 'warning', 'Pipeline complet non disponible - certains services manquants')
                
        except Exception as e:
            logger.error(f"Erreur dans le wrapper pour {session_id}: {str(e)}", exc_info=True)
    
    @app.route('/status/<session_id>')
    def get_status(session_id):
        """Récupère le statut du traitement"""
        try:
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
            history_data = log_manager.get_history()
            return render_template('history.html', history=history_data)
        except Exception as e:
            logger.error(f"Erreur lors de la récupération de l'historique: {str(e)}")
            return render_template('history.html', history=[], error=str(e))
    
    @app.route('/confidentialite')
    def confidentialite():
        """Page de déclaration de confidentialité"""
        return render_template('confidentialite.html')
    
    return app