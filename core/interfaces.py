"""
Interfaces pour les services
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional


class AudioProcessingService(ABC):
    """Interface pour le service de traitement audio"""
    
    @abstractmethod
    def process_audio(self, input_path: str, output_path: str, enable_enhancement: bool = True) -> str:
        """Traite un fichier audio"""
        pass


class DiarizationService(ABC):
    """Interface pour le service de diarisation"""
    
    @abstractmethod
    def diarize_audio(self, audio_path: str) -> Dict[str, Any]:
        """Effectue la diarisation d'un fichier audio"""
        pass


class TranscriptionService(ABC):
    """Interface pour le service de transcription"""
    
    @abstractmethod
    def transcribe_audio(self, audio_path: str, language: str = "fr") -> Dict[str, Any]:
        """Transcrit un fichier audio"""
        pass
    
    @abstractmethod
    def transcribe_file_full(self, audio_path: str, language: str = "fr") -> Dict[str, Any]:
        """Transcrit un fichier audio complet"""
        pass


class UnifiedTranscriptionService(DiarizationService, TranscriptionService):
    """
    Interface combinant diarisation et transcription en un seul service.
    Utilisé par Voxtral Mini Transcribe V2 avec diarize=true.
    """


class LLMSpeakerMappingService(ABC):
    """Interface pour le service de mapping des locuteurs avec LLM"""
    
    @abstractmethod
    def map_speakers(self, transcription_result: Dict[str, Any], 
                    liste_participants_path: Optional[str] = None,
                    president_seance: Optional[str] = None) -> Dict[str, str]:
        """Mappe les labels SPEAKER_XX vers les noms réels des locuteurs"""
        pass


class DocumentGenerationService(ABC):
    """Interface pour le service de génération de documents"""
    
    @abstractmethod
    def generate_all_documents(self, session_id: str, transcription: Dict[str, Any],
                              speaker_mapping: Dict[str, str], pre_cr: str,
                              decisions: List[Dict[str, Any]], date_seance: str,
                              output_folder: str) -> Dict[str, str]:
        """Génère tous les documents pour une session"""
        pass


class LogManagementService(ABC):
    """Interface pour le service de gestion des logs"""
    
    @abstractmethod
    def log_status(self, session_id: str, stage: str, message: str, data: Any = None):
        """Enregistre un statut de traitement"""
        pass
    
    @abstractmethod
    def get_status(self, session_id: str) -> Dict[str, Any]:
        """Récupère le statut d'un traitement"""
        pass
    
    @abstractmethod
    def get_history(self) -> List[Dict[str, Any]]:
        """Récupère l'historique des traitements"""
        pass
