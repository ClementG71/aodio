"""
Service de traitement audio amélioré : normalisation, réduction de bruit, filtrage
"""
import os
import logging
import subprocess
from pathlib import Path
from pydub import AudioSegment
import librosa
import soundfile as sf
import numpy as np

logger = logging.getLogger(__name__)


class AudioProcessor:
    """Traite les fichiers audio avec amélioration de la qualité"""
    
    def __init__(self):
        self.target_sample_rate = 16000  # Taux d'échantillonnage cible
        self.target_channels = 1  # Mono
        self.target_bitrate = '128k'  # Bitrate pour compression
        
        # Paramètres de normalisation améliorés
        self.normalize_lufs = -16.0  # Niveau cible en LUFS (Loudness Units Full Scale)
        self.normalize_tp = -1.5     # True Peak
        self.normalize_lra = 11     # Loudness Range
        
        # Paramètres de réduction de bruit (optionnel, peut être désactivé)
        self.enable_noise_reduction = True
        self.noise_reduction_strength = 0.5  # 0.0 à 1.0
    
    def process_audio(self, input_path, output_path, enable_enhancement=True):
        """
        Traite un fichier audio avec amélioration de la qualité
        
        Args:
            input_path: Chemin du fichier audio d'entrée
            output_path: Chemin du fichier audio de sortie
            enable_enhancement: Activer les améliorations (normalisation, réduction de bruit)
            
        Returns:
            str: Chemin du fichier traité
        """
        try:
            logger.info(f"Traitement audio: {input_path} -> {output_path}")
            
            # Étape 1: Analyse du fichier d'entrée
            audio_info = self._get_audio_info(input_path)
            if audio_info:
                logger.info(f"Audio d'entrée: {audio_info['sample_rate']}Hz, "
                          f"{audio_info['channels']} canaux, "
                          f"{audio_info['duration_seconds']:.1f}s")
            
            # Étape 2: Traitement avec ffmpeg (méthode optimale)
            if enable_enhancement:
                return self._process_with_ffmpeg_enhanced(input_path, output_path)
            else:
                return self._process_with_ffmpeg_basic(input_path, output_path)
                
        except Exception as e:
            logger.error(f"Erreur lors du traitement audio: {str(e)}", exc_info=True)
            # Fallback sur méthode basique
            logger.info("Tentative avec méthode basique en fallback...")
            return self._process_with_ffmpeg_basic(input_path, output_path)
    
    def _process_with_ffmpeg_enhanced(self, input_path, output_path):
        """
        Traitement audio amélioré avec ffmpeg
        - Normalisation du volume (dynaudnorm)
        - Réduction de bruit (highpass + lowpass)
        - Filtrage pour améliorer la qualité de la parole
        """
        try:
            # Méthode optimisée : utiliser dynaudnorm (normalisation dynamique, plus rapide)
            # + filtres pour améliorer la qualité
            cmd = [
                'ffmpeg',
                '-threads', '0',
                '-i', str(input_path),
                
                # Filtres audio (appliqués dans l'ordre)
                '-af', self._build_audio_filters(),
                
                # Paramètres de sortie
                '-ar', str(self.target_sample_rate),
                '-ac', str(self.target_channels),
                '-acodec', 'pcm_s16le',
                '-loglevel', 'error',
                '-y',
                str(output_path)
            ]
            
            logger.info(f"Traitement audio amélioré avec ffmpeg...")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600
            )
            
            if result.returncode != 0:
                logger.warning(f"ffmpeg amélioré a échoué: {result.stderr}")
                # Fallback sur méthode basique
                return self._process_with_ffmpeg_basic(input_path, output_path)
            
            logger.info(f"Audio traité avec succès (ffmpeg amélioré): {output_path}")
            
            # Vérification de la qualité
            self._verify_audio_quality(output_path)
            
            return output_path
            
        except subprocess.TimeoutExpired:
            logger.error("Timeout lors du traitement amélioré")
            return self._process_with_ffmpeg_basic(input_path, output_path)
        except Exception as e:
            logger.warning(f"Erreur avec traitement amélioré: {e}")
            return self._process_with_ffmpeg_basic(input_path, output_path)
    
    def _build_audio_filters(self):
        """
        Construit la chaîne de filtres audio pour améliorer la qualité
        
        Filtres appliqués (dans l'ordre):
        1. highpass: Supprime les basses fréquences (< 80Hz) - bruit de fond
        2. lowpass: Supprime les hautes fréquences (> 8000Hz) - réduit le bruit
        3. dynaudnorm: Normalisation dynamique du volume
        """
        filters = []
        
        # 1. Filtre passe-haut : supprime les basses fréquences (bruit de fond)
        filters.append(f"highpass=f=80")
        
        # 2. Filtre passe-bas : supprime les hautes fréquences (bruit aigu)
        # Pour la parole, on garde jusqu'à 8kHz (suffisant pour 16kHz sample rate)
        filters.append(f"lowpass=f=8000")
        
        # 3. Normalisation dynamique du volume
        # Paramètres: g=5 (gain), p=0.95 (target level), m=10.0 (max gain), r=0.0 (ratio)
        filters.append("dynaudnorm=g=5:p=0.95:m=10.0:r=0.0")
        
        return ",".join(filters)
    
    def _process_with_ffmpeg_basic(self, input_path, output_path):
        """
        Traitement audio basique (méthode actuelle, rapide)
        """
        cmd = [
            'ffmpeg',
            '-threads', '0',
            '-i', str(input_path),
            '-ar', str(self.target_sample_rate),
            '-ac', str(self.target_channels),
            '-acodec', 'pcm_s16le',
            '-loglevel', 'error',
            '-y',
            str(output_path)
        ]
        
        logger.info(f"Exécution de ffmpeg (basique): {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600
        )
        
        if result.returncode != 0:
            logger.warning(f"ffmpeg a retourné une erreur: {result.stderr}")
            return self._process_with_pydub(input_path, output_path)
        
        logger.info(f"Audio traité avec succès (ffmpeg basique): {output_path}")
        return output_path
    
    def _verify_audio_quality(self, output_path):
        """
        Vérifie la qualité de l'audio traité
        """
        try:
            audio_info = self._get_audio_info(output_path)
            if audio_info:
                # Vérifier que le sample rate est correct
                if audio_info['sample_rate'] != self.target_sample_rate:
                    logger.warning(f"Sample rate incorrect: {audio_info['sample_rate']}Hz au lieu de {self.target_sample_rate}Hz")
                
                # Vérifier que c'est bien mono
                if audio_info['channels'] != 1:
                    logger.warning(f"Nombre de canaux incorrect: {audio_info['channels']} au lieu de 1")
                
                logger.info(f"Qualité audio vérifiée: {audio_info['sample_rate']}Hz, "
                          f"{audio_info['channels']} canal(aux), "
                          f"{audio_info['duration_seconds']:.1f}s")
        except Exception as e:
            logger.warning(f"Impossible de vérifier la qualité audio: {e}")
    
    def _process_with_pydub(self, input_path, output_path):
        """
        Traitement audio avec pydub (fallback)
        """
        try:
            audio_segment = AudioSegment.from_file(input_path)
            
            # Conversion en mono si nécessaire
            if audio_segment.channels > 1:
                audio_segment = audio_segment.set_channels(1)
            
            # Normalisation du volume
            max_dBFS = audio_segment.max_dBFS
            if max_dBFS is not None and max_dBFS < 0:
                audio_segment = audio_segment.apply_gain(-0.1 - max_dBFS)
            
            # Rééchantillonnage à 16kHz si nécessaire
            if audio_segment.frame_rate != self.target_sample_rate:
                audio_segment = audio_segment.set_frame_rate(self.target_sample_rate)
            
            # Export en WAV 16kHz mono
            audio_segment.export(
                output_path,
                format="wav",
                parameters=["-acodec", "pcm_s16le"]
            )
            
            logger.info(f"Audio traité avec succès (pydub): {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Erreur avec pydub: {str(e)}", exc_info=True)
            # Dernier fallback sur librosa (peut être très lent pour les longs fichiers)
            logger.info("Tentative avec librosa en dernier recours...")
            try:
                audio, sr = librosa.load(input_path, sr=None, mono=True)
                
                # Normalisation du volume
                if np.max(np.abs(audio)) > 0:
                    audio = audio / np.max(np.abs(audio)) * 0.95
                
                # Rééchantillonnage si nécessaire
                if sr != self.target_sample_rate:
                    audio = librosa.resample(audio, orig_sr=sr, target_sr=self.target_sample_rate)
                
                # Sauvegarde
                sf.write(output_path, audio, self.target_sample_rate, subtype='PCM_16')
                logger.info(f"Audio traité avec succès (librosa fallback): {output_path}")
                return output_path
            except Exception as e2:
                logger.error(f"Erreur également avec librosa: {str(e2)}", exc_info=True)
                raise
    
    def get_audio_info(self, audio_path):
        """
        Récupère les informations d'un fichier audio
        
        Returns:
            dict: Informations sur l'audio (durée, sample rate, etc.)
        """
        try:
            audio = AudioSegment.from_file(audio_path)
            return {
                'duration_seconds': len(audio) / 1000.0,
                'sample_rate': audio.frame_rate,
                'channels': audio.channels,
                'bitrate': audio.frame_width * 8,
                'file_size': os.path.getsize(audio_path)
            }
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des infos audio: {str(e)}")
            return None

