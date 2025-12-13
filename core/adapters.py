"""
Adaptateurs pour faire correspondre les services existants aux interfaces
"""
from typing import Dict, List, Any, Optional
from core.interfaces import (
    AudioProcessingService,
    DiarizationService,
    TranscriptionService,
    LLMSpeakerMappingService,
    DocumentGenerationService,
    LogManagementService
)


class AudioProcessorAdapter(AudioProcessingService):
    """Adaptateur pour le service de traitement audio existant"""
    
    def __init__(self, audio_processor_instance):
        self.audio_processor = audio_processor_instance
    
    def process_audio(self, input_path: str, output_path: str, enable_enhancement: bool = True) -> str:
        """Traite un fichier audio"""
        return self.audio_processor.process_audio(input_path, output_path, enable_enhancement)


class RunPodWorkerAdapter(DiarizationService):
    """Adaptateur pour le service de diarisation RunPod"""
    
    def __init__(self, runpod_worker_instance):
        self.runpod_worker = runpod_worker_instance
    
    def diarize_audio(self, audio_path: str) -> Dict[str, Any]:
        """Effectue la diarisation d'un fichier audio"""
        return self.runpod_worker.diarize_audio(audio_path)


class MistralVoxtralClientAdapter(TranscriptionService):
    """Adaptateur pour le service de transcription Mistral Voxtral"""
    
    def __init__(self, mistral_client_instance):
        self.mistral_client = mistral_client_instance
    
    def transcribe_audio(self, audio_path: str, language: str = "fr") -> Dict[str, Any]:
        """Transcrit un fichier audio"""
        # Note: La méthode originale transcribe_audio prend aussi diarization_segments
        # Pour l'instant, nous utilisons transcribe_file_full qui ne nécessite pas de diarization
        return self.mistral_client.transcribe_file_full(audio_path, language)
    
    def transcribe_file_full(self, audio_path: str, language: str = "fr") -> Dict[str, Any]:
        """Transcrit un fichier audio complet"""
        return self.mistral_client.transcribe_file_full(audio_path, language)


class MistralProcessorAdapter(LLMSpeakerMappingService):
    """Adaptateur pour le service de mapping des locuteurs Mistral"""
    
    def __init__(self, mistral_processor_instance):
        self.mistral_processor = mistral_processor_instance
    
    def map_speakers(self, transcription_result: Dict[str, Any], 
                    liste_participants_path: Optional[str] = None,
                    president_seance: Optional[str] = None) -> Dict[str, str]:
        """Mappe les labels SPEAKER_XX vers les noms réels des locuteurs"""
        return self.mistral_processor.map_speakers(
            transcription_result, 
            liste_participants_path, 
            president_seance
        )
    
    def generate_pre_compte_rendu(self, transcription_text: str, speaker_mapping: Dict[str, str]) -> str:
        """Génère un pré-compte rendu"""
        return self.mistral_processor.generate_pre_compte_rendu(transcription_text, speaker_mapping)
    
    def extract_decisions(self, transcription_text: str, speaker_mapping: Dict[str, str]) -> List[str]:
        """Extrait les décisions"""
        return self.mistral_processor.extract_decisions(transcription_text, speaker_mapping)


class DocumentGeneratorAdapter(DocumentGenerationService):
    """Adaptateur pour le service de génération de documents"""
    
    def __init__(self, document_generator_instance):
        self.document_generator = document_generator_instance
    
    def generate_all_documents(self, session_id: str, transcription: Dict[str, Any],
                              speaker_mapping: Dict[str, str], pre_cr: str,
                              decisions: List[Dict[str, Any]], date_seance: str,
                              output_folder: str) -> Dict[str, str]:
        """Génère tous les documents pour une session"""
        return self.document_generator.generate_all_documents(
            session_id, transcription, speaker_mapping, pre_cr, decisions, date_seance, output_folder
        )


class LogManagerAdapter(LogManagementService):
    """Adaptateur pour le service de gestion des logs"""
    
    def __init__(self, log_manager_instance):
        self.log_manager = log_manager_instance
    
    def log_status(self, session_id: str, stage: str, message: str, data: Any = None):
        """Enregistre un statut de traitement"""
        return self.log_manager.log_status(session_id, stage, message, data)
    
    def get_status(self, session_id: str) -> Dict[str, Any]:
        """Récupère le statut d'un traitement"""
        return self.log_manager.get_status(session_id)
    
    def get_history(self) -> List[Dict[str, Any]]:
        """Récupère l'historique des traitements"""
        return self.log_manager.get_history()