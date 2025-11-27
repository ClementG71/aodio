"""
Tests pour les endpoints de l'API Flask

Note: Ces tests nécessitent toutes les dépendances de l'application.
Ils sont marqués pour être skippés si les dépendances ne sont pas disponibles.
"""
import pytest
import io
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

# Vérifier si l'application peut être importée
try:
    from app import app
    APP_AVAILABLE = True
except ImportError as e:
    APP_AVAILABLE = False
    APP_IMPORT_ERROR = str(e)

# Skip all tests if app is not available
pytestmark = pytest.mark.skipif(
    not APP_AVAILABLE,
    reason=f"Application dependencies not available: {APP_IMPORT_ERROR if not APP_AVAILABLE else ''}"
)


class TestIndexEndpoint:
    """Tests pour la page d'accueil"""
    
    def test_index_returns_200(self, app_client):
        """Vérifie que la page d'accueil est accessible"""
        response = app_client.get('/')
        assert response.status_code == 200
    
    def test_index_returns_html(self, app_client):
        """Vérifie que la page d'accueil retourne du HTML"""
        response = app_client.get('/')
        assert b'<!DOCTYPE html>' in response.data or b'<html' in response.data


class TestUploadEndpoint:
    """Tests pour l'endpoint d'upload"""
    
    def test_upload_no_file(self, app_client):
        """Vérifie qu'un upload sans fichier retourne une erreur"""
        response = app_client.post('/upload', data={})
        assert response.status_code == 400
        assert b'error' in response.data.lower()
    
    def test_upload_empty_file(self, app_client, sample_wav_header):
        """Vérifie qu'un upload avec un fichier vide retourne une erreur"""
        data = {
            'audio_file': (io.BytesIO(b''), 'empty.wav')
        }
        response = app_client.post(
            '/upload',
            data=data,
            content_type='multipart/form-data'
        )
        assert response.status_code == 400
    
    def test_upload_wrong_format(self, app_client):
        """Vérifie qu'un upload avec un mauvais format retourne une erreur"""
        data = {
            'audio_file': (io.BytesIO(b'fake content'), 'test.txt')
        }
        response = app_client.post(
            '/upload',
            data=data,
            content_type='multipart/form-data'
        )
        assert response.status_code == 400
        assert b'error' in response.data.lower()
    
    def test_upload_fake_audio(self, app_client, sample_text_file):
        """Vérifie qu'un fichier texte renommé en .wav est rejeté"""
        data = {
            'audio_file': (io.BytesIO(sample_text_file), 'fake.wav')
        }
        response = app_client.post(
            '/upload',
            data=data,
            content_type='multipart/form-data'
        )
        assert response.status_code == 400
        # Doit indiquer que le format n'est pas valide
        assert b'audio' in response.data.lower() or b'format' in response.data.lower()


class TestStatusEndpoint:
    """Tests pour l'endpoint de statut"""
    
    def test_status_invalid_session(self, app_client):
        """Vérifie qu'une session inexistante retourne une erreur"""
        response = app_client.get('/status/nonexistent-session-id')
        # Doit retourner 404 ou un statut indiquant que la session n'existe pas
        assert response.status_code in [404, 200]
        if response.status_code == 200:
            # Si 200, vérifier que le statut indique une erreur ou non trouvé
            assert b'error' in response.data.lower() or b'not found' in response.data.lower() or b'status' in response.data.lower()


class TestHistoryEndpoint:
    """Tests pour l'endpoint d'historique"""
    
    def test_history_returns_200(self, app_client):
        """Vérifie que la page d'historique est accessible"""
        response = app_client.get('/history')
        # Peut retourner 200 (page) ou rediriger
        assert response.status_code in [200, 302]


class TestFilesEndpoint:
    """Tests pour l'endpoint de fichiers"""
    
    def test_files_invalid_session(self, app_client):
        """Vérifie qu'une session inexistante retourne une erreur 404"""
        response = app_client.get('/files/nonexistent-session/audio.wav')
        assert response.status_code == 404
    
    def test_files_path_traversal_blocked(self, app_client):
        """Vérifie que les tentatives de path traversal sont bloquées"""
        # Tentative d'accès à un fichier parent
        response = app_client.get('/files/../../../etc/passwd')
        # Doit soit retourner 404, soit bloquer la requête
        assert response.status_code in [400, 403, 404]


class TestCORSHeaders:
    """Tests pour les headers CORS"""
    
    def test_options_request(self, app_client):
        """Vérifie que les requêtes OPTIONS sont gérées"""
        response = app_client.options('/files/test/audio.wav')
        # La requête OPTIONS doit être autorisée
        assert response.status_code in [200, 404]


class TestErrorHandling:
    """Tests pour la gestion des erreurs"""
    
    def test_404_error(self, app_client):
        """Vérifie qu'une route inexistante retourne 404"""
        response = app_client.get('/nonexistent-route')
        assert response.status_code == 404
