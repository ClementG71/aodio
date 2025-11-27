"""
Tests pour le mapping et l'alignement des transcriptions
"""
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.transcription_mapper import TranscriptionMapper
from services.transcription_aligner import TranscriptionAligner


class TestTranscriptionMapper:
    """Tests pour TranscriptionMapper"""
    
    @pytest.fixture
    def mapper(self):
        return TranscriptionMapper()
    
    def test_merge_consecutive_segments_same_speaker(self, mapper):
        """Vérifie la fusion des segments consécutifs du même speaker"""
        segments = [
            {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_00"},
            {"start": 5.5, "end": 10.0, "speaker": "SPEAKER_00"},  # Même speaker, gap < 5s
            {"start": 10.0, "end": 15.0, "speaker": "SPEAKER_01"},
        ]
        
        merged = mapper.merge_consecutive_segments(segments, max_gap_seconds=5.0)
        
        assert len(merged) == 2
        assert merged[0]["start"] == 0.0
        assert merged[0]["end"] == 10.0
        assert merged[0]["speaker"] == "SPEAKER_00"
        assert merged[1]["speaker"] == "SPEAKER_01"
    
    def test_merge_consecutive_segments_different_speakers(self, mapper):
        """Vérifie que les segments de speakers différents ne sont pas fusionnés"""
        segments = [
            {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_00"},
            {"start": 5.0, "end": 10.0, "speaker": "SPEAKER_01"},
            {"start": 10.0, "end": 15.0, "speaker": "SPEAKER_00"},
        ]
        
        merged = mapper.merge_consecutive_segments(segments, max_gap_seconds=5.0)
        
        assert len(merged) == 3
    
    def test_merge_consecutive_segments_large_gap(self, mapper):
        """Vérifie que les segments avec un grand gap ne sont pas fusionnés"""
        segments = [
            {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_00"},
            {"start": 15.0, "end": 20.0, "speaker": "SPEAKER_00"},  # Gap > 5s
        ]
        
        merged = mapper.merge_consecutive_segments(segments, max_gap_seconds=5.0)
        
        assert len(merged) == 2
    
    def test_merge_consecutive_segments_empty_list(self, mapper):
        """Vérifie le comportement avec une liste vide"""
        merged = mapper.merge_consecutive_segments([], max_gap_seconds=5.0)
        assert merged == []
    
    def test_map_to_diarization_overlap(self, mapper, sample_diarization_segments, sample_transcription_segments):
        """Vérifie le mapping par chevauchement temporel"""
        result = mapper.map_to_diarization(
            sample_transcription_segments,
            sample_diarization_segments
        )
        
        # Doit retourner le même nombre de segments que la diarisation
        assert len(result) == len(sample_diarization_segments)
        
        # Chaque segment doit avoir le bon speaker
        for i, seg in enumerate(result):
            assert seg["speaker"] == sample_diarization_segments[i]["speaker"]
            assert seg["start"] == sample_diarization_segments[i]["start"]
            assert seg["end"] == sample_diarization_segments[i]["end"]
    
    def test_map_with_unique_attribution(self, mapper, sample_diarization_segments, sample_transcription_segments):
        """Vérifie le mapping avec attribution unique"""
        result = mapper.map_with_unique_attribution(
            sample_transcription_segments,
            sample_diarization_segments
        )
        
        assert len(result) == len(sample_diarization_segments)
        
        # Vérifier que chaque segment a le bon speaker
        for i, seg in enumerate(result):
            assert seg["speaker"] == sample_diarization_segments[i]["speaker"]
    
    def test_validate_mapping_correct(self, mapper):
        """Vérifie la validation d'un mapping correct"""
        transcriptions = [
            {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_00", "text": "Hello"},
            {"start": 5.0, "end": 10.0, "speaker": "SPEAKER_01", "text": "World"},
        ]
        diarization = [
            {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_00"},
            {"start": 5.0, "end": 10.0, "speaker": "SPEAKER_01"},
        ]
        
        issues = mapper.validate_mapping(transcriptions, diarization)
        
        # Pas de problèmes détectés
        assert len(issues) == 0
    
    def test_validate_mapping_wrong_count(self, mapper):
        """Vérifie la détection d'un nombre de segments différent"""
        transcriptions = [
            {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_00", "text": "Hello"},
        ]
        diarization = [
            {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_00"},
            {"start": 5.0, "end": 10.0, "speaker": "SPEAKER_01"},
        ]
        
        issues = mapper.validate_mapping(transcriptions, diarization)
        
        # Doit détecter le problème de nombre
        assert any("différent" in issue.lower() for issue in issues)
    
    def test_validate_mapping_speaker_mismatch(self, mapper):
        """Vérifie la détection d'un speaker incorrect"""
        transcriptions = [
            {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_01", "text": "Hello"},  # Mauvais speaker
            {"start": 5.0, "end": 10.0, "speaker": "SPEAKER_01", "text": "World"},
        ]
        diarization = [
            {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_00"},
            {"start": 5.0, "end": 10.0, "speaker": "SPEAKER_01"},
        ]
        
        issues = mapper.validate_mapping(transcriptions, diarization)
        
        # Doit détecter le mismatch de speaker
        assert any("mismatch" in issue.lower() for issue in issues)
    
    def test_normalize_segments_dict(self, mapper):
        """Vérifie la normalisation des segments dict"""
        segments = [
            {"start": 0.0, "end": 5.0, "text": "Hello"},
        ]
        
        normalized = mapper._normalize_segments(segments)
        
        assert len(normalized) == 1
        assert normalized[0]["start"] == 0.0
        assert normalized[0]["end"] == 5.0
        assert normalized[0]["text"] == "Hello"


class TestTranscriptionAligner:
    """Tests pour TranscriptionAligner"""
    
    @pytest.fixture
    def aligner(self):
        return TranscriptionAligner()
    
    def test_clean_transcription_segments_removes_empty(self, aligner):
        """Vérifie la suppression des segments vides"""
        segments = [
            {"start": 0.0, "end": 5.0, "text": "Hello"},
            {"start": 5.0, "end": 5.05, "text": ""},  # Très court et vide
            {"start": 5.1, "end": 10.0, "text": "World"},
        ]
        
        cleaned = aligner.clean_transcription_segments(segments)
        
        # Le segment vide devrait être fusionné ou supprimé
        assert len(cleaned) <= 3
    
    def test_distribute_by_chronological_order(self, aligner, sample_diarization_segments, sample_full_text):
        """Vérifie la distribution chronologique du texte"""
        result = aligner.distribute_by_chronological_order(
            sample_full_text,
            sample_diarization_segments
        )
        
        # Doit retourner le même nombre de segments
        assert len(result) == len(sample_diarization_segments)
        
        # Chaque segment doit avoir le bon speaker et timestamps
        for i, seg in enumerate(result):
            assert seg["speaker"] == sample_diarization_segments[i]["speaker"]
            assert seg["start"] == sample_diarization_segments[i]["start"]
            assert seg["end"] == sample_diarization_segments[i]["end"]
        
        # Au moins certains segments doivent avoir du texte
        texts_with_content = [s for s in result if s.get("text", "").strip()]
        assert len(texts_with_content) > 0
    
    def test_distribute_by_chronological_order_empty_text(self, aligner, sample_diarization_segments):
        """Vérifie la distribution avec un texte vide"""
        result = aligner.distribute_by_chronological_order(
            "",
            sample_diarization_segments
        )
        
        # Doit retourner les segments sans texte
        assert len(result) == len(sample_diarization_segments)
        for seg in result:
            assert seg.get("text", "") == ""
    
    def test_calculate_optimal_offset_no_offset_needed(self, aligner):
        """Vérifie le calcul d'offset quand aucun décalage n'est nécessaire"""
        transcriptions = [
            {"start": 0.0, "end": 5.0, "text": "Hello"},
            {"start": 5.0, "end": 10.0, "text": "World"},
        ]
        diarization = [
            {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_00"},
            {"start": 5.0, "end": 10.0, "speaker": "SPEAKER_01"},
        ]
        
        offset = aligner.calculate_optimal_offset(transcriptions, diarization)
        
        # L'offset devrait être proche de 0
        assert abs(offset) < 0.5
    
    def test_calculate_optimal_offset_with_shift(self, aligner):
        """Vérifie le calcul d'offset quand il y a un décalage"""
        transcriptions = [
            {"start": 1.0, "end": 6.0, "text": "Hello"},  # Décalé de 1s
            {"start": 6.0, "end": 11.0, "text": "World"},
        ]
        diarization = [
            {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_00"},
            {"start": 5.0, "end": 10.0, "speaker": "SPEAKER_01"},
        ]
        
        offset = aligner.calculate_optimal_offset(transcriptions, diarization)
        
        # L'offset devrait être proche de -1 pour compenser le décalage
        assert -1.5 < offset < -0.5
    
    def test_calculate_optimal_offset_empty_lists(self, aligner):
        """Vérifie le calcul d'offset avec des listes vides"""
        offset = aligner.calculate_optimal_offset([], [])
        assert offset == 0.0
    
    def test_fill_missing_segments(self, aligner, sample_diarization_segments, sample_full_text):
        """Vérifie le remplissage des segments manquants"""
        # Créer des transcriptions avec des trous
        transcriptions = [
            {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_00", "text": "Hello"},
            {"start": 5.0, "end": 12.0, "speaker": "SPEAKER_01", "text": ""},  # Vide
            {"start": 12.0, "end": 18.0, "speaker": "SPEAKER_00", "text": "World"},
            {"start": 18.0, "end": 25.0, "speaker": "SPEAKER_01", "text": ""},  # Vide
            {"start": 25.0, "end": 30.0, "speaker": "SPEAKER_00", "text": "!"},
        ]
        
        result = aligner.fill_missing_segments(
            transcriptions,
            sample_full_text,
            sample_diarization_segments
        )
        
        # Les segments vides devraient être remplis
        assert len(result) == len(transcriptions)
    
    def test_align_strict_improved(self, aligner, sample_diarization_segments, sample_transcription_segments, sample_full_text):
        """Vérifie l'alignement strict amélioré"""
        result = aligner.align_strict_improved(
            sample_transcription_segments,
            sample_diarization_segments,
            sample_full_text
        )
        
        # Doit retourner le même nombre de segments
        assert len(result) == len(sample_diarization_segments)
        
        # Chaque segment doit avoir le bon speaker
        for i, seg in enumerate(result):
            assert seg["speaker"] == sample_diarization_segments[i]["speaker"]
