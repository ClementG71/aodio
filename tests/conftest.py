"""
Configuration et fixtures partagées pour les tests pytest
"""
import os
import sys
import tempfile
import shutil
from pathlib import Path
from typing import Generator

import pytest

# Ajouter le répertoire racine au path pour les imports
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Crée un répertoire temporaire pour les tests"""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    # Nettoyage après le test
    if temp_path.exists():
        shutil.rmtree(temp_path)


@pytest.fixture
def sample_wav_header() -> bytes:
    """Retourne un header WAV valide (44 octets minimum)"""
    # Header WAV minimal valide
    return (
        b'RIFF'           # ChunkID
        b'\x24\x00\x00\x00'  # ChunkSize (36 + data size)
        b'WAVE'           # Format
        b'fmt '           # Subchunk1ID
        b'\x10\x00\x00\x00'  # Subchunk1Size (16 for PCM)
        b'\x01\x00'       # AudioFormat (1 = PCM)
        b'\x01\x00'       # NumChannels (1 = mono)
        b'\x80\x3e\x00\x00'  # SampleRate (16000)
        b'\x00\x7d\x00\x00'  # ByteRate
        b'\x02\x00'       # BlockAlign
        b'\x10\x00'       # BitsPerSample (16)
        b'data'           # Subchunk2ID
        b'\x00\x00\x00\x00'  # Subchunk2Size
    )


@pytest.fixture
def sample_mp3_header() -> bytes:
    """Retourne un header MP3 valide avec tag ID3"""
    return b'ID3' + b'\x00' * 10


@pytest.fixture
def sample_mp3_header_no_id3() -> bytes:
    """Retourne un header MP3 sans tag ID3 (sync word)"""
    return b'\xff\xfb\x90\x00' + b'\x00' * 10


@pytest.fixture
def sample_flac_header() -> bytes:
    """Retourne un header FLAC valide"""
    return b'fLaC' + b'\x00' * 10


@pytest.fixture
def sample_ogg_header() -> bytes:
    """Retourne un header OGG valide"""
    return b'OggS' + b'\x00' * 10


@pytest.fixture
def sample_m4a_header() -> bytes:
    """Retourne un header M4A valide (ftyp box)"""
    return b'\x00\x00\x00\x1c' + b'ftyp' + b'M4A ' + b'\x00' * 10


@pytest.fixture
def sample_text_file() -> bytes:
    """Retourne un fichier texte (pas un audio)"""
    return b'This is a text file, not an audio file.'


@pytest.fixture
def sample_diarization_segments():
    """Retourne des segments de diarisation de test"""
    return [
        {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_00"},
        {"start": 5.0, "end": 12.0, "speaker": "SPEAKER_01"},
        {"start": 12.0, "end": 18.0, "speaker": "SPEAKER_00"},
        {"start": 18.0, "end": 25.0, "speaker": "SPEAKER_01"},
        {"start": 25.0, "end": 30.0, "speaker": "SPEAKER_00"},
    ]


@pytest.fixture
def sample_transcription_segments():
    """Retourne des segments de transcription de test"""
    return [
        {"start": 0.5, "end": 4.8, "text": "Bonjour à tous, bienvenue à cette réunion."},
        {"start": 5.2, "end": 11.5, "text": "Merci, nous allons commencer par le premier point."},
        {"start": 12.3, "end": 17.8, "text": "D'accord, je vais présenter les résultats."},
        {"start": 18.5, "end": 24.2, "text": "Très bien, ces chiffres sont encourageants."},
        {"start": 25.1, "end": 29.5, "text": "Passons maintenant au point suivant."},
    ]


@pytest.fixture
def sample_full_text():
    """Retourne un texte complet de transcription"""
    return (
        "Bonjour à tous, bienvenue à cette réunion. "
        "Merci, nous allons commencer par le premier point. "
        "D'accord, je vais présenter les résultats. "
        "Très bien, ces chiffres sont encourageants. "
        "Passons maintenant au point suivant."
    )


@pytest.fixture
def app_client():
    """Client de test Flask"""
    # Import ici pour éviter les problèmes de circular import
    from app import app
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client
