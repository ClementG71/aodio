"""
Service pour appeler directement l'API Mistral AI (Voxtral) pour la transcription
Alternative au worker RunPod si vous préférez appeler directement Mistral AI
"""
import os
import logging
import time
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional
from mistralai import Mistral
from mistralai.models import SDKError

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
        # Pour la transcription via audio/transcriptions, utiliser voxtral-mini-latest
        # Documentation: https://docs.mistral.ai/capabilities/audio_transcription
        # Note: voxtral-small-latest est pour les chat completions avec audio, pas pour les transcriptions
        # voxtral-mini-latest via audio/transcriptions = Voxtral Mini Transcribe (optimisé pour transcription)
        self.model = "voxtral-mini-latest"
        # Limite de contexte: 16384 tokens
        # Pour être sûr, on découpe les fichiers > 8 minutes (estimation conservatrice)
        self.max_segment_duration = 600  # 10 minutes en secondes
        self.max_audio_duration_before_split = 480  # 8 minutes - déclenche le découpage
    
    def _get_audio_duration(self, audio_path: str) -> float:
        """
        Récupère la durée d'un fichier audio en secondes
        
        Args:
            audio_path: Chemin du fichier audio
            
        Returns:
            float: Durée en secondes
        """
        try:
            # Utiliser ffprobe pour obtenir la durée (plus rapide que de charger tout le fichier)
            cmd = [
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                str(audio_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                duration = float(result.stdout.strip())
                return duration
        except Exception as e:
            logger.warning(f"Impossible d'obtenir la durée avec ffprobe: {e}, utilisation de pydub")
        
        # Fallback sur pydub
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_file(audio_path)
            return len(audio) / 1000.0
        except Exception as e:
            logger.error(f"Impossible d'obtenir la durée de l'audio: {e}")
            return 0.0
    
    def _split_audio_into_segments(self, audio_path: str, output_dir: Path) -> List[Dict[str, Any]]:
        """
        Découpe un fichier audio en segments de 10 minutes
        
        Args:
            audio_path: Chemin du fichier audio complet
            output_dir: Dossier où sauvegarder les segments
            
        Returns:
            list: Liste de dict avec 'path', 'start_time', 'end_time' pour chaque segment
        """
        segments = []
        duration = self._get_audio_duration(audio_path)
        
        if duration <= 0:
            raise ValueError(f"Impossible de déterminer la durée de l'audio: {audio_path}")
        
        num_segments = int(duration / self.max_segment_duration) + (1 if duration % self.max_segment_duration > 0 else 0)
        logger.info(f"Découpage de l'audio ({duration:.1f}s) en {num_segments} segments de {self.max_segment_duration}s")
        
        for i in range(num_segments):
            start_time = i * self.max_segment_duration
            segment_duration = min(self.max_segment_duration, duration - start_time)
            
            if segment_duration <= 0:
                break
            
            segment_path = output_dir / f"audio_segment_{i:04d}.wav"
            
            # Découper avec ffmpeg
            cmd = [
                'ffmpeg',
                '-threads', '0',
                '-i', str(audio_path),
                '-ss', str(start_time),
                '-t', str(segment_duration),
                '-acodec', 'pcm_s16le',
                '-ar', '16000',
                '-ac', '1',
                '-loglevel', 'error',
                '-y',
                str(segment_path)
            ]
            
            logger.info(f"Création du segment {i+1}/{num_segments}: {start_time:.1f}s - {start_time + segment_duration:.1f}s")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            
            if result.returncode != 0:
                logger.error(f"Erreur lors du découpage du segment {i}: {result.stderr}")
                raise Exception(f"Erreur lors du découpage de l'audio: {result.stderr}")
            
            segments.append({
                'path': str(segment_path),
                'start_time': start_time,
                'end_time': start_time + segment_duration,
                'index': i
            })
        
        logger.info(f"{len(segments)} segments créés avec succès")
        return segments
    
    def _transcribe_segment(self, segment_path: str, language: str = "fr", 
                           max_retries: int = 3) -> Dict[str, Any]:
        """
        Transcrit un segment audio unique
        
        Args:
            segment_path: Chemin du segment audio
            language: Langue de l'audio
            max_retries: Nombre maximum de tentatives
            
        Returns:
            dict: Réponse de transcription avec segments
        """
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                with open(segment_path, "rb") as f:
                    transcription_response = self.client.audio.transcriptions.complete(
                        model=self.model,
                        file={
                            "content": f,
                            "file_name": os.path.basename(segment_path)
                        },
                        language=language,
                        temperature=0.0,
                        timestamp_granularities=["segment"]
                    )
                
                # Extraire le texte complet
                full_text = ""
                if hasattr(transcription_response, 'text'):
                    full_text = transcription_response.text
                elif isinstance(transcription_response, dict):
                    full_text = transcription_response.get('text', '')
                
                # Extraire les segments
                segments = []
                if hasattr(transcription_response, 'segments'):
                    segments = transcription_response.segments
                elif isinstance(transcription_response, dict):
                    segments = transcription_response.get('segments', [])
                
                # Convertir les segments en listes de dicts si nécessaire
                segments_list = []
                for seg in segments:
                    if isinstance(seg, dict):
                        segments_list.append(seg)
                    else:
                        # Objet avec attributs
                        segments_list.append({
                            'start': getattr(seg, 'start', 0),
                            'end': getattr(seg, 'end', 0),
                            'text': getattr(seg, 'text', '')
                        })
                
                # Log pour déboguer
                logger.debug(f"Transcription segment: {len(segments_list)} segments, texte complet: {len(full_text)} caractères")
                if segments_list:
                    logger.debug(f"Premier segment: start={segments_list[0].get('start', 0):.1f}s, end={segments_list[0].get('end', 0):.1f}s, text_length={len(segments_list[0].get('text', ''))}")
                
                return {
                    'text': full_text,
                    'segments': segments_list
                }
                
            except SDKError as e:
                if hasattr(e, 'http_res') and e.http_res:
                    if e.http_res.status_code == 503:
                        if attempt < max_retries - 1:
                            logger.warning(f"Service indisponible (503), retry dans {retry_delay}s...")
                            time.sleep(retry_delay)
                            retry_delay *= 2
                            continue
                    elif e.http_res.status_code == 400:
                        # Erreur 400 pourrait être "too large" - ne pas retry
                        logger.error(f"Erreur 400 lors de la transcription du segment: {e}")
                        raise
                
                if attempt < max_retries - 1:
                    logger.warning(f"Erreur lors de la transcription (tentative {attempt + 1}/{max_retries}): {e}")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                else:
                    raise
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Erreur lors de la transcription (tentative {attempt + 1}/{max_retries}): {e}")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                else:
                    raise
        
        raise Exception("Échec de la transcription après toutes les tentatives")
    
    def transcribe_audio(self, audio_path: str, 
                        diarization_segments: List[Dict[str, Any]],
                        language: str = "fr") -> Dict[str, Any]:
        """
        Transcrit un fichier audio avec Voxtral Mini (voxtral-mini-latest)
        Découpe automatiquement en segments de 10 minutes si nécessaire
        
        Args:
            audio_path: Chemin du fichier audio local
            diarization_segments: Segments de diarisation pour mapper les speakers
            language: Langue de l'audio (défaut: "fr")
            
        Returns:
            dict: Transcription avec segments mappés aux speakers
        """
        audio_path_obj = Path(audio_path)
        output_dir = audio_path_obj.parent
        
        # Vérifier si le fichier est trop long et nécessite un découpage
        duration = self._get_audio_duration(audio_path)
        needs_split = duration > self.max_audio_duration_before_split
        
        if needs_split:
            logger.info(f"Fichier audio long ({duration:.1f}s), découpage en segments de {self.max_segment_duration}s")
            return self._transcribe_long_audio(audio_path, diarization_segments, language, output_dir)
        else:
            # Fichier court, transcription directe avec gestion d'erreur pour découpage automatique
            return self._transcribe_short_audio(audio_path, diarization_segments, language)
    
    def _transcribe_short_audio(self, audio_path: str,
                               diarization_segments: List[Dict[str, Any]],
                               language: str = "fr") -> Dict[str, Any]:
        """
        Transcrit un fichier audio court (< 8 minutes) directement
        Si erreur 400 (too large), découpe automatiquement et réessaie
        """
        max_retries = 3
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Transcription directe avec {self.model} (tentative {attempt + 1}/{max_retries}): {audio_path}")
                
                with open(audio_path, "rb") as f:
                    transcription_response = self.client.audio.transcriptions.complete(
                        model=self.model,
                        file={
                            "content": f,
                            "file_name": os.path.basename(audio_path)
                        },
                        language=language,
                        temperature=0.0,
                        timestamp_granularities=["segment"]
                    )
                
                # Extraire les segments (même logique que _transcribe_segment)
                segments = []
                if hasattr(transcription_response, 'segments'):
                    segments = transcription_response.segments
                elif isinstance(transcription_response, dict):
                    segments = transcription_response.get('segments', [])
                
                # Convertir les segments en listes de dicts si nécessaire
                mistral_segments = []
                for seg in segments:
                    if isinstance(seg, dict):
                        mistral_segments.append(seg)
                    else:
                        # Objet avec attributs
                        mistral_segments.append({
                            'start': getattr(seg, 'start', 0),
                            'end': getattr(seg, 'end', 0),
                            'text': getattr(seg, 'text', '')
                        })
                
                logger.debug(f"Transcription directe: {len(mistral_segments)} segments Mistral reçus")
                
                # Mapping avec diarisation
                transcriptions = self._map_transcription_to_diarization(mistral_segments, diarization_segments)
                
                result = {
                    "segments": transcriptions,
                    "full_text": transcription_response.text if hasattr(transcription_response, 'text') else ""
                }
                
                logger.info(f"Transcription terminée: {len(transcriptions)} segments")
                return result
                
            except SDKError as e:
                # Si erreur 400 "too large", découper et réessayer
                if (hasattr(e, 'http_res') and e.http_res and 
                    e.http_res.status_code == 400 and 
                    "too large" in str(e).lower()):
                    logger.warning(f"Fichier trop grand (400), découpage automatique...")
                    output_dir = Path(audio_path).parent
                    return self._transcribe_long_audio(audio_path, diarization_segments, language, output_dir)
                
                # Gérer les erreurs 503 avec retry
                if hasattr(e, 'http_res') and e.http_res and e.http_res.status_code == 503:
                    if attempt < max_retries - 1:
                        logger.warning(f"Service indisponible (503), retry dans {retry_delay}s...")
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    else:
                        raise Exception(f"Service Mistral AI indisponible après {max_retries} tentatives: {str(e)}")
                else:
                    logger.error(f"Erreur lors de la transcription: {str(e)}", exc_info=True)
                    raise
            except Exception as e:
                logger.error(f"Erreur lors de la transcription: {str(e)}", exc_info=True)
                raise
    
    def _transcribe_long_audio(self, audio_path: str,
                              diarization_segments: List[Dict[str, Any]],
                              language: str, output_dir: Path) -> Dict[str, Any]:
        """
        Transcrit un fichier audio long en le découpant en segments
        """
        all_mistral_segments = []
        full_text_parts = []
        audio_segments = []  # Initialiser pour le finally
        
        try:
            # Découper l'audio
            audio_segments = self._split_audio_into_segments(audio_path, output_dir)
            
            # Transcrir chaque segment
            for i, seg_info in enumerate(audio_segments):
                logger.info(f"Transcription du segment {i+1}/{len(audio_segments)}: {seg_info['start_time']:.1f}s - {seg_info['end_time']:.1f}s")
                
                seg_result = self._transcribe_segment(seg_info['path'], language)
                
                # Ajuster les timestamps en ajoutant l'offset du segment
                offset = seg_info['start_time']
                segment_mistral_segments = seg_result.get('segments', [])
                logger.debug(f"Segment {i+1}: {len(segment_mistral_segments)} segments Mistral reçus")
                
                for seg in segment_mistral_segments:
                    # Extraire les valeurs (gérer à la fois les dicts et les objets)
                    if isinstance(seg, dict):
                        seg_start = seg.get('start', 0)
                        seg_end = seg.get('end', 0)
                        seg_text = seg.get('text', '')
                    else:
                        seg_start = getattr(seg, 'start', 0)
                        seg_end = getattr(seg, 'end', 0)
                        seg_text = getattr(seg, 'text', '')
                    
                    # Créer un nouveau dict avec timestamps ajustés
                    adjusted_seg = {
                        'start': seg_start + offset,
                        'end': seg_end + offset,
                        'text': seg_text.strip() if seg_text else ''
                    }
                    
                    # Log si le texte est vide
                    if not adjusted_seg['text']:
                        logger.warning(f"Segment Mistral vide: [{adjusted_seg['start']:.1f}s - {adjusted_seg['end']:.1f}s]")
                    
                    all_mistral_segments.append(adjusted_seg)
                
                if seg_result['text']:
                    full_text_parts.append(seg_result['text'])
            
            # Mapping avec diarisation
            transcriptions = self._map_transcription_to_diarization(all_mistral_segments, diarization_segments)
            
            result = {
                "segments": transcriptions,
                "full_text": " ".join(full_text_parts)
            }
            
            logger.info(f"Transcription terminée: {len(transcriptions)} segments (depuis {len(audio_segments)} segments audio)")
            return result
            
        finally:
            # Nettoyer les segments temporaires
            for seg_info in audio_segments:
                try:
                    if os.path.exists(seg_info['path']):
                        os.remove(seg_info['path'])
                        logger.debug(f"Segment temporaire supprimé: {seg_info['path']}")
                except Exception as e:
                    logger.warning(f"Impossible de supprimer le segment {seg_info['path']}: {e}")
    
    def _map_transcription_to_diarization(self, mistral_segments: List[Dict[str, Any]],
                                         diarization_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Mappe les segments de transcription Mistral avec les segments de diarisation
        
        Args:
            mistral_segments: Segments de transcription avec start, end, text
            diarization_segments: Segments de diarisation avec start, end, speaker
            
        Returns:
            list: Segments mappés avec speaker et text
        """
        transcriptions = []
        
        # Convertir tous les segments Mistral en dicts pour faciliter le traitement
        mistral_dicts = []
        for mistral_seg in mistral_segments:
            if isinstance(mistral_seg, dict):
                mistral_dicts.append(mistral_seg)
            else:
                # Objet avec attributs
                mistral_dicts.append({
                    'start': getattr(mistral_seg, 'start', 0),
                    'end': getattr(mistral_seg, 'end', 0),
                    'text': getattr(mistral_seg, 'text', '')
                })
        
        logger.debug(f"Mapping: {len(mistral_dicts)} segments Mistral avec {len(diarization_segments)} segments de diarisation")
        
        # Trier les segments Mistral par timestamp pour faciliter la recherche
        mistral_dicts.sort(key=lambda x: x.get('start', 0))
        
        for diar_seg in diarization_segments:
            diar_start = diar_seg['start']
            diar_end = diar_seg['end']
            
            # Trouver tous les segments Mistral qui chevauchent avec ce segment de diarisation
            matching_texts = []
            for mistral_seg in mistral_dicts:
                mistral_start = mistral_seg.get('start', 0)
                mistral_end = mistral_seg.get('end', float('inf'))
                mistral_text = mistral_seg.get('text', '').strip()
                
                # Vérifier le chevauchement : le segment Mistral chevauche si :
                # - Il commence avant la fin du segment de diarisation ET
                # - Il se termine après le début du segment de diarisation
                if mistral_start < diar_end and mistral_end > diar_start and mistral_text:
                    # Calculer la proportion de chevauchement pour prioriser les segments les plus pertinents
                    overlap_start = max(mistral_start, diar_start)
                    overlap_end = min(mistral_end, diar_end)
                    overlap_duration = overlap_end - overlap_start
                    diar_duration = diar_end - diar_start
                    
                    # Si le chevauchement est significatif (> 50% du segment de diarisation)
                    if overlap_duration > 0 and (overlap_duration / diar_duration) > 0.3:
                        matching_texts.append(mistral_text)
            
            # Concaténer tous les textes correspondants
            mistral_text = " ".join(matching_texts).strip()
            
            # Log si aucun texte trouvé pour déboguer
            if not mistral_text:
                logger.debug(f"Aucun texte trouvé pour segment diarisation [{diar_start:.1f}s - {diar_end:.1f}s] speaker={diar_seg.get('speaker', 'UNKNOWN')}")
            
            transcriptions.append({
                "start": diar_start,
                "end": diar_end,
                "speaker": diar_seg.get('speaker', 'UNKNOWN'),
                "text": mistral_text
            })
        
        # Statistiques de mapping
        segments_with_text = sum(1 for t in transcriptions if t.get('text', '').strip())
        logger.info(f"Mapping terminé: {segments_with_text}/{len(transcriptions)} segments avec texte")
        
        return transcriptions
    
    def transcribe_audio_from_url(self, audio_url: str,
                                  diarization_segments: List[Dict[str, Any]],
                                  language: str = "fr") -> Dict[str, Any]:
        """
        Transcrit un fichier audio depuis une URL avec Voxtral Mini (voxtral-mini-latest)
        
        Args:
            audio_url: URL du fichier audio
            diarization_segments: Segments de diarisation pour mapper les speakers
            language: Langue de l'audio (défaut: "fr")
            
        Returns:
            dict: Transcription avec segments mappés aux speakers
        """
        max_retries = 3
        retry_delay = 5  # secondes
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Transcription depuis URL avec {self.model} (tentative {attempt + 1}/{max_retries}): {audio_url}")
                
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
                
            except SDKError as e:
                # Gérer les erreurs 503 (Service Unavailable) avec retry
                if hasattr(e, 'http_res') and e.http_res and e.http_res.status_code == 503:
                    if attempt < max_retries - 1:
                        logger.warning(f"Service Mistral AI temporairement indisponible (503), nouvelle tentative dans {retry_delay}s...")
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Backoff exponentiel
                        continue
                    else:
                        logger.error(f"Service Mistral AI indisponible après {max_retries} tentatives: {str(e)}")
                        raise Exception(f"Service Mistral AI temporairement indisponible. Veuillez réessayer plus tard. Erreur: {str(e)}")
                else:
                    # Autres erreurs (400, 401, etc.) - ne pas retry
                    logger.error(f"Erreur lors de la transcription: {str(e)}", exc_info=True)
                    raise
            except Exception as e:
                logger.error(f"Erreur lors de la transcription: {str(e)}", exc_info=True)
                raise

