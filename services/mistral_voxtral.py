"""
Service pour appeler directement l'API Mistral AI (Voxtral) pour la transcription
Alternative au worker RunPod si vous préférez appeler directement Mistral AI

Refactorisé pour utiliser les modules:
- audio_segmenter.py : Découpage audio
- transcription_mapper.py : Mapping avec diarisation
- transcription_aligner.py : Alignement et distribution du texte
"""
import os
import json
import logging
import time
import base64
from pathlib import Path
from typing import Dict, List, Any, Optional
from mistralai import Mistral
from mistralai.models import SDKError

# Import des modules refactorisés
from services.audio_segmenter import AudioSegmenter
from services.transcription_mapper import TranscriptionMapper
from services.transcription_aligner import TranscriptionAligner
from services.circuit_breaker import mistral_breaker, CircuitBreakerOpen
from services.terminology_service import TerminologyService

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
        self.model = os.getenv("VOXTRAL_TRANSCRIPTION_MODEL", "voxtral-mini-latest")
        self.fallback_model = "voxtral-mini-latest"
        logger.info(f"Modèle de transcription configuré: {self.model}")
        # Limite de contexte: 16384 tokens
        self.max_segment_duration = 600  # 10 minutes en secondes
        self.max_audio_duration_before_split = 480  # 8 minutes
        
        # Configuration pour Voxtral-Small en mode chat (méthode principale)
        self.use_voxtral_small_chat = True
        self.max_duration_for_voxtral_small_chat = 900  # 15 minutes
        self.voxtral_small_segment_duration = 600  # 10 minutes par segment
        
        # Initialiser les modules de support
        self.segmenter = AudioSegmenter(max_segment_duration=self.max_segment_duration)
        self.mapper = TranscriptionMapper()
        self.aligner = TranscriptionAligner()
        self.terminology_service = TerminologyService()
    
    def _call_api(self, api_func, *args, **kwargs):
        """
        Wrapper pour les appels API avec circuit breaker
        
        Args:
            api_func: Fonction API à appeler
            *args, **kwargs: Arguments de la fonction
            
        Returns:
            Résultat de l'appel API
            
        Raises:
            CircuitBreakerOpen: Si l'API est indisponible
        """
        with mistral_breaker:
            return api_func(*args, **kwargs)
    
    def transcribe_audio(self, audio_path: str, 
                        diarization_segments: List[Dict[str, Any]],
                        language: str = "fr") -> Dict[str, Any]:
        """
        Nouvelle implémentation Text-First :
        1. Transcrit tout l'audio (Master Text) pour garantir le verbatim
        2. Aligne avec la diarisation (Master Time) pour attribuer les locuteurs
        
        Args:
            audio_path: Chemin du fichier audio local
            diarization_segments: Segments de diarisation pour mapper les speakers
            language: Langue de l'audio (défaut: "fr")
            
        Returns:
            dict: Transcription avec segments mappés aux speakers
        """
        try:
            # 1. Transcription brute (Text-First)
            logger.info("Démarrage transcription Text-First (indépendante de la diarisation)")
            raw_transcription = self.transcribe_file_full(audio_path, language)
            
            # 2. Alignement
            logger.info(f"Alignement : Fusion de {len(raw_transcription['segments'])} segments texte avec {len(diarization_segments)} segments diarisation")
            aligned_segments = self.aligner.align_strict_improved(
                raw_transcription['segments'],
                diarization_segments,
                raw_transcription['full_text']
            )
            
            # 3. Validation
            self.mapper.validate_mapping(aligned_segments, diarization_segments)
            
            return {
                "segments": aligned_segments,
                "full_text": raw_transcription['full_text']
            }
            
        except Exception as e:
            logger.error(f"Erreur lors de la transcription Text-First: {e}", exc_info=True)
            raise

    def transcribe_file_full(self, audio_path: str, language: str = "fr") -> Dict[str, Any]:
        """
        Transcrit le fichier audio complet sans tenir compte de la diarisation.
        Gère le découpage automatique si nécessaire.
        
        Args:
            audio_path: Chemin du fichier audio
            language: Langue (fr)
            
        Returns:
            dict: {
                "full_text": str,
                "segments": List[Dict]  # Segments Mistral bruts avec timestamps
            }
        """
        duration = self.segmenter.get_audio_duration(audio_path)
        logger.info(f"Transcription brute - Durée: {duration:.1f}s")
        
        result = {}
        if duration <= self.max_audio_duration_before_split:
            result = self._transcribe_segment(audio_path, language)
        else:
            result = self._transcribe_long_audio_raw(audio_path, language)
            
        # Application de la correction terminologique
        if result.get('full_text'):
            result['full_text'] = self.terminology_service.correct_text(result['full_text'])
            
        if result.get('segments'):
            for seg in result['segments']:
                if seg.get('text'):
                    seg['text'] = self.terminology_service.correct_text(seg['text'])
                    
        return result

    def _transcribe_long_audio_raw(self, audio_path: str, language: str) -> Dict[str, Any]:
        """
        Découpe et transcrit un long fichier audio (mode brut)
        """
        output_dir = Path(audio_path).parent
        # Découpage en blocs de 10 min
        audio_segments = self.segmenter.split_audio(
            audio_path, output_dir, self.voxtral_small_segment_duration
        )
        
        all_segments = []
        full_text_parts = []
        
        # Utiliser le contextmanager pour le nettoyage automatique
        with self.segmenter.temporary_segments(audio_segments):
            for i, seg_info in enumerate(audio_segments):
                logger.info(f"Traitement bloc {i+1}/{len(audio_segments)} ({seg_info['start_time']:.0f}s - {seg_info['end_time']:.0f}s)")
                
                try:
                    # Transcription du bloc
                    result = self._transcribe_segment(seg_info['path'], language)
                    
                    # Ajustement des timestamps
                    offset = seg_info['start_time']
                    for seg in result.get('segments', []):
                        # Normalisation des objets segments
                        s_start = getattr(seg, 'start', seg.get('start', 0))
                        s_end = getattr(seg, 'end', seg.get('end', 0))
                        s_text = getattr(seg, 'text', seg.get('text', ''))
                        
                        all_segments.append({
                            "start": s_start + offset,
                            "end": s_end + offset,
                            "text": s_text,
                            "speaker": "UNKNOWN" # Sera rempli par l'alignement
                        })
                    
                    if result.get('text'):
                        full_text_parts.append(result['text'])
                        
                except Exception as e:
                    logger.error(f"Erreur transcription bloc {i+1}: {e}")
                    # On continue avec les autres blocs pour sauver ce qu'on peut
                    continue
                    
        return {
            "segments": all_segments,
            "full_text": " ".join(full_text_parts)
        }

    
    def _get_audio_url(self, audio_path: str) -> str:
        """
        Génère l'URL publique de l'audio pour l'API Mistral
        
        Args:
            audio_path: Chemin local du fichier audio
            
        Returns:
            str: URL publique du fichier audio
        """
        # Priorité: DOKPLOY_PUBLIC_DOMAIN > RAILWAY_PUBLIC_DOMAIN > APP_BASE_URL > localhost
        app_base_url = (os.getenv('DOKPLOY_PUBLIC_DOMAIN') or 
                       os.getenv('RAILWAY_PUBLIC_DOMAIN') or 
                       os.getenv('APP_BASE_URL', 'http://localhost:5000'))
        if not app_base_url.startswith('http'):
            app_base_url = f"https://{app_base_url}"
        
        path_parts = Path(audio_path).parts
        if 'uploads' in path_parts:
            idx = path_parts.index('uploads')
            return f"{app_base_url}/files/{'/'.join(path_parts[idx+1:])}"
        
        return f"{app_base_url}/files/{Path(audio_path).name}"
    
    def _encode_audio_base64(self, audio_path: str) -> str:
        """
        Encode un fichier audio en base64 pour l'API Mistral chat multimodal
        
        Args:
            audio_path: Chemin local du fichier audio
            
        Returns:
            str: Audio encodé en base64
        """
        with open(audio_path, "rb") as f:
            content = f.read()
        return base64.b64encode(content).decode('utf-8')
    
    def _transcribe_with_voxtral_small_chat(self, audio_path: str,
                                           audio_url: Optional[str],
                                           diarization_segments: List[Dict[str, Any]],
                                           language: str = "fr") -> Dict[str, Any]:
        """
        Transcription avec Voxtral-Small en mode chat
        Fournit l'audio encodé en base64 + segments de diarisation comme contexte
        
        Args:
            audio_path: Chemin local du fichier audio
            audio_url: (non utilisé, conservé pour compatibilité)
            diarization_segments: Segments de diarisation
            language: Langue de l'audio
            
        Returns:
            dict: Transcription avec segments mappés aux speakers
        """
        try:
            diarization_context = self._format_diarization_for_prompt(diarization_segments)
            prompt = self._build_transcription_prompt(diarization_context)
            
            # Encoder l'audio en base64 (requis par l'API Mistral)
            logger.info(f"Encodage audio en base64: {audio_path}")
            audio_base64 = self._encode_audio_base64(audio_path)
            logger.info(f"Audio encodé ({len(audio_base64)} caractères base64)")
            
            with mistral_breaker:
                response = self.client.chat.complete(
                    model="voxtral-small-latest",
                    messages=[{
                        "role": "user",
                        "content": [
                            {
                                "type": "input_audio",
                                "input_audio": audio_base64,
                            },
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }],
                    temperature=0.0,
                    response_format={"type": "json_object"}
                )
            
            result_content = response.choices[0].message.content
            result = json.loads(result_content)
            
            transcriptions = result.get('segments', [])
            full_text = result.get('full_text', '')
            
            logger.info(f"Voxtral-Small chat: {len(transcriptions)} segments reçus pour {len(diarization_segments)} segments de diarisation")
            
            # Utiliser l'alignement strict amélioré
            transcriptions = self.aligner.align_strict_improved(
                transcriptions, diarization_segments, full_text
            )
            
            # Validation finale
            self.mapper.validate_mapping(transcriptions, diarization_segments)
            
            return {
                "segments": transcriptions,
                "full_text": full_text
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"Erreur parsing JSON de Voxtral-Small: {e}")
            if 'result_content' in locals():
                logger.error(f"Réponse reçue (premiers 500 caractères): {result_content[:500]}")
            return self._transcribe_audio_classic(audio_path, diarization_segments, language)
        except Exception as e:
            logger.error(f"Erreur avec Voxtral-Small chat: {e}", exc_info=True)
            return self._transcribe_audio_classic(audio_path, diarization_segments, language)
    
    def _build_transcription_prompt(self, diarization_context: str) -> str:
        """
        Construit le prompt pour la transcription
        
        Args:
            diarization_context: Contexte de diarisation formaté
            
        Returns:
            str: Prompt complet
        """
        return f"""Tu es un assistant expert en transcription de réunions.

TÂCHE :
Transcris l'audio fourni en respectant STRICTEMENT et EXACTEMENT les segments de diarisation fournis.
Chaque segment de diarisation correspond à une intervention d'un locuteur spécifique.

SEGMENTS DE DIARISATION (ordre chronologique) :
{diarization_context}

INSTRUCTIONS CRITIQUES (STRICTES - À RESPECTER ABSOLUMENT) :
1. Tu DOIS retourner EXACTEMENT un segment de transcription pour CHAQUE segment de diarisation fourni
2. INTERDICTION ABSOLUE de regrouper ou fusionner des segments, même s'ils ont le même speaker
3. INTERDICTION ABSOLUE de sauter ou ignorer un segment de diarisation
4. Si un segment de diarisation est silencieux ou très court (< 0.5s), retourne quand même un segment avec texte vide ""
5. Les timestamps (start/end) doivent correspondre EXACTEMENT aux segments de diarisation fournis
6. Le speaker doit correspondre EXACTEMENT au speaker du segment de diarisation
7. L'ordre des segments doit être IDENTIQUE à l'ordre des segments de diarisation fournis
8. Le texte doit être la transcription verbatim (mot à mot) de ce qui est dit pendant ce segment temporel précis
9. Si une phrase commence dans un segment et se termine dans le suivant, répartis-la intelligemment entre les deux segments

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

VALIDATION OBLIGATOIRE :
- Le nombre de segments retournés DOIT être EXACTEMENT égal au nombre de segments de diarisation fournis
- Chaque segment de diarisation DOIT avoir un segment de transcription correspondant avec les mêmes timestamps
- Aucun regroupement, fusion ou omission n'est autorisé
"""
    
    def _format_diarization_for_prompt(self, diarization_segments: List[Dict[str, Any]]) -> str:
        """
        Formate les segments de diarisation pour le prompt
        
        Args:
            diarization_segments: Liste des segments de diarisation
            
        Returns:
            str: Texte formaté pour le prompt
        """
        lines = ["Voici les segments de diarisation (détection automatique des locuteurs) :", ""]
        
        for i, seg in enumerate(diarization_segments, 1):
            start = seg.get('start', 0)
            end = seg.get('end', 0)
            speaker = seg.get('speaker', 'UNKNOWN')
            duration = end - start
            
            start_str = self._format_time(start)
            end_str = self._format_time(end)
            
            lines.append(f"Segment {i}: [{start_str} - {end_str}] {speaker} (durée: {duration:.1f}s)")
        
        return "\n".join(lines)
    
    def _format_time(self, seconds: float) -> str:
        """Formate les secondes en HH:MM:SS"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    def _transcribe_long_audio_with_voxtral_small(self, audio_path: str,
                                                  audio_url: Optional[str],
                                                  diarization_segments: List[Dict[str, Any]],
                                                  language: str = "fr") -> Dict[str, Any]:
        """
        Transcription de fichiers longs avec découpage intelligent
        
        Args:
            audio_path: Chemin du fichier audio complet
            audio_url: URL publique du fichier audio
            diarization_segments: Segments de diarisation complets
            language: Langue de l'audio
            
        Returns:
            dict: Transcription complète avec segments mappés
        """
        output_dir = Path(audio_path).parent
        
        # Découper l'audio en segments
        audio_segments = self.segmenter.split_audio(
            audio_path, output_dir, self.voxtral_small_segment_duration
        )
        
        all_transcriptions = []
        full_text_parts = []
        
        # Utiliser le contextmanager pour garantir la suppression des fichiers temporaires
        with self.segmenter.temporary_segments(audio_segments):
            for i, seg_info in enumerate(audio_segments):
                seg_start = seg_info['start_time']
                seg_end = seg_info['end_time']
                
                logger.info(f"Traitement segment {i+1}/{len(audio_segments)}: {seg_start:.1f}s - {seg_end:.1f}s")
                
                # Filtrer les segments de diarisation pour ce segment audio
                adjusted_diarization = self.segmenter.filter_diarization_for_segment(
                    diarization_segments, seg_start, seg_end, adjust_timestamps=True
                )
                
                if not adjusted_diarization:
                    logger.warning(f"Aucun segment de diarisation pour le segment audio {i+1}")
                    continue
                
                try:
                    segment_result = self._transcribe_with_voxtral_small_chat(
                        seg_info['path'],
                        None,  # Sera généré automatiquement
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
                    
                    # Mapper avec diarisation
                    mistral_segments = fallback_result.get('segments', [])
                    for seg in mistral_segments:
                        seg['start'] += seg_start
                        seg['end'] += seg_start
                    
                    segment_transcriptions = self._map_hybrid(
                        mistral_segments, 
                        self.segmenter.filter_diarization_for_segment(
                            diarization_segments, seg_start, seg_end, adjust_timestamps=False
                        ),
                        fallback_result.get('text', '')
                    )
                    
                    for trans in segment_transcriptions:
                        all_transcriptions.append(trans)
                    
                    if fallback_result.get('text'):
                        full_text_parts.append(fallback_result['text'])
            
            # Trier par timestamp
            all_transcriptions.sort(key=lambda x: x.get('start', 0))
            
            # Validation finale
            self.mapper.validate_mapping(all_transcriptions, diarization_segments)
            
            return {
                "segments": all_transcriptions,
                "full_text": " ".join(full_text_parts)
            }
    
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
        duration = self.segmenter.get_audio_duration(audio_path)
        if duration <= self.max_audio_duration_before_split:
            return self._transcribe_short_audio(audio_path, diarization_segments, language)
        else:
            output_dir = Path(audio_path).parent
            return self._transcribe_long_audio(audio_path, diarization_segments, language, output_dir)
    
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
                    with mistral_breaker:
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
                
                full_text = ""
                if hasattr(transcription_response, 'text'):
                    full_text = transcription_response.text
                elif isinstance(transcription_response, dict):
                    full_text = transcription_response.get('text', '')
                
                segments = []
                if hasattr(transcription_response, 'segments'):
                    segments = transcription_response.segments
                elif isinstance(transcription_response, dict):
                    segments = transcription_response.get('segments', [])
                
                # Convertir les segments en listes de dicts
                segments_list = []
                for seg in segments:
                    if isinstance(seg, dict):
                        segments_list.append(seg)
                    else:
                        segments_list.append({
                            'start': getattr(seg, 'start', 0),
                            'end': getattr(seg, 'end', 0),
                            'text': getattr(seg, 'text', '')
                        })
                
                logger.debug(f"Transcription segment: {len(segments_list)} segments, texte: {len(full_text)} caractères")
                
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
                        if self.model != self.fallback_model:
                            logger.warning(
                                f"FALLBACK: Modèle {self.model} non supporté pour transcription, "
                                f"bascule vers {self.fallback_model}"
                            )
                            self.model = self.fallback_model
                            continue
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
    
    def _transcribe_short_audio(self, audio_path: str,
                               diarization_segments: List[Dict[str, Any]],
                               language: str = "fr") -> Dict[str, Any]:
        """
        Transcrit un fichier audio court (< 8 minutes) directement
        """
        max_retries = 3
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Transcription directe avec {self.model} (tentative {attempt + 1}/{max_retries}): {audio_path}")
                
                with open(audio_path, "rb") as f:
                    with mistral_breaker:
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
                
                segments = []
                if hasattr(transcription_response, 'segments'):
                    segments = transcription_response.segments
                elif isinstance(transcription_response, dict):
                    segments = transcription_response.get('segments', [])
                
                # Convertir les segments
                mistral_segments = []
                for seg in segments:
                    if isinstance(seg, dict):
                        mistral_segments.append(seg)
                    else:
                        mistral_segments.append({
                            'start': getattr(seg, 'start', 0),
                            'end': getattr(seg, 'end', 0),
                            'text': getattr(seg, 'text', '')
                        })
                
                logger.info(f"Transcription directe: {len(mistral_segments)} segments Mistral reçus")
                
                # Utiliser le mapping hybride amélioré
                full_text = transcription_response.text if hasattr(transcription_response, 'text') else ""
                transcriptions = self._map_hybrid(
                    mistral_segments, diarization_segments, full_text
                )
                
                result = {
                    "segments": transcriptions,
                    "full_text": full_text
                }
                
                logger.info(f"Transcription terminée: {len(transcriptions)} segments")
                return result
                
            except SDKError as e:
                if hasattr(e, 'http_res') and e.http_res and e.http_res.status_code == 400:
                    if self.model != self.fallback_model:
                        logger.warning(
                            f"FALLBACK: Modèle {self.model} non supporté pour transcription, "
                            f"bascule vers {self.fallback_model}"
                        )
                        self.model = self.fallback_model
                        continue
                    if "too large" in str(e).lower():
                        logger.warning(f"Fichier trop grand (400), découpage automatique...")
                        output_dir = Path(audio_path).parent
                        return self._transcribe_long_audio(audio_path, diarization_segments, language, output_dir)
                    logger.error(f"Erreur 400 lors de la transcription: {e}")
                    raise
                
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
        
        # Découper l'audio
        audio_segments = self.segmenter.split_audio(audio_path, output_dir)
        
        # Utiliser le contextmanager pour garantir la suppression des fichiers temporaires
        with self.segmenter.temporary_segments(audio_segments):
            
            # Transcrire chaque segment
            for i, seg_info in enumerate(audio_segments):
                logger.info(f"Transcription du segment {i+1}/{len(audio_segments)}: {seg_info['start_time']:.1f}s - {seg_info['end_time']:.1f}s")
                
                seg_result = self._transcribe_segment(seg_info['path'], language)
                
                # Ajuster les timestamps
                offset = seg_info['start_time']
                segment_mistral_segments = seg_result.get('segments', [])
                
                for seg in segment_mistral_segments:
                    if isinstance(seg, dict):
                        seg_start = seg.get('start', 0)
                        seg_end = seg.get('end', 0)
                        seg_text = seg.get('text', '')
                    else:
                        seg_start = getattr(seg, 'start', 0)
                        seg_end = getattr(seg, 'end', 0)
                        seg_text = getattr(seg, 'text', '')
                    
                    adjusted_seg = {
                        'start': seg_start + offset,
                        'end': seg_end + offset,
                        'text': seg_text.strip() if seg_text else ''
                    }
                    all_mistral_segments.append(adjusted_seg)
                
                if seg_result.get('text'):
                    full_text_parts.append(seg_result['text'])
            
            # Utiliser le mapping hybride amélioré
            full_text = " ".join(full_text_parts) if full_text_parts else ""
            transcriptions = self._map_hybrid(
                all_mistral_segments, diarization_segments, full_text
            )
            
            result = {
                "segments": transcriptions,
                "full_text": " ".join(full_text_parts)
            }
            
            logger.info(f"Transcription terminée: {len(transcriptions)} segments (depuis {len(audio_segments)} segments audio)")
            return result
    
    def _map_hybrid(self, mistral_segments: List[Dict[str, Any]],
                   diarization_segments: List[Dict[str, Any]],
                   full_text: str = "") -> List[Dict[str, Any]]:
        """
        Mapping hybride amélioré avec validation
        
        Stratégie:
        1. Si timestamps Mistral disponibles → mapping par chevauchement temporel
        2. Si timestamps partiels → combinaison des deux méthodes
        3. Si seulement texte complet → distribution séquentielle
        4. Validation et correction des incohérences
        
        Args:
            mistral_segments: Segments de transcription
            diarization_segments: Segments de diarisation
            full_text: Texte complet
            
        Returns:
            list: Segments mappés
        """
        logger.info(f"Mapping hybride: {len(mistral_segments)} segments Mistral, "
                   f"{len(diarization_segments)} segments diarisation")
        
        diarization_segments = sorted(diarization_segments, key=lambda x: x.get('start', 0))
        
        # Cas 1: Segments Mistral avec timestamps disponibles
        mistral_with_timestamps = [m for m in mistral_segments 
                                   if m.get('start') is not None and m.get('end') is not None]
        
        if len(mistral_with_timestamps) >= len(diarization_segments) * 0.5:
            logger.info("Utilisation du mapping temporel (timestamps disponibles)")
            transcriptions = self.mapper.map_with_unique_attribution(
                mistral_with_timestamps, diarization_segments
            )
            
            # Validation et complétion si nécessaire
            segments_without_text = [t for t in transcriptions if not t.get('text', '').strip()]
            if segments_without_text and full_text:
                logger.warning(f"{len(segments_without_text)} segments sans texte, complétion...")
                transcriptions = self.aligner.fill_missing_segments(
                    transcriptions, full_text, diarization_segments
                )
        else:
            logger.info("Utilisation de la distribution séquentielle (peu de timestamps)")
            transcriptions = self.aligner.distribute_by_chronological_order(
                full_text, diarization_segments
            )
        
        # Validation finale
        self.mapper.validate_mapping(transcriptions, diarization_segments)
        
        return transcriptions
    
