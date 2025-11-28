"""
Tests pour la logique d'alignement Text-First
"""
import pytest
from services.transcription_aligner import TranscriptionAligner

class TestAlignerLogic:
    
    @pytest.fixture
    def aligner(self):
        return TranscriptionAligner()
    
    def test_align_simple_overlap(self, aligner):
        """Cas simple: alignement parfait"""
        transcriptions = [
            {"start": 0.0, "end": 5.0, "text": "Bonjour tout le monde"},
            {"start": 5.0, "end": 10.0, "text": "Comment allez vous"}
        ]
        
        diarization = [
            {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_00"},
            {"start": 5.0, "end": 10.0, "speaker": "SPEAKER_01"}
        ]
        
        result = aligner.align_strict_improved(transcriptions, diarization)
        
        assert len(result) == 2
        assert result[0]["speaker"] == "SPEAKER_00"
        assert "Bonjour" in result[0]["text"]
        assert result[1]["speaker"] == "SPEAKER_01"
        assert "Comment" in result[1]["text"]

    def test_align_split_sentence(self, aligner):
        """Cas complexe: une phrase à cheval sur 2 speakers"""
        # Phrase de 0 à 10s : "Je commence ici et je finis la bas" (8 mots)
        transcriptions = [
            {"start": 0.0, "end": 10.0, "text": "Je commence ici et je finis la bas"}
        ]
        
        # Speaker A de 0 à 5s, Speaker B de 5 à 10s
        diarization = [
            {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_A"},
            {"start": 5.0, "end": 10.0, "speaker": "SPEAKER_B"}
        ]
        
        result = aligner.align_strict_improved(transcriptions, diarization)
        
        # On s'attend à ce que le texte soit coupé en deux
        assert len(result) == 2
        print(f"Result 0: {result[0]['text']}")
        print(f"Result 1: {result[1]['text']}")
        
        # Vérifions que le texte est bien réparti (environ moitié moitié)
        assert "Je commence" in result[0]["text"]
        # Note: L'algo actuel prend les N premiers mots pour chaque segment qui overlap
        # Donc pour SPEAKER_A (50% overlap), il prend 50% des mots ("Je commence ici et")
        # Pour SPEAKER_B (50% overlap), il prend AUSSI les 50% premiers mots ? 
        # C'est là le danger de l'implémentation actuelle !
        
    def test_align_offset_correction(self, aligner):
        """Cas avec décalage temporel"""
        # Transcription décalée de +2s
        transcriptions = [
            {"start": 2.0, "end": 7.0, "text": "Bonjour"} 
        ]
        
        # Diarisation à 0s
        diarization = [
            {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_A"}
        ]
        
        # L'algo devrait détecter l'offset de -2s pour aligner T sur D
        # Note: L'algo calcule l'offset pour aligner T sur D, donc il devrait trouver -2.0
        
        result = aligner.align_strict_improved(transcriptions, diarization)
        
        assert "Bonjour" in result[0]["text"]
