"""
Service pour appeler directement l'API Mistral AI (Voxtral) pour la transcription
Alternative au worker RunPod si vous préférez appeler directement Mistral AI
"""
import os
import json
import logging
import time
import subprocess
import re
import uuid
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
        
        # Configuration pour Voxtral-Small en mode chat (méthode principale)
        self.use_voxtral_small_chat = True  # Activer Voxtral-Small chat comme méthode principale
        self.max_duration_for_voxtral_small_chat = 900  # 15 minutes (marge sécurité pour limite 20 min)
        self.voxtral_small_segment_duration = 600  # 10 minutes par segment pour rester sous 20 MB
    
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
    
    def _split_audio_into_segments(self, audio_path: str, output_dir: Path, 
                                   segment_duration: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Découpe un fichier audio en segments
        
        Args:
            audio_path: Chemin du fichier audio complet
            output_dir: Dossier où sauvegarder les segments
            segment_duration: Durée de chaque segment en secondes (défaut: self.max_segment_duration)
            
        Returns:
            list: Liste de dict avec 'path', 'start_time', 'end_time' pour chaque segment
        """
        # Utiliser la durée fournie ou la durée par défaut
        if segment_duration is None:
            segment_duration = self.max_segment_duration
        
        segments = []
        duration = self._get_audio_duration(audio_path)
        
        if duration <= 0:
            raise ValueError(f"Impossible de déterminer la durée de l'audio: {audio_path}")
        
        num_segments = int(duration / segment_duration) + (1 if duration % segment_duration > 0 else 0)
        logger.info(f"Découpage de l'audio ({duration:.1f}s) en {num_segments} segments de {segment_duration}s")
        
        for i in range(num_segments):
            start_time = i * segment_duration
            seg_duration = min(segment_duration, duration - start_time)
            
            if seg_duration <= 0:
                break
            
            # Générer un nom de fichier unique pour éviter les conflits
            unique_id = str(uuid.uuid4())[:8]
            segment_path = output_dir / f"audio_segment_{i:04d}_{unique_id}.wav"
            
            # Découper avec ffmpeg
            cmd = [
                'ffmpeg',
                '-threads', '0',
                '-i', str(audio_path),
                '-ss', str(start_time),
                '-t', str(seg_duration),
                '-acodec', 'pcm_s16le',
                '-ar', '16000',
                '-ac', '1',
                '-loglevel', 'error',
                '-y',
                str(segment_path)
            ]
            
            logger.info(f"Création du segment {i+1}/{num_segments}: {start_time:.1f}s - {start_time + seg_duration:.1f}s")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            
            if result.returncode != 0:
                logger.error(f"Erreur lors du découpage du segment {i}: {result.stderr}")
                raise Exception(f"Erreur lors du découpage de l'audio: {result.stderr}")
            
            segments.append({
                'path': str(segment_path),
                'start_time': start_time,
                'end_time': start_time + seg_duration,
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
        Transcrit un fichier audio avec routage intelligent :
        - Méthode principale : Voxtral-Small en mode chat avec contexte diarisation
        - Fallback : Méthode classique (Voxtral Mini) en dernier recours
        
        Args:
            audio_path: Chemin du fichier audio local
            diarization_segments: Segments de diarisation pour mapper les speakers
            language: Langue de l'audio (défaut: "fr")
            
        Returns:
            dict: Transcription avec segments mappés aux speakers
        """
        # Utiliser Voxtral-Small chat comme méthode principale si activé
        if self.use_voxtral_small_chat:
            try:
                duration = self._get_audio_duration(audio_path)
                audio_url = self._get_audio_url(audio_path)
                
                if duration <= self.max_duration_for_voxtral_small_chat:
                    logger.info(f"Fichier court ({duration:.1f}s), utilisation Voxtral-Small chat")
                    return self._transcribe_with_voxtral_small_chat(
                        audio_path, audio_url, diarization_segments, language
                    )
                else:
                    logger.info(f"Fichier long ({duration:.1f}s), découpage en segments avec Voxtral-Small")
                    return self._transcribe_long_audio_with_voxtral_small(
                        audio_path, audio_url, diarization_segments, language
                    )
            except Exception as e:
                logger.error(f"Erreur avec Voxtral-Small chat: {e}, fallback sur méthode classique")
                # Fallback sur méthode classique
                return self._transcribe_audio_classic(audio_path, diarization_segments, language)
        else:
            # Méthode classique directement
            return self._transcribe_audio_classic(audio_path, diarization_segments, language)
    
    def _get_audio_url(self, audio_path: str) -> str:
        """
        Génère l'URL publique de l'audio pour l'API Mistral
        
        Args:
            audio_path: Chemin local du fichier audio
            
        Returns:
            str: URL publique du fichier audio
        """
        app_base_url = os.getenv('RAILWAY_PUBLIC_DOMAIN') or os.getenv('APP_BASE_URL', 'http://localhost:5000')
        if not app_base_url.startswith('http'):
            app_base_url = f"https://{app_base_url}"
        
        # Extraire le chemin relatif depuis audio_path
        # Exemple: uploads/session_id/audio_processed.wav
        path_parts = Path(audio_path).parts
        if 'uploads' in path_parts:
            idx = path_parts.index('uploads')
            # Construire l'URL: https://domain.com/files/session_id/audio_processed.wav
            return f"{app_base_url}/files/{'/'.join(path_parts[idx+1:])}"
        
        # Fallback : utiliser le nom du fichier
        return f"{app_base_url}/files/{Path(audio_path).name}"
    
    def _transcribe_with_voxtral_small_chat(self, audio_path: str,
                                           audio_url: Optional[str],
                                           diarization_segments: List[Dict[str, Any]],
                                           language: str = "fr") -> Dict[str, Any]:
        """
        Transcription avec Voxtral-Small en mode chat
        Fournit l'audio + segments de diarisation comme contexte
        Obtient directement un format structuré avec attribution correcte
        
        Args:
            audio_path: Chemin local du fichier audio
            audio_url: URL publique du fichier audio
            diarization_segments: Segments de diarisation
            language: Langue de l'audio
            
        Returns:
            dict: Transcription avec segments mappés aux speakers
        """
        try:
            # Formater les segments de diarisation pour le prompt
            diarization_context = self._format_diarization_for_prompt(diarization_segments)
            
            # Construire le prompt avec instructions précises
            prompt = f"""Tu es un assistant expert en transcription de réunions.

TÂCHE :
Transcris l'audio fourni en respectant STRICTEMENT les segments de diarisation fournis.
Chaque segment de diarisation correspond à une intervention d'un locuteur spécifique.

SEGMENTS DE DIARISATION (ordre chronologique) :
{diarization_context}

INSTRUCTIONS CRITIQUES :
1. Pour chaque segment de diarisation, transcris UNIQUEMENT le texte prononcé pendant cette période temporelle exacte
2. Respecte l'ordre chronologique strict des segments
3. Si un segment de diarisation est très court (< 0.5s) ou silencieux, laisse le texte vide mais conserve le segment
4. Si plusieurs segments consécutifs ont le même speaker, tu peux regrouper le texte mais conserve les timestamps individuels
5. Ne tronque PAS les interventions au milieu d'une phrase - si une phrase commence dans un segment et se termine dans le suivant, répartis-la intelligemment
6. Si tu détectes une incohérence (ex: même voix mais speaker différent sur segments adjacents), attribue au speaker le plus probable en te basant sur le contexte
7. Le texte doit être la transcription verbatim (mot à mot) de ce qui est dit

FORMAT DE RÉPONSE (JSON strict, aucun texte avant/après) :
{{
  "segments": [
    {{
      "start": 0.0,
      "end": 5.2,
      "speaker": "SPEAKER_00",
      "text": "Texte transcrit pour ce segment exact"
    }},
    {{
      "start": 5.2,
      "end": 12.8,
      "speaker": "SPEAKER_01",
      "text": "Texte transcrit pour ce segment exact"
    }}
  ],
  "full_text": "Texte complet de toute la transcription"
}}

IMPORTANT :
- Les timestamps (start/end) doivent correspondre EXACTEMENT aux segments de diarisation fournis
- Le speaker doit correspondre EXACTEMENT au speaker du segment de diarisation
- Chaque segment de diarisation doit avoir un segment de transcription correspondant
- Le texte doit être la transcription verbatim de ce qui est dit pendant ce segment temporel précis
"""
            
            # Utiliser URL si fournie, sinon générer URL Flask publique
            audio_url_to_use = audio_url
            
            if not audio_url_to_use:
                # Générer URL Flask publique (réutilise l'infrastructure existante)
                audio_url_to_use = self._get_audio_url(audio_path)
                logger.info(f"URL Flask générée pour le fichier audio: {audio_url_to_use}")
            
            # Utiliser l'URL Flask pour la transcription
            logger.info(f"Transcription avec audio (URL Flask): {audio_url_to_use}")
            response = self.client.chat.complete(
                model="voxtral-small-latest",
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": audio_url_to_use,  # URL Flask publique
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }],
                temperature=0.0,  # Déterministe
                response_format={"type": "json_object"}  # Forcer JSON
            )
            
            # Parser la réponse JSON
            result_content = response.choices[0].message.content
            result = json.loads(result_content)
            
            # Extraire les segments et le texte complet
            transcriptions = result.get('segments', [])
            full_text = result.get('full_text', '')
            
            logger.info(f"Voxtral-Small chat: {len(transcriptions)} segments reçus")
            
            # Valider et aligner avec les segments de diarisation
            # S'assurer que tous les segments de diarisation ont un segment de transcription
            transcriptions = self._align_transcription_with_diarization(
                transcriptions, diarization_segments
            )
            
            # Validation finale
            self._validate_transcription_mapping(transcriptions, diarization_segments)
            
            return {
                "segments": transcriptions,
                "full_text": full_text
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"Erreur parsing JSON de Voxtral-Small: {e}")
            if 'result_content' in locals():
                logger.error(f"Réponse reçue (premiers 500 caractères): {result_content[:500]}")
            # Fallback sur méthode classique
            return self._fallback_to_classic_transcription(audio_path, diarization_segments, language)
        except Exception as e:
            logger.error(f"Erreur avec Voxtral-Small chat: {e}", exc_info=True)
            # Fallback sur méthode classique
            return self._fallback_to_classic_transcription(audio_path, diarization_segments, language)
    
    def _format_diarization_for_prompt(self, diarization_segments: List[Dict[str, Any]]) -> str:
        """
        Formate les segments de diarisation pour le prompt
        Format lisible et structuré
        
        Args:
            diarization_segments: Liste des segments de diarisation
            
        Returns:
            str: Texte formaté pour le prompt
        """
        lines = []
        lines.append("Voici les segments de diarisation (détection automatique des locuteurs) :")
        lines.append("")
        
        for i, seg in enumerate(diarization_segments, 1):
            start = seg.get('start', 0)
            end = seg.get('end', 0)
            speaker = seg.get('speaker', 'UNKNOWN')
            duration = end - start
            
            # Formater le temps en HH:MM:SS
            start_str = self._format_time_for_prompt(start)
            end_str = self._format_time_for_prompt(end)
            
            lines.append(f"Segment {i}: [{start_str} - {end_str}] {speaker} (durée: {duration:.1f}s)")
        
        return "\n".join(lines)
    
    def _format_time_for_prompt(self, seconds: float) -> str:
        """
        Formate les secondes en HH:MM:SS pour le prompt
        
        Args:
            seconds: Nombre de secondes
            
        Returns:
            str: Temps formaté HH:MM:SS
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    def _align_transcription_with_diarization(self, transcriptions: List[Dict[str, Any]],
                                              diarization_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Aligne les transcriptions reçues de Voxtral-Small avec les segments de diarisation
        S'assure que chaque segment de diarisation a un segment de transcription
        
        Args:
            transcriptions: Segments de transcription de Voxtral-Small
            diarization_segments: Segments de diarisation originaux
            
        Returns:
            list: Segments alignés avec diarisation
        """
        # Créer un mapping par timestamp (avec tolérance)
        transcription_map = {}
        for trans in transcriptions:
            trans_start = trans.get('start', 0)
            trans_end = trans.get('end', 0)
            # Utiliser le début comme clé (avec tolérance de 0.5s)
            key = round(trans_start * 2) / 2  # Arrondir à 0.5s près
            transcription_map[key] = trans
        
        # Aligner avec les segments de diarisation
        aligned = []
        for diar_seg in diarization_segments:
            diar_start = diar_seg.get('start', 0)
            diar_end = diar_seg.get('end', 0)
            diar_speaker = diar_seg.get('speaker', 'UNKNOWN')
            
            # Chercher le segment de transcription le plus proche
            best_match = None
            best_distance = float('inf')
            
            for trans in transcriptions:
                trans_start = trans.get('start', 0)
                trans_end = trans.get('end', 0)
                
                # Distance = différence de début + différence de fin
                distance = abs(trans_start - diar_start) + abs(trans_end - diar_end)
                
                # Tolérance : si la distance est < 2 secondes, c'est probablement le bon segment
                if distance < best_distance and distance < 2.0:
                    best_distance = distance
                    best_match = trans
            
            if best_match:
                # Utiliser le texte de la transcription mais les timestamps de la diarisation
                aligned.append({
                    "start": diar_start,  # Utiliser les timestamps de diarisation (plus précis)
                    "end": diar_end,
                    "speaker": diar_speaker,  # Utiliser le speaker de diarisation (garanti cohérent)
                    "text": best_match.get('text', '').strip()
                })
            else:
                # Segment sans transcription correspondante
                aligned.append({
                    "start": diar_start,
                    "end": diar_end,
                    "speaker": diar_speaker,
                    "text": ""
                })
                if len(aligned) <= 5:  # Logger seulement les premiers
                    logger.debug(f"Aucune transcription trouvée pour segment diarisation [{diar_start:.1f}s-{diar_end:.1f}s] {diar_speaker}")
        
        return aligned
    
    def _transcribe_long_audio_with_voxtral_small(self, audio_path: str,
                                                  audio_url: Optional[str],
                                                  diarization_segments: List[Dict[str, Any]],
                                                  language: str = "fr") -> Dict[str, Any]:
        """
        Transcription de fichiers longs avec découpage intelligent
        Chaque segment est traité avec Voxtral-Small en mode chat avec son contexte de diarisation
        
        Args:
            audio_path: Chemin du fichier audio complet
            audio_url: URL publique du fichier audio
            diarization_segments: Segments de diarisation complets
            language: Langue de l'audio
            
        Returns:
            dict: Transcription complète avec segments mappés
        """
        duration = self._get_audio_duration(audio_path)
        output_dir = Path(audio_path).parent
        
        # Découper l'audio en segments de 15 minutes
        audio_segments = self._split_audio_into_segments(
            audio_path, output_dir, self.voxtral_small_segment_duration
        )
        
        all_transcriptions = []
        full_text_parts = []
        
        try:
            for i, seg_info in enumerate(audio_segments):
                seg_start = seg_info['start_time']
                seg_end = seg_info['end_time']
                
                logger.info(f"Traitement segment {i+1}/{len(audio_segments)}: {seg_start:.1f}s - {seg_end:.1f}s")
                
                # Filtrer les segments de diarisation qui appartiennent à ce segment audio
                relevant_diarization = [
                    d for d in diarization_segments
                    if d.get('start', 0) < seg_end and d.get('end', 0) > seg_start
                ]
                
                if not relevant_diarization:
                    logger.warning(f"Aucun segment de diarisation pour le segment audio {i+1}")
                    continue
                
                # Ajuster les timestamps des segments de diarisation pour ce segment audio
                # (relatifs au début du segment audio)
                adjusted_diarization = []
                for d in relevant_diarization:
                    # Calculer les timestamps relatifs au segment audio
                    rel_start = max(0, d.get('start', 0) - seg_start)
                    rel_end = min(seg_end - seg_start, d.get('end', 0) - seg_start)
                    
                    adjusted_diarization.append({
                        'start': rel_start,
                        'end': rel_end,
                        'speaker': d.get('speaker', 'UNKNOWN')
                    })
                
                # Les segments temporaires sont dans le même dossier que le fichier original
                # donc ils sont accessibles via la route Flask /files/
                segment_url = None  # Sera généré automatiquement par _get_audio_url() si None
                
                # Transcrir ce segment avec Voxtral-Small en mode chat
                try:
                    segment_result = self._transcribe_with_voxtral_small_chat(
                        seg_info['path'],
                        segment_url,  # None = utiliser fichier directement
                        adjusted_diarization,
                        language
                    )
                    
                    # Ajuster les timestamps pour le fichier complet
                    for trans in segment_result.get('segments', []):
                        trans['start'] += seg_start
                        trans['end'] += seg_start
                        all_transcriptions.append(trans)
                    
                    if segment_result.get('full_text'):
                        full_text_parts.append(segment_result['full_text'])
                        
                except Exception as e:
                    logger.error(f"Erreur segment {i+1} avec Voxtral-Small: {e}, fallback méthode classique")
                    # Fallback : utiliser méthode classique pour ce segment
                    fallback_result = self._transcribe_segment(seg_info['path'], language)
                    
                    # Mapper avec diarisation (méthode classique)
                    mistral_segments = fallback_result.get('segments', [])
                    for seg in mistral_segments:
                        seg['start'] += seg_start
                        seg['end'] += seg_start
                    
                    # Utiliser le mapping hybride existant
                    segment_transcriptions = self._map_transcription_to_diarization_hybrid(
                        mistral_segments, relevant_diarization, fallback_result.get('text', '')
                    )
                    
                    # Ajuster timestamps
                    for trans in segment_transcriptions:
                        trans['start'] += seg_start
                        trans['end'] += seg_start
                        all_transcriptions.append(trans)
                    
                    if fallback_result.get('text'):
                        full_text_parts.append(fallback_result['text'])
            
            # Trier par timestamp
            all_transcriptions.sort(key=lambda x: x.get('start', 0))
            
            # Validation finale
            self._validate_transcription_mapping(all_transcriptions, diarization_segments)
            
            return {
                "segments": all_transcriptions,
                "full_text": " ".join(full_text_parts)
            }
            
        finally:
            # Nettoyer les segments temporaires
            for seg_info in audio_segments:
                try:
                    if os.path.exists(seg_info['path']):
                        os.remove(seg_info['path'])
                        logger.debug(f"Segment temporaire supprimé: {seg_info['path']}")
                except Exception as e:
                    logger.warning(f"Impossible de supprimer le segment {seg_info['path']}: {e}")
    
    def _transcribe_audio_classic(self, audio_path: str,
                                  diarization_segments: List[Dict[str, Any]],
                                  language: str = "fr") -> Dict[str, Any]:
        """
        Méthode classique de transcription (fallback)
        Utilise Voxtral Mini via l'endpoint de transcription
        
        Args:
            audio_path: Chemin du fichier audio
            diarization_segments: Segments de diarisation
            language: Langue de l'audio
            
        Returns:
            dict: Transcription avec segments mappés
        """
        logger.info("Utilisation de la méthode classique de transcription")
        duration = self._get_audio_duration(audio_path)
        if duration <= self.max_audio_duration_before_split:
            return self._transcribe_short_audio(audio_path, diarization_segments, language)
        else:
            output_dir = Path(audio_path).parent
            return self._transcribe_long_audio(audio_path, diarization_segments, language, output_dir)
    
    def _fallback_to_classic_transcription(self, audio_path: str,
                                          diarization_segments: List[Dict[str, Any]],
                                          language: str) -> Dict[str, Any]:
        """
        Fallback sur la méthode de transcription classique
        Appelé en cas d'erreur avec Voxtral-Small chat
        
        Args:
            audio_path: Chemin du fichier audio
            diarization_segments: Segments de diarisation
            language: Langue de l'audio
            
        Returns:
            dict: Transcription avec segments mappés
        """
        logger.info("Fallback sur méthode de transcription classique")
        return self._transcribe_audio_classic(audio_path, diarization_segments, language)
    
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
                
                logger.info(f"Transcription directe: {len(mistral_segments)} segments Mistral reçus, texte complet: {len(transcription_response.text if hasattr(transcription_response, 'text') else '')} caractères")
                
                # Utiliser le mapping hybride amélioré
                full_text = transcription_response.text if hasattr(transcription_response, 'text') else ""
                transcriptions = self._map_transcription_to_diarization_hybrid(
                    mistral_segments, diarization_segments, full_text
                )
                
                result = {
                    "segments": transcriptions,
                    "full_text": full_text
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
                logger.info(f"Segment {i+1}: {len(segment_mistral_segments)} segments Mistral reçus, texte complet: {len(seg_result.get('text', ''))} caractères")
                
                segments_with_text_count = 0
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
                    
                    # Compter les segments avec texte
                    if adjusted_seg['text']:
                        segments_with_text_count += 1
                        # Log les premiers segments avec texte pour déboguer
                        if segments_with_text_count <= 3:
                            logger.info(f"Segment Mistral {segments_with_text_count} avec texte: [{adjusted_seg['start']:.1f}s - {adjusted_seg['end']:.1f}s] '{adjusted_seg['text'][:50]}...'")
                    else:
                        # Log seulement les premiers segments vides
                        if len(all_mistral_segments) < 3:
                            logger.warning(f"Segment Mistral vide: [{adjusted_seg['start']:.1f}s - {adjusted_seg['end']:.1f}s]")
                    
                    all_mistral_segments.append(adjusted_seg)
                
                logger.info(f"Segment {i+1}: {segments_with_text_count}/{len(segment_mistral_segments)} segments Mistral avec texte")
                
                if seg_result.get('text'):
                    full_text_parts.append(seg_result['text'])
            
            logger.info(f"Total segments Mistral après ajustement: {len(all_mistral_segments)}, segments avec texte: {sum(1 for s in all_mistral_segments if s.get('text', '').strip())}")
            
            # Utiliser le mapping hybride amélioré
            full_text = " ".join(full_text_parts) if full_text_parts else ""
            transcriptions = self._map_transcription_to_diarization_hybrid(
                all_mistral_segments, diarization_segments, full_text
            )
            
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
        
        logger.info(f"Mapping: {len(mistral_dicts)} segments Mistral avec {len(diarization_segments)} segments de diarisation")
        
        # Compter les segments Mistral avec texte
        mistral_with_text = sum(1 for m in mistral_dicts if m.get('text', '').strip())
        logger.info(f"Segments Mistral avec texte: {mistral_with_text}/{len(mistral_dicts)}")
        
        # Log les premiers segments Mistral pour déboguer
        if mistral_dicts:
            logger.info(f"Premier segment Mistral: start={mistral_dicts[0].get('start', 0):.1f}s, end={mistral_dicts[0].get('end', 0):.1f}s, text_length={len(mistral_dicts[0].get('text', ''))}")
            if len(mistral_dicts) > 1:
                logger.info(f"Dernier segment Mistral: start={mistral_dicts[-1].get('start', 0):.1f}s, end={mistral_dicts[-1].get('end', 0):.1f}s, text_length={len(mistral_dicts[-1].get('text', ''))}")
        
        # Log les premiers segments de diarisation pour déboguer
        if diarization_segments:
            logger.info(f"Premier segment diarisation: start={diarization_segments[0].get('start', 0):.1f}s, end={diarization_segments[0].get('end', 0):.1f}s, speaker={diarization_segments[0].get('speaker', 'UNKNOWN')}")
            if len(diarization_segments) > 1:
                logger.info(f"Dernier segment diarisation: start={diarization_segments[-1].get('start', 0):.1f}s, end={diarization_segments[-1].get('end', 0):.1f}s, speaker={diarization_segments[-1].get('speaker', 'UNKNOWN')}")
        
        # Trier les segments Mistral par timestamp pour faciliter la recherche
        mistral_dicts.sort(key=lambda x: x.get('start', 0))
        
        matches_found = 0
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
                    
                    # Si le chevauchement est significatif (au moins 10% du segment de diarisation ou 1 seconde)
                    # Réduit le seuil de 30% à 10% pour être plus permissif
                    min_overlap_ratio = 0.1  # 10% minimum
                    min_overlap_duration = 1.0  # ou au moins 1 seconde
                    
                    if overlap_duration > 0 and (
                        (overlap_duration / diar_duration) >= min_overlap_ratio or 
                        overlap_duration >= min_overlap_duration
                    ):
                        matching_texts.append(mistral_text)
                        
                        # Log détaillé pour les premiers matches
                        if matches_found == 0 and len(matching_texts) == 1:
                            logger.info(f"Premier match trouvé: diarisation [{diar_start:.1f}s-{diar_end:.1f}s] chevauche avec Mistral [{mistral_start:.1f}s-{mistral_end:.1f}s] (overlap: {overlap_duration:.1f}s, ratio: {overlap_duration/diar_duration*100:.1f}%)")
            
            # Concaténer tous les textes correspondants
            mistral_text = " ".join(matching_texts).strip()
            
            if mistral_text:
                matches_found += 1
                # Log les premiers matches pour déboguer
                if matches_found <= 3:
                    logger.info(f"Match {matches_found}: segment diarisation [{diar_start:.1f}s - {diar_end:.1f}s] speaker={diar_seg.get('speaker', 'UNKNOWN')} -> texte: '{mistral_text[:50]}...'")
            else:
                # Log seulement les premiers segments sans match pour déboguer
                if len(transcriptions) < 5:
                    logger.debug(f"Aucun texte trouvé pour segment diarisation [{diar_start:.1f}s - {diar_end:.1f}s] speaker={diar_seg.get('speaker', 'UNKNOWN')}")
            
            transcriptions.append({
                "start": diar_start,
                "end": diar_end,
                "speaker": diar_seg.get('speaker', 'UNKNOWN'),
                "text": mistral_text
            })
        
        # Statistiques de mapping
        segments_with_text = sum(1 for t in transcriptions if t.get('text', '').strip())
        logger.info(f"Mapping terminé: {segments_with_text}/{len(transcriptions)} segments avec texte ({matches_found} matches trouvés)")
        
        if segments_with_text == 0 and mistral_with_text > 0:
            logger.error(f"PROBLÈME: {mistral_with_text} segments Mistral ont du texte mais aucun mapping n'a été trouvé! Vérifier la logique de chevauchement.")
        
        return transcriptions
    
    def _map_transcription_to_diarization_hybrid(self, mistral_segments: List[Dict[str, Any]],
                                                diarization_segments: List[Dict[str, Any]],
                                                full_text: str = "") -> List[Dict[str, Any]]:
        """
        Mapping hybride amélioré avec validation
        
        Stratégie:
        1. Si timestamps Mistral disponibles → mapping par chevauchement temporel
        2. Si timestamps partiels → combinaison des deux méthodes
        3. Si seulement texte complet → distribution séquentielle
        4. Validation et correction des incohérences
        """
        logger.info(f"Mapping hybride: {len(mistral_segments)} segments Mistral, "
                   f"{len(diarization_segments)} segments diarisation")
        
        # Trier par timestamp
        diarization_segments = sorted(diarization_segments, key=lambda x: x.get('start', 0))
        
        # Cas 1: Segments Mistral avec timestamps disponibles
        mistral_with_timestamps = [m for m in mistral_segments 
                                   if m.get('start') is not None and m.get('end') is not None]
        
        if len(mistral_with_timestamps) >= len(diarization_segments) * 0.5:
            # Au moins 50% des segments ont des timestamps → utiliser mapping temporel
            logger.info("Utilisation du mapping temporel (timestamps disponibles)")
            transcriptions = self._map_transcription_to_diarization_v1(
                mistral_with_timestamps, diarization_segments
            )
            
            # Validation et complétion si nécessaire
            segments_without_text = [t for t in transcriptions if not t.get('text', '').strip()]
            if segments_without_text and full_text:
                logger.warning(f"{len(segments_without_text)} segments sans texte, complétion...")
                transcriptions = self._fill_missing_segments_with_sequential(
                    transcriptions, full_text, diarization_segments
                )
        else:
            # Moins de 50% de timestamps → utiliser distribution séquentielle
            logger.info("Utilisation de la distribution séquentielle (peu de timestamps)")
            transcriptions = self._distribute_text_by_chronological_order(
                full_text, diarization_segments
            )
        
        # Validation finale
        self._validate_transcription_mapping(transcriptions, diarization_segments)
        
        return transcriptions
    
    def _map_transcription_to_diarization_v1(self, mistral_segments: List[Dict[str, Any]],
                                             diarization_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Mapping temporel amélioré : attribution unique avec meilleur chevauchement
        """
        # Convertir et trier
        mistral_dicts = []
        for mistral_seg in mistral_segments:
            if isinstance(mistral_seg, dict):
                mistral_dicts.append(mistral_seg)
            else:
                mistral_dicts.append({
                    'start': getattr(mistral_seg, 'start', 0),
                    'end': getattr(mistral_seg, 'end', 0),
                    'text': getattr(mistral_seg, 'text', '')
                })
        
        mistral_dicts = sorted(mistral_dicts, key=lambda x: x.get('start', 0))
        diarization_segments = sorted(diarization_segments, key=lambda x: x.get('start', 0))
        
        # Marquer les segments Mistral comme non utilisés
        mistral_used = [False] * len(mistral_dicts)
        transcriptions = []
        
        for diar_seg in diarization_segments:
            diar_start = diar_seg['start']
            diar_end = diar_seg['end']
            diar_duration = diar_end - diar_start
            
            # Trouver le segment Mistral avec le meilleur chevauchement (non utilisé)
            best_match = None
            best_overlap_ratio = 0
            best_overlap_duration = 0
            
            for idx, mistral_seg in enumerate(mistral_dicts):
                if mistral_used[idx]:
                    continue
                    
                mistral_start = mistral_seg.get('start', 0)
                mistral_end = mistral_seg.get('end', float('inf'))
                mistral_text = mistral_seg.get('text', '').strip()
                
                if not mistral_text:
                    continue
                
                # Calculer le chevauchement
                overlap_start = max(mistral_start, diar_start)
                overlap_end = min(mistral_end, diar_end)
                overlap_duration = max(0, overlap_end - overlap_start)
                
                if overlap_duration <= 0:
                    continue
                
                # Ratio de chevauchement (proportion du segment de diarisation couvert)
                overlap_ratio = overlap_duration / diar_duration if diar_duration > 0 else 0
                
                # Seuil minimum : au moins 30% de chevauchement OU au moins 1 seconde
                min_overlap_ratio = 0.3
                min_overlap_duration = 1.0
                
                if (overlap_ratio >= min_overlap_ratio or overlap_duration >= min_overlap_duration):
                    # Prioriser les segments avec le meilleur chevauchement
                    # Score = ratio de chevauchement * 0.7 + durée de chevauchement normalisée * 0.3
                    normalized_duration = min(overlap_duration / 10.0, 1.0)  # Normaliser sur 10s max
                    score = overlap_ratio * 0.7 + normalized_duration * 0.3
                    
                    current_score = best_overlap_ratio * 0.7 + (best_overlap_duration / 10.0) * 0.3
                    
                    if score > current_score:
                        best_overlap_ratio = overlap_ratio
                        best_overlap_duration = overlap_duration
                        best_match = (idx, mistral_seg)
            
            # Attribuer le texte si match trouvé
            if best_match:
                idx, mistral_seg = best_match
                mistral_used[idx] = True
                text = mistral_seg.get('text', '').strip()
                
                # Log pour les premiers matches
                if len(transcriptions) < 3:
                    logger.info(f"Match trouvé: diarisation [{diar_start:.1f}s-{diar_end:.1f}s] "
                              f"speaker={diar_seg.get('speaker', 'UNKNOWN')} "
                              f"-> Mistral [{mistral_seg.get('start', 0):.1f}s-{mistral_seg.get('end', 0):.1f}s] "
                              f"(overlap: {best_overlap_ratio*100:.1f}%)")
            else:
                text = ""
                if len(transcriptions) < 5:
                    logger.debug(f"Aucun match pour segment diarisation "
                               f"[{diar_start:.1f}s-{diar_end:.1f}s] speaker={diar_seg.get('speaker', 'UNKNOWN')}")
            
            transcriptions.append({
                "start": diar_start,
                "end": diar_end,
                "speaker": diar_seg.get('speaker', 'UNKNOWN'),
                "text": text
            })
        
        # Statistiques
        segments_with_text = sum(1 for t in transcriptions if t.get('text', '').strip())
        logger.info(f"Mapping temporel terminé: {segments_with_text}/{len(transcriptions)} segments avec texte")
        
        return transcriptions
    
    def _distribute_text_by_chronological_order(self, full_text: str,
                                               diarization_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Distribution séquentielle : le texte est distribué dans l'ordre chronologique
        strict des segments de diarisation
        """
        # Trier par ordre chronologique
        sorted_segments = sorted(diarization_segments, key=lambda x: x.get('start', 0))
        
        # Découper le texte en phrases
        sentence_pattern = r'([.!?])\s+'
        sentences = re.split(sentence_pattern, full_text)
        
        # Reconstruire les phrases complètes
        complete_sentences = []
        i = 0
        while i < len(sentences):
            sentence = sentences[i].strip()
            if i + 1 < len(sentences):
                punctuation = sentences[i + 1]
                sentence += punctuation
                i += 2
            else:
                i += 1
            
            if sentence:
                complete_sentences.append(sentence)
        
        complete_sentences = [s.strip() for s in complete_sentences if s.strip()]
        total_sentences = len(complete_sentences)
        
        logger.info(f"Distribution séquentielle: {total_sentences} phrases sur {len(sorted_segments)} segments")
        
        # Calculer la durée totale de parole
        total_speech_duration = sum(seg.get('end', 0) - seg.get('start', 0) 
                                   for seg in sorted_segments)
        
        if total_speech_duration == 0:
            logger.error("Durée totale de parole = 0, impossible de distribuer")
            return [{"start": seg['start'], "end": seg['end'], 
                    "speaker": seg['speaker'], "text": ""} 
                   for seg in sorted_segments]
        
        # Distribution séquentielle
        transcriptions = []
        sentence_index = 0
        current_speaker = None
        
        for seg_idx, diar_seg in enumerate(sorted_segments):
            diar_start = diar_seg.get('start', 0)
            diar_end = diar_seg.get('end', 0)
            diar_duration = diar_end - diar_start
            seg_speaker = diar_seg.get('speaker', 'UNKNOWN')
            
            # Si changement de speaker, s'assurer qu'on termine la phrase en cours
            if current_speaker != seg_speaker and current_speaker is not None:
                # Prendre au moins une phrase complète pour le nouveau speaker
                if sentence_index < total_sentences:
                    # Ne pas prendre de phrase ici, on la prendra dans le segment suivant
                    pass
            
            # Calculer le nombre de phrases pour ce segment (proportionnel mais séquentiel)
            if diar_duration > 0 and total_speech_duration > 0:
                sentences_for_segment = (diar_duration / total_speech_duration) * total_sentences
                sentences_count = max(1, int(round(sentences_for_segment)))  # Au moins 1 phrase
            else:
                sentences_count = 0
            
            # Prendre les phrases suivantes dans l'ordre
            segment_sentences = []
            if sentences_count > 0 and sentence_index < total_sentences:
                end_index = min(sentence_index + sentences_count, total_sentences)
                segment_sentences = complete_sentences[sentence_index:end_index]
                sentence_index = end_index
            
            segment_text = " ".join(segment_sentences).strip()
            current_speaker = seg_speaker
            
            transcriptions.append({
                "start": diar_start,
                "end": diar_end,
                "speaker": seg_speaker,
                "text": segment_text
            })
        
        # Distribuer les phrases restantes
        if sentence_index < total_sentences:
            remaining_sentences = complete_sentences[sentence_index:]
            remaining_text = " ".join(remaining_sentences).strip()
            if transcriptions:
                transcriptions[-1]["text"] = (transcriptions[-1]["text"] + " " + remaining_text).strip()
                logger.info(f"Ajout de {len(remaining_sentences)} phrases restantes au dernier segment")
        
        segments_with_text = sum(1 for t in transcriptions if t.get('text', '').strip())
        logger.info(f"Distribution séquentielle terminée: {segments_with_text}/{len(transcriptions)} segments avec texte")
        
        return transcriptions
    
    def _fill_missing_segments_with_sequential(self, transcriptions: List[Dict[str, Any]],
                                              full_text: str,
                                              diarization_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Complète les segments sans texte avec distribution séquentielle
        """
        # Identifier les segments sans texte
        segments_without_text = [i for i, t in enumerate(transcriptions) 
                                if not t.get('text', '').strip()]
        
        if not segments_without_text:
            return transcriptions
        
        logger.info(f"Complétion de {len(segments_without_text)} segments sans texte")
        
        # Extraire le texte déjà utilisé (approximatif)
        used_text = " ".join([t.get('text', '') for t in transcriptions if t.get('text', '').strip()])
        
        # Calculer le texte restant (approximatif)
        # On prend le texte complet et on retire les parties déjà utilisées
        remaining_text = full_text
        # Note: Cette méthode est approximative, mais mieux que rien
        
        # Distribuer le texte restant aux segments vides
        sentences = re.split(r'([.!?])\s+', remaining_text)
        complete_sentences = []
        i = 0
        while i < len(sentences):
            sentence = sentences[i].strip()
            if i + 1 < len(sentences):
                sentence += sentences[i + 1]
                i += 2
            else:
                i += 1
            if sentence:
                complete_sentences.append(sentence)
        
        # Distribuer proportionnellement aux segments vides
        total_duration_empty = sum(diarization_segments[i].get('end', 0) - diarization_segments[i].get('start', 0)
                                  for i in segments_without_text)
        
        if total_duration_empty > 0:
            sentence_index = 0
            for idx in segments_without_text:
                seg = diarization_segments[idx]
                seg_duration = seg.get('end', 0) - seg.get('start', 0)
                
                if seg_duration > 0:
                    sentences_for_seg = int((seg_duration / total_duration_empty) * len(complete_sentences))
                    sentences_for_seg = max(1, sentences_for_seg)
                    
                    if sentence_index < len(complete_sentences):
                        end_idx = min(sentence_index + sentences_for_seg, len(complete_sentences))
                        seg_sentences = complete_sentences[sentence_index:end_idx]
                        transcriptions[idx]["text"] = " ".join(seg_sentences).strip()
                        sentence_index = end_idx
        
        return transcriptions
    
    def _validate_transcription_mapping(self, transcriptions: List[Dict[str, Any]],
                                       diarization_segments: List[Dict[str, Any]]):
        """
        Valide la cohérence du mapping et détecte les problèmes
        """
        issues = []
        
        # Vérifier le nombre de segments
        if len(transcriptions) != len(diarization_segments):
            issues.append(f"Nombre de segments différent: {len(transcriptions)} vs {len(diarization_segments)}")
        
        # Vérifier l'ordre chronologique
        for i in range(len(transcriptions) - 1):
            if transcriptions[i].get('start', 0) > transcriptions[i+1].get('start', 0):
                issues.append(f"Ordre chronologique cassé à l'index {i}")
        
        # Vérifier que les speakers correspondent
        for i, (trans, diar) in enumerate(zip(transcriptions, diarization_segments)):
            if trans.get('speaker') != diar.get('speaker'):
                issues.append(f"Speaker mismatch à l'index {i}: {trans.get('speaker')} vs {diar.get('speaker')}")
        
        # Vérifier les segments sans texte
        segments_without_text = sum(1 for t in transcriptions if not t.get('text', '').strip())
        if segments_without_text > len(transcriptions) * 0.2:  # Plus de 20% sans texte
            issues.append(f"Trop de segments sans texte: {segments_without_text}/{len(transcriptions)}")
        
        # Logger les problèmes
        if issues:
            logger.warning(f"Problèmes détectés dans le mapping: {len(issues)}")
            for issue in issues[:5]:  # Limiter à 5 pour éviter les logs trop longs
                logger.warning(f"  - {issue}")
        else:
            logger.info("Validation du mapping: OK")
    
    def _merge_consecutive_diarization_segments(self, diarization_segments: List[Dict[str, Any]], 
                                               max_gap_seconds: float = 5.0) -> List[Dict[str, Any]]:
        """
        Regroupe les segments consécutifs de diarisation du même speaker
        
        Args:
            diarization_segments: Liste des segments de diarisation avec start, end, speaker
            max_gap_seconds: Gap maximum en secondes entre deux segments pour les regrouper (défaut: 5s)
            
        Returns:
            list: Segments regroupés avec même structure
        """
        if not diarization_segments:
            return []
        
        # Trier les segments par timestamp pour s'assurer qu'ils sont dans l'ordre chronologique
        sorted_segments = sorted(diarization_segments, key=lambda x: x.get('start', 0))
        
        merged_segments = []
        current_group = None
        
        # Calculer la durée moyenne avant regroupement pour les logs
        avg_duration_before = sum(seg.get('end', 0) - seg.get('start', 0) for seg in sorted_segments) / len(sorted_segments) if sorted_segments else 0
        
        for i, seg in enumerate(sorted_segments):
            seg_start = seg.get('start', 0)
            seg_end = seg.get('end', 0)
            seg_speaker = seg.get('speaker', 'UNKNOWN')
            
            if current_group is None:
                # Premier segment, initialiser le groupe
                current_group = {
                    'start': seg_start,
                    'end': seg_end,
                    'speaker': seg_speaker
                }
            else:
                # Vérifier si on peut regrouper avec le groupe actuel
                current_speaker = current_group.get('speaker', 'UNKNOWN')
                current_end = current_group.get('end', 0)
                gap = seg_start - current_end
                
                # Vérifier qu'aucun autre speaker ne parle entre les deux segments
                has_other_speaker_between = False
                if gap > 0:
                    # Chercher s'il y a un segment d'un autre speaker entre current_end et seg_start
                    # Un segment est "entre" s'il chevauche l'intervalle [current_end, seg_start]
                    for other_seg in sorted_segments:
                        other_start = other_seg.get('start', 0)
                        other_end = other_seg.get('end', 0)
                        other_speaker = other_seg.get('speaker', 'UNKNOWN')
                        
                        # Vérifier si ce segment d'un autre speaker chevauche l'intervalle
                        # Un segment chevauche si : il commence avant seg_start ET se termine après current_end
                        if (other_speaker != current_speaker and 
                            other_start < seg_start and 
                            other_end > current_end):
                            has_other_speaker_between = True
                            logger.debug(f"Speaker {other_speaker} parle entre {current_speaker} [{current_end:.1f}s - {seg_start:.1f}s], pas de regroupement")
                            break
                
                # Regrouper si même speaker, gap <= max_gap_seconds, et aucun autre speaker entre les deux
                if (current_speaker == seg_speaker and 
                    gap <= max_gap_seconds and 
                    not has_other_speaker_between):
                    # Fusionner : garder le start du premier, mettre à jour le end avec le dernier
                    current_group['end'] = seg_end
                else:
                    # Finaliser le groupe actuel et commencer un nouveau groupe
                    merged_segments.append(current_group)
                    current_group = {
                        'start': seg_start,
                        'end': seg_end,
                        'speaker': seg_speaker
                    }
        
        # Ajouter le dernier groupe
        if current_group is not None:
            merged_segments.append(current_group)
        
        # Calculer la durée moyenne après regroupement pour les logs
        avg_duration_after = sum(seg.get('end', 0) - seg.get('start', 0) for seg in merged_segments) / len(merged_segments) if merged_segments else 0
        
        logger.info(f"Regroupement segments: {len(sorted_segments)} -> {len(merged_segments)} segments")
        logger.info(f"Durée moyenne avant: {avg_duration_before:.1f}s, après: {avg_duration_after:.1f}s")
        
        # Log les premiers segments regroupés pour déboguer
        if merged_segments:
            for i, merged_seg in enumerate(merged_segments[:3]):
                duration = merged_seg.get('end', 0) - merged_seg.get('start', 0)
                logger.debug(f"Segment regroupé {i+1}: [{merged_seg.get('start', 0):.1f}s - {merged_seg.get('end', 0):.1f}s] speaker={merged_seg.get('speaker', 'UNKNOWN')} durée={duration:.1f}s")
        
        return merged_segments
    
    def _distribute_text_by_linguistic_cues(self, full_text: str,
                                           diarization_segments: List[Dict[str, Any]],
                                           total_speech_duration: float) -> List[Dict[str, Any]]:
        """
        Distribue le texte complet selon les segments de diarisation en utilisant des indices linguistiques
        (ponctuation forte pour découper en phrases complètes)
        
        Args:
            full_text: Texte complet de la transcription
            diarization_segments: Segments de diarisation avec speakers (déjà regroupés)
            total_speech_duration: Durée totale de parole en secondes
            
        Returns:
            list: Segments mappés avec speaker et texte distribué par phrases complètes
        """
        logger.info(f"Distribution linguistique: {len(full_text)} caractères sur {len(diarization_segments)} segments")
        
        # Découper le texte en phrases basées sur la ponctuation forte (. ! ?)
        # Pattern: ponctuation forte suivie d'un espace ou fin de texte
        # On garde la ponctuation avec la phrase précédente
        sentence_pattern = r'([.!?])\s+'
        sentences = re.split(sentence_pattern, full_text)
        
        # Reconstruire les phrases complètes avec leur ponctuation
        complete_sentences = []
        i = 0
        while i < len(sentences):
            sentence = sentences[i].strip()
            if i + 1 < len(sentences):
                # Ajouter la ponctuation si présente
                punctuation = sentences[i + 1]
                sentence += punctuation
                i += 2
            else:
                i += 1
            
            if sentence:
                complete_sentences.append(sentence)
        
        # Filtrer les phrases vides
        complete_sentences = [s.strip() for s in complete_sentences if s.strip()]
        
        total_sentences = len(complete_sentences)
        logger.info(f"Découpage en phrases: {total_sentences} phrases détectées")
        
        if total_sentences == 0:
            logger.warning("Aucune phrase détectée dans le texte, utilisation de la distribution par mots")
            # Fallback: utiliser les mots si aucune phrase n'est détectée
            words = full_text.split()
            total_words = len(words)
            text_index = 0
            transcriptions = []
            
            for diar_seg in diarization_segments:
                diar_start = diar_seg.get('start', 0)
                diar_end = diar_seg.get('end', 0)
                diar_duration = diar_end - diar_start
                
                if diar_duration > 0 and total_speech_duration > 0:
                    words_for_segment = int((diar_duration / total_speech_duration) * total_words)
                else:
                    words_for_segment = 0
                
                if words_for_segment > 0 and text_index < total_words:
                    segment_words = words[text_index:text_index + words_for_segment]
                    segment_text = " ".join(segment_words)
                    text_index += words_for_segment
                else:
                    segment_text = ""
                
                transcriptions.append({
                    "start": diar_start,
                    "end": diar_end,
                    "speaker": diar_seg.get('speaker', 'UNKNOWN'),
                    "text": segment_text
                })
            
            # Ajouter les mots restants au dernier segment
            if text_index < total_words and transcriptions:
                remaining_words = words[text_index:]
                remaining_text = " ".join(remaining_words)
                transcriptions[-1]["text"] = (transcriptions[-1]["text"] + " " + remaining_text).strip()
            
            return transcriptions
        
        # Distribuer les phrases aux segments de diarisation proportionnellement à leur durée
        transcriptions = []
        sentence_index = 0
        
        for seg_idx, diar_seg in enumerate(diarization_segments):
            diar_start = diar_seg.get('start', 0)
            diar_end = diar_seg.get('end', 0)
            diar_duration = diar_end - diar_start
            
            # Calculer le nombre de phrases attendues pour ce segment (proportionnel à sa durée)
            if diar_duration > 0 and total_speech_duration > 0:
                sentences_for_segment = (diar_duration / total_speech_duration) * total_sentences
                # Arrondir pour avoir un nombre entier de phrases
                # Utiliser max(0, ...) pour éviter les valeurs négatives, mais permettre 0 pour les très petits segments
                sentences_count = max(0, int(round(sentences_for_segment)))
            else:
                sentences_count = 0
            
            # Extraire les phrases pour ce segment
            segment_sentences = []
            if sentences_count > 0 and sentence_index < total_sentences:
                # Prendre les phrases suivantes dans l'ordre
                end_index = min(sentence_index + sentences_count, total_sentences)
                segment_sentences = complete_sentences[sentence_index:end_index]
                sentence_index = end_index
            
            # Joindre les phrases avec un espace
            segment_text = " ".join(segment_sentences).strip()
            
            # Log pour les premiers segments
            if seg_idx < 3:
                logger.debug(f"Segment {seg_idx + 1}: [{diar_start:.1f}s - {diar_end:.1f}s] speaker={diar_seg.get('speaker', 'UNKNOWN')} -> {len(segment_sentences)} phrases, texte: '{segment_text[:80]}...'")
            
            transcriptions.append({
                "start": diar_start,
                "end": diar_end,
                "speaker": diar_seg.get('speaker', 'UNKNOWN'),
                "text": segment_text
            })
        
        # Distribuer les phrases restantes sur les derniers segments
        if sentence_index < total_sentences:
            remaining_sentences = complete_sentences[sentence_index:]
            remaining_text = " ".join(remaining_sentences).strip()
            if transcriptions:
                # Ajouter au dernier segment
                transcriptions[-1]["text"] = (transcriptions[-1]["text"] + " " + remaining_text).strip()
                logger.info(f"Ajout de {len(remaining_sentences)} phrases restantes au dernier segment")
        
        segments_with_text = sum(1 for t in transcriptions if t.get('text', '').strip())
        logger.info(f"Distribution linguistique terminée: {segments_with_text}/{len(transcriptions)} segments avec texte ({total_sentences} phrases distribuées)")
        
        return transcriptions
    
    def _distribute_text_by_diarization(self, full_text: str, 
                                       audio_segments: List[Dict[str, Any]],
                                       diarization_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Distribue le texte complet selon les segments de diarisation
        Utilisé quand l'API Mistral ne retourne pas de segments avec timestamps
        
        Args:
            full_text: Texte complet de la transcription
            audio_segments: Liste des segments audio découpés (avec start_time, end_time)
            diarization_segments: Segments de diarisation avec speakers
            
        Returns:
            list: Segments mappés avec speaker et texte distribué
        """
        logger.info(f"Distribution du texte complet ({len(full_text)} caractères) selon {len(diarization_segments)} segments de diarisation")
        
        # Regrouper les segments consécutifs du même speaker (gap max 5s, aucun autre speaker entre)
        merged_segments = self._merge_consecutive_diarization_segments(diarization_segments, max_gap_seconds=5.0)
        logger.info(f"Segments regroupés: {len(diarization_segments)} -> {len(merged_segments)}")
        
        # Utiliser merged_segments au lieu de diarization_segments pour la suite
        diarization_segments = merged_segments
        
        # Calculer la durée totale de l'audio
        total_duration = 0
        if audio_segments:
            last_segment = audio_segments[-1]
            total_duration = last_segment.get('end_time', 0)
        else:
            # Estimer depuis les segments de diarisation
            if diarization_segments:
                total_duration = max(seg.get('end', 0) for seg in diarization_segments)
        
        if total_duration == 0:
            logger.error("Impossible de déterminer la durée totale de l'audio")
            return [{"start": seg['start'], "end": seg['end'], "speaker": seg['speaker'], "text": ""} 
                   for seg in diarization_segments]
        
        # Calculer la durée totale de parole (somme des durées des segments de diarisation)
        total_speech_duration = sum(seg.get('end', 0) - seg.get('start', 0) for seg in diarization_segments)
        
        if total_speech_duration == 0:
            logger.error("Aucune durée de parole détectée dans les segments de diarisation")
            return [{"start": seg['start'], "end": seg['end'], "speaker": seg['speaker'], "text": ""} 
                   for seg in diarization_segments]
        
        # Distribuer le texte en utilisant des indices linguistiques (phrases complètes)
        # au lieu d'une distribution proportionnelle mot par mot
        transcriptions = self._distribute_text_by_linguistic_cues(
            full_text, 
            diarization_segments, 
            total_speech_duration
        )
        
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

