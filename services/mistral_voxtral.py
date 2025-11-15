"""
Service pour appeler directement l'API Mistral AI (Voxtral) pour la transcription
Alternative au worker RunPod si vous préférez appeler directement Mistral AI
"""
import os
import logging
from typing import Dict, List, Any, Optional
from mistralai import Mistral

logger = logging.getLogger(__name__)


class MistralVoxtralClient:
    """Client pour appeler directement l'API Mistral AI (Voxtral)"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialise le client Mistral AI
        
        Args:
            api_key: Clé API Mistral AI (si None, lit depuis MISTRAL_API_KEY)
        """
        self.api_key = api_key or os.getenv('MISTRAL_API_KEY')
        if not self.api_key:
            raise ValueError("MISTRAL_API_KEY doit être fourni")
        
        self.client = Mistral(api_key=self.api_key)
        self.model = "voxtral-small-latest"
    
    def transcribe_audio(self, audio_path: str, 
                        diarization_segments: List[Dict[str, Any]],
                        language: str = "fr") -> Dict[str, Any]:
        """
        Transcrit un fichier audio avec Voxtral-small-latest
        
        Args:
            audio_path: Chemin du fichier audio local
            diarization_segments: Segments de diarisation pour mapper les speakers
            language: Langue de l'audio (défaut: "fr")
            
        Returns:
            dict: Transcription avec segments mappés aux speakers
        """
        try:
            logger.info(f"Transcription avec Voxtral-small-latest: {audio_path}")
            
            # Transcription avec timestamps de segments
            with open(audio_path, "rb") as f:
                transcription_response = self.client.audio.transcriptions.complete(
                    model=self.model,
                    file={
                        "content": f,
                        "file_name": os.path.basename(audio_path)
                    },
                    language=language,
                    temperature=0.0,  # Déterministe
                    timestamp_granularities=["segment"]  # Pour obtenir start/end
                )
            
            # Format de réponse Mistral AI:
            # {
            #     "text": "texte complet",
            #     "segments": [
            #         {"text": "...", "start": 0.0, "end": 5.2},
            #         ...
            #     ]
            # }
            
            mistral_segments = transcription_response.segments if hasattr(transcription_response, 'segments') else []
            
            # Mapping des segments Mistral avec les segments de diarisation
            transcriptions = []
            for diar_seg in diarization_segments:
                # Trouver le segment Mistral correspondant (par timestamp)
                matching_mistral = None
                for mistral_seg in mistral_segments:
                    mistral_start = getattr(mistral_seg, 'start', mistral_seg.get('start', 0))
                    mistral_end = getattr(mistral_seg, 'end', mistral_seg.get('end', float('inf')))
                    
                    if mistral_start <= diar_seg['start'] < mistral_end:
                        matching_mistral = mistral_seg
                        break
                
                mistral_text = ""
                if matching_mistral:
                    mistral_text = getattr(matching_mistral, 'text', matching_mistral.get('text', ''))
                
                transcriptions.append({
                    "start": diar_seg['start'],
                    "end": diar_seg['end'],
                    "speaker": diar_seg['speaker'],
                    "text": mistral_text
                })
            
            result = {
                "segments": transcriptions,
                "full_text": transcription_response.text if hasattr(transcription_response, 'text') else ""
            }
            
            logger.info(f"Transcription terminée: {len(transcriptions)} segments")
            return result
            
        except Exception as e:
            logger.error(f"Erreur lors de la transcription: {str(e)}", exc_info=True)
            raise
    
    def transcribe_audio_from_url(self, audio_url: str,
                                  diarization_segments: List[Dict[str, Any]],
                                  language: str = "fr") -> Dict[str, Any]:
        """
        Transcrit un fichier audio depuis une URL avec Voxtral-small-latest
        
        Args:
            audio_url: URL du fichier audio
            diarization_segments: Segments de diarisation pour mapper les speakers
            language: Langue de l'audio (défaut: "fr")
            
        Returns:
            dict: Transcription avec segments mappés aux speakers
        """
        try:
            logger.info(f"Transcription depuis URL avec Voxtral-small-latest: {audio_url}")
            
            # Transcription avec timestamps de segments
            transcription_response = self.client.audio.transcriptions.complete(
                model=self.model,
                file_url=audio_url,
                language=language,
                temperature=0.0,  # Déterministe
                timestamp_granularities=["segment"]  # Pour obtenir start/end
            )
            
            # Même logique de mapping que transcribe_audio
            mistral_segments = transcription_response.segments if hasattr(transcription_response, 'segments') else []
            
            transcriptions = []
            for diar_seg in diarization_segments:
                matching_mistral = None
                for mistral_seg in mistral_segments:
                    mistral_start = getattr(mistral_seg, 'start', mistral_seg.get('start', 0))
                    mistral_end = getattr(mistral_seg, 'end', mistral_seg.get('end', float('inf')))
                    
                    if mistral_start <= diar_seg['start'] < mistral_end:
                        matching_mistral = mistral_seg
                        break
                
                mistral_text = ""
                if matching_mistral:
                    mistral_text = getattr(matching_mistral, 'text', matching_mistral.get('text', ''))
                
                transcriptions.append({
                    "start": diar_seg['start'],
                    "end": diar_seg['end'],
                    "speaker": diar_seg['speaker'],
                    "text": mistral_text
                })
            
            result = {
                "segments": transcriptions,
                "full_text": transcription_response.text if hasattr(transcription_response, 'text') else ""
            }
            
            logger.info(f"Transcription terminée: {len(transcriptions)} segments")
            return result
            
        except Exception as e:
            logger.error(f"Erreur lors de la transcription: {str(e)}", exc_info=True)
            raise

