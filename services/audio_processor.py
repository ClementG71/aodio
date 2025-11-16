"""
Service de traitement audio : normalisation et compression
"""
import os
import logging
from pathlib import Path
from pydub import AudioSegment
import librosa
import soundfile as sf
import numpy as np

logger = logging.getLogger(__name__)


class AudioProcessor:
    """Traite les fichiers audio : normalisation et compression"""
    
    def __init__(self):
        self.target_sample_rate = 16000  # Taux d'échantillonnage cible
        self.target_channels = 1  # Mono
        self.target_bitrate = '128k'  # Bitrate pour compression
    
    def process_audio(self, input_path, output_path):
        """
        Normalise et compresse un fichier audio
        
        Args:
            input_path: Chemin du fichier audio d'entrée
            output_path: Chemin du fichier audio de sortie
            
        Returns:
            str: Chemin du fichier traité
        """
        try:
            logger.info(f"Traitement audio: {input_path} -> {output_path}")
            
            # Utiliser pydub pour les opérations de base (plus rapide)
            # Charger avec pydub qui utilise ffmpeg en arrière-plan
            audio_segment = AudioSegment.from_file(input_path)
            
            # Conversion en mono si nécessaire
            if audio_segment.channels > 1:
                audio_segment = audio_segment.set_channels(1)
            
            # Normalisation du volume (peak normalization)
            # pydub utilise des dB, on normalise à -0.1 dB pour éviter la saturation
            max_dBFS = audio_segment.max_dBFS
            if max_dBFS is not None and max_dBFS < 0:
                # Normaliser à -0.1 dB (équivalent à 95% en amplitude)
                audio_segment = audio_segment.apply_gain(-0.1 - max_dBFS)
            
            # Rééchantillonnage à 16kHz si nécessaire
            if audio_segment.frame_rate != self.target_sample_rate:
                audio_segment = audio_segment.set_frame_rate(self.target_sample_rate)
            
            # Export en WAV 16kHz mono
            audio_segment.export(
                output_path,
                format="wav",
                parameters=["-acodec", "pcm_s16le"]  # PCM 16-bit little-endian
            )
            
            logger.info(f"Audio traité avec succès: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Erreur lors du traitement audio: {str(e)}", exc_info=True)
            # Fallback sur librosa si pydub échoue
            logger.info("Tentative avec librosa en fallback...")
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

