"""
Service de gestion des logs et de l'historique des traitements
"""
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class LogManager:
    """Gère les logs et l'historique des traitements"""
    
    def __init__(self, logs_folder: str):
        self.logs_folder = Path(logs_folder)
        self.logs_folder.mkdir(exist_ok=True)
        self.history_file = self.logs_folder / 'history.json'
        self._init_history_file()
    
    def _init_history_file(self):
        """Initialise le fichier d'historique s'il n'existe pas"""
        if not self.history_file.exists():
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=2)
    
    def log_status(self, session_id: str, stage: str, message: str, data: Any = None):
        """
        Enregistre un statut de traitement
        
        Args:
            session_id: ID de la session
            stage: Étape du traitement (uploaded, diarization, transcription, etc.)
            message: Message de statut
            data: Données supplémentaires optionnelles
        """
        try:
            # Lecture de l'historique
            with open(self.history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
            
            # Recherche de l'entrée existante
            entry = None
            for item in history:
                if item.get('session_id') == session_id:
                    entry = item
                    break
            
            # Création d'une nouvelle entrée si nécessaire
            if not entry:
                entry = {
                    'session_id': session_id,
                    'created_at': datetime.now().isoformat(),
                    'status': 'processing',
                    'stages': []
                }
                history.append(entry)
            
            # Ajout du nouveau statut
            status_entry = {
                'stage': stage,
                'message': message,
                'timestamp': datetime.now().isoformat(),
                'data': data if data else None
            }
            entry['stages'].append(status_entry)
            entry['status'] = stage
            entry['updated_at'] = datetime.now().isoformat()
            
            # Sauvegarde
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
            
            logger.info(f"[{session_id}] {stage}: {message}")
            
        except Exception as e:
            logger.error(f"Erreur lors de l'enregistrement du statut: {str(e)}", exc_info=True)
    
    def get_status(self, session_id: str) -> Dict[str, Any]:
        """
        Récupère le statut d'une session
        
        Args:
            session_id: ID de la session
            
        Returns:
            dict: Statut de la session
        """
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
            
            for entry in history:
                if entry.get('session_id') == session_id:
                    return entry
            
            return {
                'session_id': session_id,
                'status': 'not_found',
                'message': 'Session introuvable'
            }
            
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du statut: {str(e)}")
            return {
                'session_id': session_id,
                'status': 'error',
                'message': str(e)
            }
    
    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Récupère l'historique des traitements
        
        Args:
            limit: Nombre maximum d'entrées à retourner
            
        Returns:
            list: Liste des entrées d'historique
        """
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
            
            # Tri par date de création (plus récent en premier)
            history.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            
            return history[:limit]
            
        except Exception as e:
            logger.error(f"Erreur lors de la récupération de l'historique: {str(e)}")
            return []

