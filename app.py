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
UPLOAD_FOLDER = 'uploads'
PROCESSED_FOLDER = 'processed'
LOGS_FOLDER = 'logs'
ALLOWED_EXTENSIONS = {'wav', 'mp3', 'm4a', 'flac', 'ogg', 'webm'}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB

# Création des dossiers nécessaires
for folder in [UPLOAD_FOLDER, PROCESSED_FOLDER, LOGS_FOLDER]:
    Path(folder).mkdir(exist_ok=True)

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
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'{LOGS_FOLDER}/app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Import des modules
from services.audio_processor import AudioProcessor
from services.runpod_worker import RunPodWorker
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
        
        # Initialisation des services
        audio_processor = AudioProcessor()
        
        # Traitement de l'audio (normalisation et compression)
        logger.info(f"Début du traitement audio pour la session {session_id}")
        processed_audio_path = audio_processor.process_audio(
            str(audio_path),
            str(session_folder / 'audio_processed.wav')
        )
        
        # Sauvegarde des métadonnées
        metadata = {
            'session_id': session_id,
            'date_upload': datetime.now().isoformat(),
            'president_seance': president_seance,
            'date_seance': date_seance,
            'audio_file': str(audio_path),
            'processed_audio': processed_audio_path,
            'context_files': {k: str(v) for k, v in context_files.items()},
            'status': 'uploaded'
        }
        
        metadata_path = session_folder / 'metadata.json'
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        # Démarrage du traitement asynchrone
        # Note: En production, utiliser Celery ou un système de queue
        from threading import Thread
        thread = Thread(target=process_audio_pipeline, args=(session_id, metadata))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'session_id': session_id,
            'message': 'Fichiers uploadés avec succès. Traitement en cours...'
        })
        
    except RequestEntityTooLarge:
        return jsonify({'error': 'Fichier trop volumineux (max 500 MB)'}), 413
    except Exception as e:
        logger.error(f"Erreur lors de l'upload: {str(e)}", exc_info=True)
        return jsonify({'error': f'Erreur lors de l\'upload: {str(e)}'}), 500


def process_audio_pipeline(session_id, metadata):
    """Pipeline complet de traitement audio"""
    # Initialisation des services
    log_manager = LogManager(LOGS_FOLDER)
    runpod_worker = RunPodWorker(
        api_key=app.config['RUNPOD_API_KEY'],
        endpoint_id=app.config['RUNPOD_ENDPOINT_ID']
    )
    llm_processor = LLMProcessor(api_key=app.config['ANTHROPIC_API_KEY'])
    document_generator = DocumentGenerator()
    
    try:
        log_manager.log_status(session_id, 'processing', 'Démarrage du traitement')
        
        # 1. Diarisation avec Pyannote (via RunPod)
        log_manager.log_status(session_id, 'diarization', 'Démarrage de la diarisation')
        diarization_result = runpod_worker.diarize_audio(metadata['processed_audio'])
        log_manager.log_status(session_id, 'diarization', 'Diarisation terminée', diarization_result)
        
        # 2. Transcription avec Voxtral
        log_manager.log_status(session_id, 'transcription', 'Démarrage de la transcription')
        transcription_result = runpod_worker.transcribe_audio(
            metadata['processed_audio'],
            diarization_result
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

