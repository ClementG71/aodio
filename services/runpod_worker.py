"""
Service pour interagir avec le worker RunPod
Diarisation Pyannote et transcription Voxtral
"""
import json
import logging
import requests
import time
import os
from typing import Dict, List, Any

from services.circuit_breaker import runpod_breaker, CircuitBreakerOpen

logger = logging.getLogger(__name__)


class RunPodWorker:
    """Gère les appels au worker RunPod pour diarisation et transcription"""
    
    def __init__(self, api_key: str, endpoint_id: str, base_url: str = None):
        """
        Initialise le client RunPod
        
        Args:
            api_key: Clé API RunPod
            endpoint_id: ID de l'endpoint RunPod
            base_url: URL de base de l'application Flask (pour servir les fichiers)
        """
        self.api_key = api_key
        self.endpoint_id = endpoint_id
        # URL correcte selon la documentation RunPod : api.runpod.ai (pas .io)
        self.base_url = f"https://api.runpod.ai/v2/{endpoint_id}"
        
        # Déterminer l'URL de base de l'application
        # Priorité: base_url > DOKPLOY_PUBLIC_DOMAIN > RAILWAY_PUBLIC_DOMAIN > localhost
        if base_url:
            self.app_base_url = base_url
        elif os.getenv('DOKPLOY_PUBLIC_DOMAIN'):
            self.app_base_url = os.getenv('DOKPLOY_PUBLIC_DOMAIN')
        elif os.getenv('RAILWAY_PUBLIC_DOMAIN'):
            self.app_base_url = os.getenv('RAILWAY_PUBLIC_DOMAIN')
        else:
            self.app_base_url = 'http://localhost:5000'
        
        # S'assurer que l'URL ne se termine pas par /
        if self.app_base_url.endswith('/'):
            self.app_base_url = self.app_base_url[:-1]
        
        # S'assurer que l'URL commence par http ou https
        if not self.app_base_url.startswith(('http://', 'https://')):
            self.app_base_url = f'https://{self.app_base_url}'
        
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    def _sanitize_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Masque les données sensibles dans un payload pour les logs
        
        Args:
            payload: Payload à nettoyer
            
        Returns:
            dict: Payload avec données sensibles masquées
        """
        sensitive_keys = ['key', 'token', 'api_key', 'secret', 'password', 'authorization']
        
        def sanitize_value(obj):
            if isinstance(obj, dict):
                return {k: '***' if any(sk in k.lower() for sk in sensitive_keys) else sanitize_value(v)
                        for k, v in obj.items()}
            elif isinstance(obj, list):
                return [sanitize_value(item) for item in obj]
            elif isinstance(obj, str) and any(sk in obj.lower() for sk in ['bearer', 'token', 'key']):
                # Masquer les valeurs qui ressemblent à des tokens
                if len(obj) > 20 and any(c.isalnum() for c in obj):
                    return '***'
            return obj
        
        return sanitize_value(payload)
    
    def _upload_file(self, file_path: str) -> str:
        """
        Génère une URL accessible publiquement pour le fichier audio
        Le fichier sera servi via une route Flask
        
        Args:
            file_path: Chemin local du fichier (ex: uploads/session_id/audio_processed.wav)
            
        Returns:
            str: URL publique du fichier
        """
        try:
            # Extraire session_id et filename du chemin
            # Format attendu: uploads/session_id/filename
            path_parts = file_path.replace('\\', '/').split('/')
            
            if 'uploads' not in path_parts:
                raise ValueError(f"Chemin de fichier invalide: {file_path}")
            
            uploads_index = path_parts.index('uploads')
            if len(path_parts) < uploads_index + 3:
                raise ValueError(f"Chemin de fichier invalide: {file_path}")
            
            session_id = path_parts[uploads_index + 1]
            filename = path_parts[uploads_index + 2]
            
            # Construire l'URL publique
            file_url = f"{self.app_base_url}/files/{session_id}/{filename}"
            
            logger.info(f"URL générée pour le fichier: {file_url}")
            return file_url
            
        except Exception as e:
            logger.error(f"Erreur lors de la génération de l'URL: {str(e)}")
            raise
    
    def diarize_audio(self, audio_path: str, session_id: str = None) -> Dict[str, Any]:
        """
        Effectue la diarisation avec Pyannote 4.0.1
        
        Args:
            audio_path: Chemin du fichier audio
            session_id: ID de la session (optionnel, pour vérifier l'annulation)
            
        Returns:
            dict: Résultat de la diarisation avec segments et speakers, incluant job_id
        """
        try:
            logger.info(f"Démarrage de la diarisation pour: {audio_path}")
            logger.info(json.dumps({
                "session_id": session_id,
                "stage": "diarization",
                "event": "start_runpod",
                "message": "Envoi du job de diarisation à RunPod",
                "data": {"audio_path": audio_path, "endpoint_id": self.endpoint_id},
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }))
            
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
            # URL correcte selon la doc: https://api.runpod.ai/v2/{endpoint_id}/run
            api_url = f"{self.base_url}/run"
            logger.info(f"Appel API RunPod: {api_url}")
            logger.info(f"Endpoint ID utilisé: {self.endpoint_id}")
            # Masquer les données sensibles dans les logs
            safe_payload = self._sanitize_payload(payload)
            logger.debug(f"Payload: {json.dumps(safe_payload, indent=2)}")
            
            # Vérifier que l'API key est présente
            if not self.api_key:
                raise ValueError("RUNPOD_API_KEY n'est pas configurée")
            
            with runpod_breaker:
                response = requests.post(
                    api_url,
                    headers=self.headers,
                    json=payload,
                    timeout=120  # POST synchrone : on attend seulement l'acceptation du job (réponse rapide)
                )
            
            # Log de la réponse pour debug
            logger.info(f"Status code: {response.status_code}")
            logger.debug(f"Response headers: {dict(response.headers)}")
            logger.debug(f"Response: {response.text[:1000]}")
            
            if response.status_code == 404:
                error_msg = (
                    f"Endpoint non trouvé (404). "
                    f"Vérifiez que l'Endpoint ID '{self.endpoint_id}' est correct. "
                    f"URL appelée: {api_url}"
                )
                logger.error(error_msg)
                raise Exception(error_msg)
            
            if response.status_code == 401:
                error_msg = (
                    f"Authentification échouée (401). "
                    f"Vérifiez que votre RUNPOD_API_KEY est correcte et valide."
                )
                logger.error(error_msg)
                raise Exception(error_msg)
            
            response.raise_for_status()
            
            response_data = response.json()
            job_id = response_data.get('id')
            
            if not job_id:
                logger.error(f"Réponse inattendue de l'API: {response_data}")
                raise Exception(f"L'API n'a pas retourné d'ID de job. Réponse: {response_data}")
            
            logger.info(f"Job RunPod créé avec succès. Job ID: {job_id}")
            
            # Attente de la complétion avec vérification d'annulation
            result = self._wait_for_completion(job_id, session_id=session_id)
            
            # Ajouter le job_id au résultat pour référence
            if isinstance(result, dict):
                result['job_id'] = job_id
            
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
            
            # Le résultat contient directement la liste des segments ou un dict avec 'segments'
            segments = result if isinstance(result, list) else result.get('segments', [])
            
            # Post-traitement des segments (fusion/nettoyage)
            cleaned_segments = self._post_process_diarization(segments)
            
            # Si le résultat original était un dict, on met à jour la liste des segments
            if isinstance(result, dict):
                result['segments'] = cleaned_segments
            else:
                result = {"segments": cleaned_segments}
            
            logger.info(f"Diarisation terminée: {len(cleaned_segments)} segments (après nettoyage)")
            logger.info(json.dumps({
                "session_id": session_id,
                "stage": "diarization",
                "event": "end_runpod",
                "message": "Diarisation RunPod terminée",
                "data": {"segments": len(cleaned_segments), "job_id": job_id},
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }))
            return result
            
        except Exception as e:
            logger.error(f"Erreur lors de la diarisation: {str(e)}", exc_info=True)
            raise

    def _post_process_diarization(self, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Nettoie et fusionne les segments de diarisation
        
        Args:
            segments: Liste brute des segments Pyannote
            
        Returns:
            Liste nettoyée et optimisée
        """
        if not segments:
            return []
            
        # Trier par temps de début
        sorted_segments = sorted(segments, key=lambda x: x['start'])
        cleaned_segments = []
        
        # 1. Nettoyage initial (suppression des micro-segments < 0.15s)
        # On garde les segments courts s'ils semblent isolés (potentiel "Oui/Non")
        # mais on supprime les "glitchs" très courts collés à d'autres
        for seg in sorted_segments:
            duration = seg['end'] - seg['start']
            if duration >= 0.15:
                cleaned_segments.append(seg)
            else:
                logger.debug(f"Suppression segment trop court: {duration:.3f}s ({seg['start']}-{seg['end']})")
                
        if not cleaned_segments:
            return []
            
        # 2. Fusion des segments consécutifs du même speaker
        merged_segments = []
        current_seg = cleaned_segments[0].copy() # Copie pour ne pas modifier l'original
        
        for next_seg in cleaned_segments[1:]:
            # Si même speaker et écart faible (< 1s)
            gap = next_seg['start'] - current_seg['end']
            
            if (next_seg.get('speaker') == current_seg.get('speaker') and gap < 1.0):
                # Fusionner : étendre la fin du segment courant
                current_seg['end'] = next_seg['end']
            else:
                # Valider le segment courant et passer au suivant
                merged_segments.append(current_seg)
                current_seg = next_seg.copy()
                
        merged_segments.append(current_seg)
        
        logger.info(f"Post-traitement diarisation: {len(segments)} -> {len(merged_segments)} segments")
        return merged_segments
    
    
    def _wait_for_completion(self, job_id: str, max_wait: int = 7200, session_id: str = None) -> Dict[str, Any]:
        """
        Attend la complétion d'un job RunPod avec vérification d'annulation
        
        Args:
            job_id: ID du job
            max_wait: Temps maximum d'attente en secondes
            session_id: ID de la session (optionnel, pour vérifier l'annulation)
            
        Returns:
            dict: Résultat du job
            
        Raises:
            Exception: Si la session a été annulée
        """
        start_time = time.time()
        # Délai initial pour laisser le job être créé dans le système
        initial_delay = 2
        logger.info(f"Attente initiale de {initial_delay} secondes pour que le job soit disponible...")
        time.sleep(initial_delay)
        
        consecutive_404 = 0
        max_consecutive_404 = 3  # Tolérer 3 erreurs 404 consécutives avant d'abandonner
        
        check_count = 0
        while time.time() - start_time < max_wait:
            # Vérifier si la session a été annulée (toutes les 6 vérifications, ~30 secondes)
            if session_id and check_count % 6 == 0:
                try:
                    from services.log_manager import LogManager
                    from config import LOGS_FOLDER
                    log_manager = LogManager(LOGS_FOLDER)
                    if log_manager.is_cancelled(session_id):
                        logger.warning(f"Session {session_id} annulée, arrêt de l'attente du job {job_id}")
                        # Tenter d'annuler le job RunPod
                        self.cancel_job(job_id)
                        raise Exception(f"Traitement annulé par l'utilisateur pour la session {session_id}")
                except ImportError:
                    # Si LogManager n'est pas disponible, on continue
                    pass
                except Exception as e:
                    if "annulé" in str(e).lower():
                        raise
                    # Autres erreurs, on continue
            
            check_count += 1
            elapsed_time = int(time.time() - start_time)
            status_url = f"{self.base_url}/status/{job_id}"
            
            # Logger toutes les 6 vérifications (environ toutes les 30 secondes) pour éviter le spam
            if check_count % 6 == 0 or check_count <= 3:
                logger.info(f"Vérification du statut du job {job_id} (tentative {check_count}, {elapsed_time}s écoulées)...")
            
            try:
                with runpod_breaker:
                    response = requests.get(
                        status_url,
                        headers=self.headers,
                        timeout=30
                    )
                
                if response.status_code == 404:
                    consecutive_404 += 1
                    if consecutive_404 >= max_consecutive_404:
                        error_msg = (
                            f"Job {job_id} non trouvé (404) après {consecutive_404} tentatives. "
                            f"Vérifiez que l'Endpoint ID '{self.endpoint_id}' est correct. "
                            f"URL: {status_url}"
                        )
                        logger.error(error_msg)
                        raise Exception(error_msg)
                    else:
                        logger.warning(f"Job {job_id} non trouvé (404), tentative {consecutive_404}/{max_consecutive_404}. Nouvelle tentative dans 3 secondes...")
                        time.sleep(3)
                        continue
                
                # Réinitialiser le compteur si on obtient une réponse valide
                consecutive_404 = 0
                response.raise_for_status()
                
                status = response.json()
                job_status = status.get('status')
                
                # Logger le statut à chaque vérification (mais pas en debug)
                if check_count % 6 == 0 or check_count <= 3 or job_status in ['COMPLETED', 'FAILED']:
                    logger.info(f"Statut du job {job_id}: {job_status}")
                
                if job_status == 'COMPLETED':
                    output = status.get('output', {})
                    logger.info(f"Job {job_id} terminé avec succès après {elapsed_time}s")
                    return output
                elif job_status == 'FAILED':
                    error = status.get('error', 'Erreur inconnue')
                    error_details = status.get('output', {})
                    error_msg = f"Job {job_id} échoué après {elapsed_time}s: {error}"
                    if error_details:
                        logger.error(f"Détails de l'erreur: {error_details}")
                    logger.error(error_msg)
                    raise Exception(error_msg)
                
                # Job en cours (IN_QUEUE, IN_PROGRESS, etc.)
                time.sleep(5)  # Attente de 5 secondes avant le prochain check
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"Erreur lors de la vérification du statut: {str(e)}. Nouvelle tentative dans 5 secondes...")
                time.sleep(5)
                continue
        
        raise TimeoutError(f"Job {job_id} n'a pas terminé dans le délai imparti ({max_wait} secondes)")
    
    def cancel_job(self, job_id: str) -> bool:
        """
        Annule un job RunPod en cours d'exécution
        
        Args:
            job_id: ID du job à annuler
            
        Returns:
            bool: True si l'annulation a réussi, False sinon
        """
        try:
            # API RunPod pour annuler un job : POST /v2/{endpoint_id}/cancel/{job_id}
            cancel_url = f"{self.base_url}/cancel/{job_id}"
            logger.info(f"Tentative d'annulation du job {job_id}...")
            
            with runpod_breaker:
                response = requests.post(
                    cancel_url,
                    headers=self.headers,
                    timeout=30
                )
            
            if response.status_code == 200:
                logger.info(f"Job {job_id} annulé avec succès")
                return True
            elif response.status_code == 404:
                logger.warning(f"Job {job_id} non trouvé (peut-être déjà terminé)")
                return False
            else:
                logger.error(f"Erreur lors de l'annulation du job {job_id}: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Erreur lors de l'annulation du job {job_id}: {str(e)}", exc_info=True)
            return False

