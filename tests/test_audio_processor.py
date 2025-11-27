"""
Tests pour le traitement audio et le découpage en segments
"""
import pytest
from pathlib import Path
import sys
import os

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.audio_segmenter import AudioSegmenter


class TestAudioSegmenter:
    """Tests pour AudioSegmenter"""
    
    @pytest.fixture
    def segmenter(self):
        return AudioSegmenter(max_segment_duration=600)
    
    def test_init_default_duration(self):
        """Vérifie l'initialisation avec la durée par défaut"""
        segmenter = AudioSegmenter()
        assert segmenter.max_segment_duration == 600
    
    def test_init_custom_duration(self):
        """Vérifie l'initialisation avec une durée personnalisée"""
        segmenter = AudioSegmenter(max_segment_duration=300)
        assert segmenter.max_segment_duration == 300
    
    def test_temporary_segments_context_manager(self, segmenter, temp_dir):
        """Vérifie que le context manager supprime les fichiers temporaires"""
        # Créer des fichiers temporaires
        segments = []
        for i in range(3):
            file_path = temp_dir / f"segment_{i}.wav"
            file_path.write_bytes(b'fake audio content')
            segments.append({"path": str(file_path), "start_time": i * 10, "end_time": (i + 1) * 10})
        
        # Vérifier que les fichiers existent
        for seg in segments:
            assert Path(seg["path"]).exists()
        
        # Utiliser le context manager
        with segmenter.temporary_segments(segments) as segs:
            # Les fichiers doivent toujours exister pendant le bloc
            for seg in segs:
                assert Path(seg["path"]).exists()
        
        # Après le bloc, les fichiers doivent être supprimés
        for seg in segments:
            assert not Path(seg["path"]).exists()
    
    def test_temporary_segments_cleanup_on_exception(self, segmenter, temp_dir):
        """Vérifie que le context manager supprime les fichiers même en cas d'exception"""
        segments = []
        for i in range(3):
            file_path = temp_dir / f"segment_{i}.wav"
            file_path.write_bytes(b'fake audio content')
            segments.append({"path": str(file_path), "start_time": i * 10, "end_time": (i + 1) * 10})
        
        # Lever une exception dans le bloc
        try:
            with segmenter.temporary_segments(segments):
                raise ValueError("Test exception")
        except ValueError:
            pass
        
        # Les fichiers doivent être supprimés malgré l'exception
        for seg in segments:
            assert not Path(seg["path"]).exists()
    
    def test_temporary_segments_handles_missing_files(self, segmenter, temp_dir):
        """Vérifie que le context manager gère les fichiers déjà supprimés"""
        segments = [
            {"path": str(temp_dir / "nonexistent.wav"), "start_time": 0, "end_time": 10}
        ]
        
        # Ne doit pas lever d'exception
        with segmenter.temporary_segments(segments):
            pass
    
    def test_filter_diarization_for_segment_within_range(self, segmenter):
        """Vérifie le filtrage des segments de diarisation dans la plage"""
        diarization = [
            {"start": 0.0, "end": 10.0, "speaker": "SPEAKER_00"},
            {"start": 10.0, "end": 20.0, "speaker": "SPEAKER_01"},
            {"start": 20.0, "end": 30.0, "speaker": "SPEAKER_00"},
            {"start": 30.0, "end": 40.0, "speaker": "SPEAKER_01"},
        ]
        
        # Filtrer pour le segment 10-30s
        result = segmenter.filter_diarization_for_segment(
            diarization, seg_start=10.0, seg_end=30.0, adjust_timestamps=False
        )
        
        # Doit inclure les segments qui chevauchent 10-30s
        assert len(result) == 2
        assert result[0]["speaker"] == "SPEAKER_01"
        assert result[1]["speaker"] == "SPEAKER_00"
    
    def test_filter_diarization_for_segment_with_adjustment(self, segmenter):
        """Vérifie l'ajustement des timestamps lors du filtrage"""
        diarization = [
            {"start": 10.0, "end": 20.0, "speaker": "SPEAKER_00"},
            {"start": 20.0, "end": 30.0, "speaker": "SPEAKER_01"},
        ]
        
        # Filtrer pour le segment 10-30s avec ajustement
        result = segmenter.filter_diarization_for_segment(
            diarization, seg_start=10.0, seg_end=30.0, adjust_timestamps=True
        )
        
        # Les timestamps doivent être relatifs au début du segment
        assert len(result) == 2
        assert result[0]["start"] == 0.0  # 10 - 10 = 0
        assert result[0]["end"] == 10.0   # 20 - 10 = 10
        assert result[1]["start"] == 10.0 # 20 - 10 = 10
        assert result[1]["end"] == 20.0   # 30 - 10 = 20
    
    def test_filter_diarization_for_segment_partial_overlap(self, segmenter):
        """Vérifie le filtrage avec chevauchement partiel"""
        diarization = [
            {"start": 5.0, "end": 15.0, "speaker": "SPEAKER_00"},  # Chevauche partiellement
            {"start": 25.0, "end": 35.0, "speaker": "SPEAKER_01"},  # Chevauche partiellement
        ]
        
        # Filtrer pour le segment 10-30s
        result = segmenter.filter_diarization_for_segment(
            diarization, seg_start=10.0, seg_end=30.0, adjust_timestamps=True
        )
        
        # Les deux segments chevauchent la plage
        assert len(result) == 2
        
        # Premier segment: tronqué au début
        assert result[0]["start"] == 0.0  # max(0, 5-10) = 0
        assert result[0]["end"] == 5.0    # min(20, 15-10) = 5
        
        # Deuxième segment: tronqué à la fin
        assert result[1]["start"] == 15.0  # 25-10 = 15
        assert result[1]["end"] == 20.0    # min(30-10, 35-10) = 20
    
    def test_filter_diarization_empty_result(self, segmenter):
        """Vérifie le filtrage quand aucun segment ne correspond"""
        diarization = [
            {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_00"},
            {"start": 35.0, "end": 40.0, "speaker": "SPEAKER_01"},
        ]
        
        # Filtrer pour le segment 10-30s (aucun chevauchement)
        result = segmenter.filter_diarization_for_segment(
            diarization, seg_start=10.0, seg_end=30.0, adjust_timestamps=False
        )
        
        assert len(result) == 0
    
    def test_filter_diarization_empty_input(self, segmenter):
        """Vérifie le filtrage avec une liste vide"""
        result = segmenter.filter_diarization_for_segment(
            [], seg_start=10.0, seg_end=30.0, adjust_timestamps=False
        )
        
        assert result == []


class TestAudioSegmenterIntegration:
    """Tests d'intégration pour AudioSegmenter (nécessitent ffmpeg)"""
    
    @pytest.fixture
    def segmenter(self):
        return AudioSegmenter(max_segment_duration=60)
    
    @pytest.mark.skipif(
        os.system("which ffprobe > /dev/null 2>&1") != 0,
        reason="ffprobe n'est pas installé"
    )
    def test_get_audio_duration_nonexistent_file(self, segmenter):
        """Vérifie le comportement avec un fichier inexistant"""
        duration = segmenter.get_audio_duration("/nonexistent/file.wav")
        assert duration == 0.0
