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
        
        Pour les fichiers très longs (jusqu'à 4h15), utilise ffmpeg directement
        pour éviter de charger tout en mémoire.
        
        Args:
            input_path: Chemin du fichier audio d'entrée
            output_path: Chemin du fichier audio de sortie
            
        Returns:
            str: Chemin du fichier traité
        """
        try:
            logger.info(f"Traitement audio: {input_path} -> {output_path}")
            
            # Utiliser ffmpeg directement via subprocess pour les gros fichiers
            # Cela évite de charger tout en mémoire et est plus rapide
            import subprocess
            
            # Construire la commande ffmpeg
            # -i : fichier d'entrée
            # -ar : sample rate (16kHz)
            # -ac : nombre de canaux (1 = mono)
            # -af "loudnorm=I=-16:TP=-1.5:LRA=11" : normalisation du volume (optionnel, peut être lent)
            # -acodec pcm_s16le : codec PCM 16-bit little-endian
            # -y : écraser le fichier de sortie s'il existe
            
            # Pour les très longs fichiers, on simplifie la normalisation
            # On utilise juste la conversion de format et le rééchantillonnage
            # Optimisations de performance :
            # -threads 0 : utilise tous les CPU disponibles
            # -preset fast : équilibre vitesse/qualité
            # -loglevel error : réduit les logs pour améliorer les performances
            cmd = [
                'ffmpeg',
                '-threads', '0',  # Utiliser tous les CPU disponibles
                '-i', str(input_path),
                '-ar', str(self.target_sample_rate),  # Sample rate 16kHz
                '-ac', '1',  # Mono
                '-acodec', 'pcm_s16le',  # PCM 16-bit
                '-loglevel', 'error',  # Réduire les logs pour améliorer les performances
                '-y',  # Overwrite output
                str(output_path)
            ]
            
            logger.info(f"Exécution de ffmpeg: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600  # Timeout de 1 heure pour les très longs fichiers
            )
            
            if result.returncode != 0:
                logger.warning(f"ffmpeg a retourné une erreur: {result.stderr}")
                # Fallback sur pydub si ffmpeg échoue
                logger.info("Tentative avec pydub en fallback...")
                return self._process_with_pydub(input_path, output_path)
            
            logger.info(f"Audio traité avec succès (ffmpeg): {output_path}")
            return output_path
            
        except subprocess.TimeoutExpired:
            logger.error("Timeout lors du traitement avec ffmpeg")
            raise Exception("Le traitement audio a pris trop de temps")
        except FileNotFoundError:
            logger.warning("ffmpeg non trouvé, utilisation de pydub")
            return self._process_with_pydub(input_path, output_path)
        except Exception as e:
            logger.error(f"Erreur lors du traitement audio: {str(e)}", exc_info=True)
            # Fallback sur pydub
            logger.info("Tentative avec pydub en fallback...")
            return self._process_with_pydub(input_path, output_path)
    
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

