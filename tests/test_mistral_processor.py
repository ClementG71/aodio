"""
Tests pour le MistralProcessor
"""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.mistral_processor import MistralProcessor

class TestMistralProcessor:
    """Tests pour MistralProcessor"""
    
    @pytest.fixture
    def processor(self):
        # Patch la classe Mistral là où elle est importée dans le service
        with patch('services.mistral_processor.Mistral') as MockMistral:
            mock_client = MockMistral.return_value
            # Configurer le mock pour chat.complete
            mock_client.chat.complete = MagicMock()
            
            proc = MistralProcessor(api_key="test_key")
            proc.speaker_mapper = MagicMock()
            proc.speaker_mapper.identify_speakers.return_value = ({}, [])
            return proc
    
    def test_map_speakers_hybrid_flow(self, processor):
        """Vérifie le flux hybride (Spacy + Fallback LLM)"""
        # Configurer le mock Spacy
        processor.speaker_mapper.identify_speakers.return_value = (
            {"SPEAKER_00": "Jean"}, # Identifié par Spacy
            ["SPEAKER_01"]          # Ambigu
        )
    
        # Configurer le mock Mistral (Fallback)
        mock_response = MagicMock()
        mock_response.choices[0].message.content = '{"SPEAKER_01": "Marie"}'
        processor.client.chat.complete.return_value = mock_response
        
        segments = [{"speaker": "SPEAKER_00"}, {"speaker": "SPEAKER_01"}]
        participants = ["Jean", "Marie"]
        
        mapping = processor.map_speakers(
            {"segments": segments},
            liste_participants_path=None
        )
        
        # Vérifier que les résultats sont fusionnés
        assert mapping["SPEAKER_00"] == "Jean"
        assert mapping["SPEAKER_01"] == "Marie"
        
        # Vérifier que Spacy a été appelé
        processor.speaker_mapper.identify_speakers.assert_called_once()
        
        # Vérifier que Mistral a été appelé (pour SPEAKER_01 uniquement)
        processor.client.chat.complete.assert_called_once()
        
    def test_generate_pre_compte_rendu(self, processor):
        """Vérifie l'appel pour le CR"""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Compte rendu généré"
        processor.client.chat.complete.return_value = mock_response
        
        result = processor.generate_pre_compte_rendu("texte", {})
        
        assert result == "Compte rendu généré"
        processor.client.chat.complete.assert_called()
        args = processor.client.chat.complete.call_args[1]
        assert args["model"] == processor.model_large
