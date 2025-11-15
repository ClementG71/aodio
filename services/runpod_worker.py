"""
Service pour interagir avec le worker RunPod
Diarisation Pyannote et transcription Voxtral
"""
import json
import logging
import requests
import time
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class RunPodWorker:
    """Gère les appels au worker RunPod pour diarisation et transcription"""
    
    def __init__(self, api_key: str, endpoint_id: str):
        self.api_key = api_key
        self.endpoint_id = endpoint_id
        self.base_url = f"https://api.runpod.io/v2/{endpoint_id}"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    def _upload_file(self, file_path: str) -> str:
        """
        Upload un fichier vers RunPod et retourne l'URL
        
        Args:
            file_path: Chemin local du fichier
            
        Returns:
            str: URL du fichier uploadé
        """
        # Note: Implémentation dépendante de votre configuration RunPod
        # Ici, on suppose que le fichier est accessible via une URL
        # En production, vous devrez uploader vers S3 ou un service similaire
        logger.warning("Upload de fichier non implémenté - à adapter selon votre infrastructure")
        return file_path
    
    def diarize_audio(self, audio_path: str) -> Dict[str, Any]:
        """
        Effectue la diarisation avec Pyannote 4.0.1
        
        Args:
            audio_path: Chemin du fichier audio
            
        Returns:
            dict: Résultat de la diarisation avec segments et speakers
        """
        try:
            logger.info(f"Démarrage de la diarisation pour: {audio_path}")
            
            # Upload du fichier (à adapter selon votre infrastructure)
            audio_url = self._upload_file(audio_path)
            
            # Préparation de la requête
            payload = {
                "input": {
                    "task": "diarization",
                    "audio_url": audio_url,
                    "model": "pyannote/speaker-diarization-3.1"
                }
            }
            
            # Appel à l'API RunPod
            response = requests.post(
                f"{self.base_url}/run",
                headers=self.headers,
                json=payload,
                timeout=300
            )
            response.raise_for_status()
            
            job_id = response.json().get('id')
            
            # Attente de la complétion
            result = self._wait_for_completion(job_id)
            
            # Format du résultat attendu:
            # {
            #     "segments": [
            #         {
            #             "start": 0.0,
            #             "end": 5.2,
            #             "speaker": "SPEAKER_00"
            #         },
            #         ...
            #     ]
            # }
            
            logger.info(f"Diarisation terminée: {len(result.get('segments', []))} segments")
            return result
            
        except Exception as e:
            logger.error(f"Erreur lors de la diarisation: {str(e)}", exc_info=True)
            raise
    
    def transcribe_audio(self, audio_path: str, diarization_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transcrit l'audio avec Voxtral-small-latest en respectant les segments de diarisation
        
        Args:
            audio_path: Chemin du fichier audio
            diarization_result: Résultat de la diarisation
            
        Returns:
            dict: Transcription avec segments et texte
        """
        try:
            logger.info(f"Démarrage de la transcription pour: {audio_path}")
            
            # Upload du fichier
            audio_url = self._upload_file(audio_path)
            
            segments = diarization_result.get('segments', [])
            
            # Traitement par segments pour éviter de surcharger l'API
            # Regroupement des segments pour optimiser les appels
            transcriptions = []
            max_tokens_per_call = 100000  # Limite à adapter selon Voxtral
            
            current_batch = []
            current_tokens = 0
            
            for segment in segments:
                segment_duration = segment['end'] - segment['start']
                # Estimation: ~100 tokens par seconde d'audio
                estimated_tokens = int(segment_duration * 100)
                
                if current_tokens + estimated_tokens > max_tokens_per_call and current_batch:
                    # Traiter le batch actuel
                    batch_transcription = self._transcribe_segment_batch(
                        audio_url, current_batch
                    )
                    transcriptions.extend(batch_transcription)
                    current_batch = []
                    current_tokens = 0
                
                current_batch.append(segment)
                current_tokens += estimated_tokens
            
            # Traiter le dernier batch
            if current_batch:
                batch_transcription = self._transcribe_segment_batch(
                    audio_url, current_batch
                )
                transcriptions.extend(batch_transcription)
            
            result = {
                "segments": transcriptions,
                "full_text": "\n".join([t.get('text', '') for t in transcriptions])
            }
            
            logger.info(f"Transcription terminée: {len(transcriptions)} segments")
            return result
            
        except Exception as e:
            logger.error(f"Erreur lors de la transcription: {str(e)}", exc_info=True)
            raise
    
    def _transcribe_segment_batch(self, audio_url: str, segments: List[Dict]) -> List[Dict]:
        """
        Transcrit un batch de segments avec Voxtral via Mistral AI API
        
        Note: Voxtral-small-latest est un modèle de Mistral AI accessible via:
        - Endpoint: https://api.mistral.ai/v1/audio/transcriptions
        - Modèle: voxtral-small-latest
        - Supporte timestamp_granularities=["segment"] pour obtenir les timestamps
        
        Args:
            audio_url: URL du fichier audio
            segments: Liste des segments de diarisation (pour référence)
            
        Returns:
            list: Liste des transcriptions avec texte et métadonnées
        """
        try:
            # Le worker RunPod doit appeler l'API Mistral AI avec:
            # - model: "voxtral-small-latest"
            # - file_url: URL du fichier audio
            # - timestamp_granularities: ["segment"] pour obtenir les timestamps
            # - language: "fr" (optionnel, améliore la précision)
            # - temperature: 0.0 (pour des résultats déterministes)
            
            payload = {
                "input": {
                    "task": "transcription",
                    "audio_url": audio_url,
                    "segments": segments,  # Segments de diarisation pour référence
                    "model": "voxtral-small-latest",  # Modèle Mistral AI
                    "api_endpoint": "https://api.mistral.ai/v1/audio/transcriptions",
                    "timestamp_granularities": ["segment"],  # Pour obtenir start/end
                    "language": "fr",  # Optionnel mais recommandé
                    "temperature": 0.0  # Déterministe
                }
            }
            
            response = requests.post(
                f"{self.base_url}/run",
                headers=self.headers,
                json=payload,
                timeout=600
            )
            response.raise_for_status()
            
            job_id = response.json().get('id')
            result = self._wait_for_completion(job_id)
            
            # Format de réponse attendu de Mistral AI:
            # {
            #     "text": "texte complet",
            #     "segments": [
            #         {"text": "...", "start": 0.0, "end": 5.2},
            #         ...
            #     ]
            # }
            # On doit mapper ces segments avec les speakers de la diarisation
            
            mistral_segments = result.get('segments', [])
            transcriptions = []
            
            # Mapping des segments Mistral avec les segments de diarisation
            for diar_seg in segments:
                # Trouver le segment Mistral correspondant (par timestamp)
                matching_mistral = None
                for mistral_seg in mistral_segments:
                    if (mistral_seg.get('start', 0) <= diar_seg['start'] < mistral_seg.get('end', float('inf'))):
                        matching_mistral = mistral_seg
                        break
                
                transcriptions.append({
                    "start": diar_seg['start'],
                    "end": diar_seg['end'],
                    "speaker": diar_seg['speaker'],
                    "text": matching_mistral.get('text', '') if matching_mistral else ''
                })
            
            return transcriptions
            
        except Exception as e:
            logger.error(f"Erreur lors de la transcription du batch: {str(e)}", exc_info=True)
            raise
    
    def _wait_for_completion(self, job_id: str, max_wait: int = 3600) -> Dict[str, Any]:
        """
        Attend la complétion d'un job RunPod
        
        Args:
            job_id: ID du job
            max_wait: Temps maximum d'attente en secondes
            
        Returns:
            dict: Résultat du job
        """
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            response = requests.get(
                f"{self.base_url}/status/{job_id}",
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            
            status = response.json()
            
            if status.get('status') == 'COMPLETED':
                return status.get('output', {})
            elif status.get('status') == 'FAILED':
                error = status.get('error', 'Erreur inconnue')
                raise Exception(f"Job échoué: {error}")
            
            time.sleep(5)  # Attente de 5 secondes avant le prochain check
        
        raise TimeoutError(f"Job {job_id} n'a pas terminé dans le délai imparti")

