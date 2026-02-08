"""
Service unifié Voxtral Mini Transcribe V2 : transcription + diarisation en un seul appel API.
Remplace RunPod/Pyannote + Voxtral par un seul appel avec diarize=true.
Utilise l'API REST Mistral directement car le SDK mistralai peut ne pas exposer diarize/context_bias.
"""
import os
import json
import logging
import time
import requests
from pathlib import Path
from typing import Dict, List, Any, Optional

from core.interfaces import UnifiedTranscriptionService
from services.audio_segmenter import AudioSegmenter
from services.terminology_service import TerminologyService
from services.circuit_breaker import mistral_breaker

MISTRAL_TRANSCRIPTIONS_URL = "https://api.mistral.ai/v1/audio/transcriptions"

logger = logging.getLogger(__name__)

# Voxtral supporte jusqu'à 3h par requête ; on découpe en blocs de 2h30 pour marge
MAX_AUDIO_DURATION_SINGLE_REQUEST = 9000  # 2h30 en secondes


class VoxtralUnifiedService(UnifiedTranscriptionService):
    """
    Service unifié : transcription + diarisation via Voxtral Mini Transcribe V2 (diarize=true).
    Implémente DiarizationService et TranscriptionService.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("MISTRAL_API_KEY")
        if not self.api_key:
            raise ValueError("MISTRAL_API_KEY doit être fourni")
        self.model = os.getenv("VOXTRAL_TRANSCRIPTION_MODEL", "voxtral-mini-latest")
        self.fallback_model = "voxtral-mini-latest"
        logger.info(f"VoxtralUnifiedService: modèle {self.model} (transcription + diarisation)")
        self.segmenter = AudioSegmenter(max_segment_duration=MAX_AUDIO_DURATION_SINGLE_REQUEST)
        self.terminology_service = TerminologyService()

    def transcribe_and_diarize(
        self,
        audio_path: str,
        language: str = "fr",
        participants: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Transcription + diarisation en un seul appel API Voxtral.
        Retourne segments avec start, end, speaker, text et full_text.

        Args:
            audio_path: Chemin du fichier audio
            language: Langue (fr)
            participants: Liste des noms pour context_bias (améliore la reconnaissance)

        Returns:
            {"segments": [{"start", "end", "speaker", "text"}], "full_text": str}
        """
        duration = self.segmenter.get_audio_duration(audio_path)
        logger.info(f"Voxtral unifié: durée {duration:.1f}s")
        if duration <= 0:
            raise ValueError(f"Durée audio invalide: {audio_path}")

        context_bias_str = self._build_context_bias(participants)

        if duration <= MAX_AUDIO_DURATION_SINGLE_REQUEST:
            return self._transcribe_single(audio_path, language, context_bias_str)
        return self._transcribe_long(audio_path, language, duration, context_bias_str)

    def _build_context_bias(self, participants: Optional[List[str]]) -> str:
        """Construit la chaîne context_bias (max 100 mots)."""
        if not participants:
            return ""
        # Nettoyer et limiter
        words = []
        for p in participants[:50]:  # limiter à 50 noms
            w = str(p).strip().replace(",", " ").replace(";", " ")
            for part in w.split():
                if 2 <= len(part) <= 60 and part not in words:
                    words.append(part)
        return ",".join(words[:100])  # max 100 mots API

    def _transcribe_single(
        self,
        audio_path: str,
        language: str,
        context_bias_str: str,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """Un seul appel API pour un fichier <= 2h30. Utilise l'API REST directe pour diarize/context_bias."""
        retry_delay = 5
        for attempt in range(max_retries):
            try:
                data = {
                    "model": self.model,
                    "language": language,
                    "temperature": 0.0,
                    "diarize": "true",
                    "timestamp_granularities": '["segment"]',
                }
                if context_bias_str:
                    data["context_bias"] = context_bias_str

                with open(audio_path, "rb") as f:
                    files = {"file": (os.path.basename(audio_path), f, "audio/wav")}
                    with mistral_breaker:
                        resp = requests.post(
                            MISTRAL_TRANSCRIPTIONS_URL,
                            headers={"Authorization": f"Bearer {self.api_key}"},
                            data=data,
                            files=files,
                            timeout=600,
                        )
                resp.raise_for_status()
                response = resp.json()

                return self._normalize_response(response, 0.0)
            except requests.RequestException as e:
                resp = getattr(e, "response", None)
                if resp is not None:
                    if resp.status_code == 400 and self.model != self.fallback_model:
                        logger.warning(
                            f"FALLBACK: {self.model} non supporté, bascule vers {self.fallback_model}"
                        )
                        self.model = self.fallback_model
                        continue
                    if resp.status_code == 503 and attempt < max_retries - 1:
                        logger.warning(f"503, retry dans {retry_delay}s...")
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                raise
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Erreur transcription (tentative {attempt + 1}/{max_retries}): {e}")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                raise
        raise Exception("Échec transcription après toutes les tentatives")

    def _transcribe_long(
        self,
        audio_path: str,
        language: str,
        duration: float,
        context_bias_str: str,
    ) -> Dict[str, Any]:
        """Découpe en blocs de 2h30, transcrit chaque bloc, merge."""
        output_dir = Path(audio_path).parent
        audio_segments = self.segmenter.split_audio(
            audio_path, output_dir, MAX_AUDIO_DURATION_SINGLE_REQUEST
        )
        all_segments = []
        full_text_parts = []

        with self.segmenter.temporary_segments(audio_segments):
            for i, seg_info in enumerate(audio_segments):
                offset = seg_info["start_time"]
                logger.info(f"Voxtral unifié bloc {i+1}/{len(audio_segments)}: {offset:.0f}s - {seg_info['end_time']:.0f}s")
                try:
                    result = self._transcribe_single(
                        seg_info["path"], language, context_bias_str
                    )
                    for s in result.get("segments", []):
                        all_segments.append({
                            "start": s.get("start", 0) + offset,
                            "end": s.get("end", 0) + offset,
                            "speaker": s.get("speaker", "UNKNOWN"),
                            "text": s.get("text", ""),
                        })
                    if result.get("full_text"):
                        full_text_parts.append(result["full_text"])
                except Exception as e:
                    logger.error(f"Erreur bloc {i+1}: {e}")
                    raise

        full_text = " ".join(full_text_parts) if full_text_parts else ""
        full_text = self.terminology_service.correct_text(full_text)
        for s in all_segments:
            if s.get("text"):
                s["text"] = self.terminology_service.correct_text(s["text"])

        return {"segments": all_segments, "full_text": full_text}

    def _normalize_response(self, response: Any, offset: float = 0.0) -> Dict[str, Any]:
        """Convertit la réponse API en format standard."""
        full_text = getattr(response, "text", None) or (response.get("text", "") if isinstance(response, dict) else "")
        segments_raw = getattr(response, "segments", None) or (response.get("segments", []) if isinstance(response, dict) else [])

        segments = []
        for seg in segments_raw:
            if isinstance(seg, dict):
                s = seg
            else:
                s = {
                    "start": getattr(seg, "start", 0),
                    "end": getattr(seg, "end", 0),
                    "text": getattr(seg, "text", ""),
                    "speaker": getattr(seg, "speaker", None) or seg.get("speaker", "UNKNOWN"),
                }
            segments.append({
                "start": s.get("start", 0) + offset,
                "end": s.get("end", 0) + offset,
                "text": s.get("text", ""),
                "speaker": s.get("speaker", "UNKNOWN"),
            })

        full_text = self.terminology_service.correct_text(full_text)
        for s in segments:
            if s.get("text"):
                s["text"] = self.terminology_service.correct_text(s["text"])

        return {"segments": segments, "full_text": full_text}

    def diarize_audio(self, audio_path: str, session_id: str = None) -> Dict[str, Any]:
        """Implémentation DiarizationService : retourne uniquement les segments diarisation."""
        result = self.transcribe_and_diarize(audio_path, language="fr")
        return {"segments": result["segments"]}

    def transcribe_file_full(
        self,
        audio_path: str,
        language: str = "fr",
        participants_path: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Implémentation TranscriptionService : transcription complète avec speakers."""
        participants = None
        if participants_path and Path(participants_path).exists():
            try:
                from services.mistral_processor import extract_participants_from_pdf
                participants = extract_participants_from_pdf(Path(participants_path))
            except Exception as e:
                logger.warning(f"Impossible d'extraire participants pour context_bias: {e}")
        return self.transcribe_and_diarize(audio_path, language=language, participants=participants)

    def transcribe_audio(self, audio_path: str, language: str = "fr") -> Dict[str, Any]:
        """Implémentation TranscriptionService."""
        return self.transcribe_and_diarize(audio_path, language=language)
