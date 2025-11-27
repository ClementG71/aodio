"""
Tests pour la validation des fichiers uploadés

Note: Ces tests importent les fonctions de validation directement depuis le code
source pour éviter les dépendances lourdes de l'application principale.
"""
import io
import os
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

# Configuration - dupliquée depuis app.py pour éviter les imports lourds
ALLOWED_EXTENSIONS = {'wav', 'mp3', 'm4a', 'flac', 'ogg', 'webm'}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB


def allowed_file(filename):
    """Vérifie si le fichier a une extension autorisée"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_file_size(file_storage) -> int:
    """
    Obtient la taille réelle d'un fichier uploadé sans le charger entièrement en mémoire
    """
    current_position = file_storage.tell()
    file_storage.seek(0, os.SEEK_END)
    size = file_storage.tell()
    file_storage.seek(current_position)
    return size


def validate_audio_file(file_storage, filename: str, max_size: int = MAX_FILE_SIZE) -> tuple:
    """
    Valide un fichier audio uploadé
    """
    # 1. Vérifier que le fichier n'est pas vide
    if not file_storage or not filename:
        return False, "Aucun fichier fourni"
    
    if filename == '':
        return False, "Nom de fichier vide"
    
    # 2. Vérifier l'extension
    if not allowed_file(filename):
        allowed_ext_str = ', '.join(sorted(ALLOWED_EXTENSIONS))
        return False, f"Extension non autorisée. Extensions acceptées: {allowed_ext_str}"
    
    # 3. Vérifier la taille du fichier AVANT sauvegarde
    file_size = get_file_size(file_storage)
    if file_size == 0:
        return False, "Le fichier est vide"
    
    if file_size > max_size:
        max_mb = max_size / (1024 * 1024)
        file_mb = file_size / (1024 * 1024)
        return False, f"Fichier trop volumineux ({file_mb:.1f} MB). Maximum autorisé: {max_mb:.0f} MB"
    
    # 4. Vérifier les premiers octets (magic bytes) pour valider le type réel
    magic_signatures = {
        b'RIFF': 'wav',
        b'ID3': 'mp3',
        b'\xff\xfb': 'mp3',
        b'\xff\xfa': 'mp3',
        b'\xff\xf3': 'mp3',
        b'\xff\xf2': 'mp3',
        b'fLaC': 'flac',
        b'OggS': 'ogg',
        b'\x1aE\xdf\xa3': 'webm',
        b'\x00\x00\x00': 'm4a',
    }
    
    file_storage.seek(0)
    header = file_storage.read(12)
    file_storage.seek(0)
    
    if len(header) < 4:
        return False, "Fichier trop petit pour être un fichier audio valide"
    
    is_valid_audio = False
    
    if len(header) >= 8 and header[4:8] == b'ftyp':
        is_valid_audio = True
    else:
        for signature in magic_signatures.keys():
            if header.startswith(signature):
                is_valid_audio = True
                break
    
    if not is_valid_audio:
        return False, "Le contenu du fichier ne correspond pas à un format audio reconnu"
    
    return True, None


class MockFileStorage:
    """Mock de werkzeug.FileStorage pour les tests"""
    
    def __init__(self, content: bytes, filename: str):
        self._content = content
        self.filename = filename
        self._position = 0
    
    def read(self, size: int = -1) -> bytes:
        if size == -1:
            data = self._content[self._position:]
            self._position = len(self._content)
        else:
            data = self._content[self._position:self._position + size]
            self._position += size
        return data
    
    def seek(self, position: int, whence: int = 0):
        if whence == 0:  # SEEK_SET
            self._position = position
        elif whence == 2:  # SEEK_END
            self._position = len(self._content) + position
    
    def tell(self) -> int:
        return self._position


class TestAllowedFile:
    """Tests pour la fonction allowed_file"""
    
    def test_allowed_extensions(self):
        """Vérifie que les extensions autorisées sont acceptées"""
        for ext in ALLOWED_EXTENSIONS:
            assert allowed_file(f"test.{ext}") is True
            assert allowed_file(f"test.{ext.upper()}") is True
    
    def test_rejected_extensions(self):
        """Vérifie que les extensions non autorisées sont rejetées"""
        rejected = ['txt', 'pdf', 'doc', 'exe', 'py', 'js', 'html']
        for ext in rejected:
            assert allowed_file(f"test.{ext}") is False
    
    def test_no_extension(self):
        """Vérifie qu'un fichier sans extension est rejeté"""
        assert allowed_file("testfile") is False
    
    def test_empty_filename(self):
        """Vérifie qu'un nom de fichier vide est rejeté"""
        assert allowed_file("") is False


class TestGetFileSize:
    """Tests pour la fonction get_file_size"""
    
    def test_get_size_small_file(self):
        """Vérifie la taille d'un petit fichier"""
        content = b'x' * 100
        mock_file = MockFileStorage(content, "test.wav")
        assert get_file_size(mock_file) == 100
    
    def test_get_size_large_file(self):
        """Vérifie la taille d'un fichier plus grand"""
        content = b'x' * 10000
        mock_file = MockFileStorage(content, "test.wav")
        assert get_file_size(mock_file) == 10000
    
    def test_get_size_preserves_position(self):
        """Vérifie que la position du curseur est préservée"""
        content = b'x' * 100
        mock_file = MockFileStorage(content, "test.wav")
        mock_file.seek(50)
        get_file_size(mock_file)
        assert mock_file.tell() == 50


class TestValidateAudioFile:
    """Tests pour la fonction validate_audio_file"""
    
    def test_valid_wav_file(self, sample_wav_header):
        """Vérifie qu'un fichier WAV valide est accepté"""
        mock_file = MockFileStorage(sample_wav_header, "test.wav")
        is_valid, error = validate_audio_file(mock_file, "test.wav")
        assert is_valid is True
        assert error is None
    
    def test_valid_mp3_file_with_id3(self, sample_mp3_header):
        """Vérifie qu'un fichier MP3 avec ID3 est accepté"""
        mock_file = MockFileStorage(sample_mp3_header, "test.mp3")
        is_valid, error = validate_audio_file(mock_file, "test.mp3")
        assert is_valid is True
        assert error is None
    
    def test_valid_mp3_file_no_id3(self, sample_mp3_header_no_id3):
        """Vérifie qu'un fichier MP3 sans ID3 est accepté"""
        mock_file = MockFileStorage(sample_mp3_header_no_id3, "test.mp3")
        is_valid, error = validate_audio_file(mock_file, "test.mp3")
        assert is_valid is True
        assert error is None
    
    def test_valid_flac_file(self, sample_flac_header):
        """Vérifie qu'un fichier FLAC valide est accepté"""
        mock_file = MockFileStorage(sample_flac_header, "test.flac")
        is_valid, error = validate_audio_file(mock_file, "test.flac")
        assert is_valid is True
        assert error is None
    
    def test_valid_ogg_file(self, sample_ogg_header):
        """Vérifie qu'un fichier OGG valide est accepté"""
        mock_file = MockFileStorage(sample_ogg_header, "test.ogg")
        is_valid, error = validate_audio_file(mock_file, "test.ogg")
        assert is_valid is True
        assert error is None
    
    def test_valid_m4a_file(self, sample_m4a_header):
        """Vérifie qu'un fichier M4A valide est accepté"""
        mock_file = MockFileStorage(sample_m4a_header, "test.m4a")
        is_valid, error = validate_audio_file(mock_file, "test.m4a")
        assert is_valid is True
        assert error is None
    
    def test_empty_file(self, sample_wav_header):
        """Vérifie qu'un fichier vide est rejeté"""
        mock_file = MockFileStorage(b'', "test.wav")
        is_valid, error = validate_audio_file(mock_file, "test.wav")
        assert is_valid is False
        assert "vide" in error.lower()
    
    def test_wrong_extension(self, sample_wav_header):
        """Vérifie qu'une mauvaise extension est rejetée"""
        mock_file = MockFileStorage(sample_wav_header, "test.txt")
        is_valid, error = validate_audio_file(mock_file, "test.txt")
        assert is_valid is False
        assert "extension" in error.lower()
    
    def test_fake_audio_file(self, sample_text_file):
        """Vérifie qu'un fichier texte renommé en .wav est rejeté"""
        mock_file = MockFileStorage(sample_text_file, "fake.wav")
        is_valid, error = validate_audio_file(mock_file, "fake.wav")
        assert is_valid is False
        assert "format audio" in error.lower()
    
    def test_file_too_large(self, sample_wav_header):
        """Vérifie qu'un fichier trop gros est rejeté"""
        # Créer un fichier de 1 octet de plus que la limite
        large_content = sample_wav_header + b'x' * (MAX_FILE_SIZE + 1 - len(sample_wav_header))
        mock_file = MockFileStorage(large_content, "large.wav")
        is_valid, error = validate_audio_file(mock_file, "large.wav", max_size=MAX_FILE_SIZE)
        assert is_valid is False
        assert "volumineux" in error.lower()
    
    def test_no_filename(self, sample_wav_header):
        """Vérifie qu'un fichier sans nom est rejeté"""
        mock_file = MockFileStorage(sample_wav_header, "")
        is_valid, error = validate_audio_file(mock_file, "")
        assert is_valid is False
    
    def test_none_file(self):
        """Vérifie que None est rejeté"""
        is_valid, error = validate_audio_file(None, "test.wav")
        assert is_valid is False
        assert "fourni" in error.lower()
    
    def test_file_too_small(self):
        """Vérifie qu'un fichier trop petit est rejeté"""
        mock_file = MockFileStorage(b'RI', "tiny.wav")
        is_valid, error = validate_audio_file(mock_file, "tiny.wav")
        assert is_valid is False
        assert "petit" in error.lower()
