"""
TemporalSpeakerMapper
----------------------

Utilitaire pour découper la réunion en blocs temporels et consolider
les mappings de locuteurs bloc par bloc.
"""

from typing import Dict, List, Any, Tuple


class TemporalSpeakerMapper:
    """
    Découpe les segments alignés en blocs temporels (par ex. 30–45 min) et
    aide à consolider les mappings {SPEAKER_XX -> Nom} entre blocs.
    """

    def __init__(self, block_duration_minutes: int = 45) -> None:
        # Durée d'un bloc en secondes
        self.block_duration = block_duration_minutes * 60

    def split_into_blocks(self, segments: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """
        Découpe la liste complète des segments en blocs temporels.

        Args:
            segments: segments alignés {start, end, speaker, text}

        Returns:
            Liste de blocs, chaque bloc étant une liste de segments.
        """
        if not segments:
            return []

        # On suppose les segments déjà triés par temps
        sorted_segments = sorted(segments, key=lambda s: s.get("start", 0.0))
        first_start = sorted_segments[0].get("start", 0.0)

        blocks: List[List[Dict[str, Any]]] = []
        current_block: List[Dict[str, Any]] = []
        current_block_index = 0

        for seg in sorted_segments:
            start = float(seg.get("start", 0.0))
            # Indice de bloc basé sur le temps relatif
            block_index = int((start - first_start) // self.block_duration)

            if block_index != current_block_index and current_block:
                blocks.append(current_block)
                current_block = []
                current_block_index = block_index

            current_block.append(seg)

        if current_block:
            blocks.append(current_block)

        return blocks

    def consolidate_mappings(self, block_mappings: List[Dict[str, str]]) -> Dict[str, str]:
        """
        Consolide les mappings de tous les blocs avec une stratégie simple :

        - Si un SPEAKER_XX est mappé de la même manière dans plusieurs blocs,
          on garde ce nom.
        - En cas de conflit (SPEAKER_01 -> Jean puis SPEAKER_01 -> Marie),
          on garde le premier nom rencontré (principe de stabilité temporelle).

        Args:
            block_mappings: liste de dicts {SPEAKER_XX: "Nom"} par bloc

        Returns:
            Mapping global consolidé.
        """
        global_mapping: Dict[str, str] = {}

        for mapping in block_mappings:
            for speaker, name in mapping.items():
                if speaker not in global_mapping:
                    # Premier mapping rencontré pour ce speaker : on le garde
                    global_mapping[speaker] = name
                else:
                    # Conflit éventuel : si le nom diffère, on garde le premier
                    if global_mapping[speaker] != name:
                        # Conflits potentiels : on pourrait les loguer plus tard si nécessaire
                        continue

        return global_mapping

