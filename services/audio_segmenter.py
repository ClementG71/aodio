"""
Service de découpage audio en segments
Extrait de mistral_voxtral.py pour une meilleure modularité
"""
import os
import logging
import subprocess
import uuid
from pathlib import Path
from contextlib import contextmanager
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# Sample rate pour les segments (aligné avec AudioProcessor, meilleure qualité pour Voxtral)
AUDIO_SEGMENT_SAMPLE_RATE = 44100


class AudioSegmenter:
    """Gère le découpage des fichiers audio en segments"""
    
    def __init__(self, max_segment_duration: float = 600, sample_rate: int = None):
        """
        Initialise le segmenteur audio
        
        Args:
            max_segment_duration: Durée maximale d'un segment en secondes (défaut: 10 min)
            sample_rate: Taux d'échantillonnage des segments (défaut: 44100)
        """
        self.max_segment_duration = max_segment_duration
        self.sample_rate = sample_rate if sample_rate is not None else AUDIO_SEGMENT_SAMPLE_RATE
    
    @contextmanager
    def temporary_segments(self, segments: List[Dict[str, Any]]):
        """
        Context manager pour gérer les segments audio temporaires
        Garantit la suppression des fichiers même en cas d'erreur
        
        Args:
            segments: Liste des segments avec 'path' pour chaque segment
            
        Yields:
            list: Liste des segments (inchangée)
        """
        try:
            yield segments
        finally:
            # Nettoyer les segments temporaires dans tous les cas
            for seg_info in segments:
                try:
                    seg_path = seg_info.get('path')
                    if seg_path and os.path.exists(seg_path):
                        os.remove(seg_path)
                        logger.debug(f"Segment temporaire supprimé: {seg_path}")
                except Exception as e:
                    logger.warning(f"Impossible de supprimer le segment {seg_info.get('path', 'unknown')}: {e}")
    
    def get_audio_duration(self, audio_path: str) -> float:
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
    
    def split_audio(self, audio_path: str, output_dir: Path, 
                    segment_duration: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Découpe un fichier audio en segments
        
        Args:
            audio_path: Chemin du fichier audio complet
            output_dir: Dossier où sauvegarder les segments
            segment_duration: Durée de chaque segment en secondes (défaut: max_segment_duration)
            
        Returns:
            list: Liste de dict avec 'path', 'start_time', 'end_time' pour chaque segment
        """
        # Utiliser la durée fournie ou la durée par défaut
        if segment_duration is None:
            segment_duration = self.max_segment_duration
        
        segments = []
        duration = self.get_audio_duration(audio_path)
        
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
            
            # Découper avec ffmpeg (même sample rate que le pipeline pour qualité Voxtral)
            cmd = [
                'ffmpeg',
                '-threads', '0',
                '-i', str(audio_path),
                '-ss', str(start_time),
                '-t', str(seg_duration),
                '-acodec', 'pcm_s16le',
                '-ar', str(self.sample_rate),
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
    
    def filter_diarization_for_segment(self, diarization_segments: List[Dict[str, Any]],
                                       seg_start: float, seg_end: float,
                                       adjust_timestamps: bool = True) -> List[Dict[str, Any]]:
        """
        Filtre les segments de diarisation pour un segment audio donné
        
        Args:
            diarization_segments: Segments de diarisation complets
            seg_start: Début du segment audio
            seg_end: Fin du segment audio
            adjust_timestamps: Si True, ajuste les timestamps relatifs au segment
            
        Returns:
            list: Segments de diarisation filtrés (et ajustés si demandé)
        """
        relevant = [
            d for d in diarization_segments
            if d.get('start', 0) < seg_end and d.get('end', 0) > seg_start
        ]
        
        if not adjust_timestamps:
            return relevant
        
        # Ajuster les timestamps relatifs au début du segment
        adjusted = []
        for d in relevant:
            rel_start = max(0, d.get('start', 0) - seg_start)
            rel_end = min(seg_end - seg_start, d.get('end', 0) - seg_start)
            
            adjusted.append({
                'start': rel_start,
                'end': rel_end,
                'speaker': d.get('speaker', 'UNKNOWN')
            })
        
        return adjusted
