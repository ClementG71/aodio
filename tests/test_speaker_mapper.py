"""
Tests pour le mapping des locuteurs avec Spacy
"""
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.speaker_mapper import SpeakerMapper

class TestSpeakerMapper:
    """Tests pour SpeakerMapper"""
    
    @pytest.fixture
    def mapper(self):
        return SpeakerMapper()
    
    @pytest.fixture
    def participants(self):
        return ["Jean Dupont", "Marie Curie", "Albert Einstein"]
    
    def test_identify_speakers_simple(self, mapper, participants):
        """Vérifie l'identification simple"""
        if not mapper.nlp:
            pytest.skip("Spacy non disponible")
            
        segments = [
            {"speaker": "SPEAKER_00", "text": "Bonjour, je suis Jean Dupont."},
            {"speaker": "SPEAKER_01", "text": "Bonjour Jean, ici Marie Curie."},
        ]
        
        mapping, ambigus = mapper.identify_speakers(segments, participants)
        
        assert mapping.get("SPEAKER_00") == "Jean Dupont"
        assert mapping.get("SPEAKER_01") == "Marie Curie"
        assert "SPEAKER_00" not in ambigus
    
    def test_identify_speakers_context(self, mapper, participants):
        """Vérifie l'identification par contexte (donner la parole)"""
        if not mapper.nlp:
            pytest.skip("Spacy non disponible")
            
        # Debug: voir ce que spacy détecte
        doc = mapper.nlp("La parole est à Albert Einstein.")
        print(f"Entities: {[(ent.text, ent.label_) for ent in doc.ents]}")
    
        segments = [
            {"speaker": "SPEAKER_00", "text": "La parole est à Albert Einstein."},
            {"speaker": "SPEAKER_01", "text": "Merci. E=mc2."},
        ]
        
        mapping, ambigus = mapper.identify_speakers(segments, participants)
        
        assert mapping.get("SPEAKER_01") == "Albert Einstein"
    
    def test_identify_speakers_ambiguous(self, mapper, participants):
        """Vérifie que les cas ambigus sont signalés"""
        if not mapper.nlp:
            pytest.skip("Spacy non disponible")
            
        segments = [
            {"speaker": "SPEAKER_00", "text": "Bonjour tout le monde."},
            {"speaker": "SPEAKER_01", "text": "Il fait beau."},
        ]
        
        mapping, ambigus = mapper.identify_speakers(segments, participants)
        
        assert "SPEAKER_00" in ambigus
        assert "SPEAKER_01" in ambigus
        assert not mapping
    
    def test_is_self_introduction(self, mapper):
        """Vérifie la détection d'auto-présentation"""
        assert mapper._is_self_introduction("Je suis Jean", "Jean")
        assert mapper._is_self_introduction("Je m'appelle Marie", "Marie")
        assert not mapper._is_self_introduction("Tu es Jean", "Jean")
        
    def test_is_giving_floor(self, mapper):
        """Vérifie la détection de passage de parole"""
        assert mapper._is_giving_floor("La parole est à Jean", "Jean")
        assert mapper._is_giving_floor("Merci Marie", "Marie")
        assert not mapper._is_giving_floor("Je suis Jean", "Jean")
