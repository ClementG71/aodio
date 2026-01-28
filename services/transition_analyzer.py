"""
TransitionAnalyzer
-------------------

Analyse les transitions entre locuteurs pour extraire des indices du type :
- "Merci Jean"        -> le locuteur précédent est probablement Jean
- "Jean, vous avez la parole" -> le prochain locuteur sera Jean
"""

import re
from typing import Dict, List, Any


class TransitionAnalyzer:
    """Analyse qui parle après qui pour améliorer l'identification des locuteurs."""

    # (pattern, type)
    # type:
    #   - "previous_speaker" : le nom correspond au locuteur précédent
    #   - "next_speaker"     : le nom correspond au locuteur suivant
    TRANSITION_PATTERNS = [
        (r"merci\s+([A-ZÉÈÊËÀÂÄÔÖÛÜ][\w\-]+)", "previous_speaker"),
        (r"([A-ZÉÈÊËÀÂÄÔÖÛÜ][\w\-]+),?\s+vous avez la parole", "next_speaker"),
        (r"c['’]est\s+([A-ZÉÈÊËÀÂÄÔÖÛÜ][\w\-]+)\s+qui va", "next_speaker"),
        (r"je passe la parole [àa]\s+([A-ZÉÈÊËÀÂÄÔÖÛÜ][\w\-]+)", "next_speaker"),
    ]

    def analyze_transitions(self, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Parcourt les segments et détecte les transitions explicites.

        Args:
            segments: segments alignés {start, end, speaker, text}

        Returns:
            Liste d'objets transition :
            {
              "index": i,                # index du segment où la phrase est prononcée
              "pattern_type": "previous_speaker" | "next_speaker",
              "name": "Jean"
            }
        """
        transitions: List[Dict[str, Any]] = []
        if not segments:
            return transitions

        for idx, seg in enumerate(segments):
            text = (seg.get("text") or "").strip()
            if not text:
                continue

            lower = text.lower()
            for pattern, p_type in self.TRANSITION_PATTERNS:
                match = re.search(pattern, text)
                if match:
                    name = match.group(1)
                    transitions.append(
                        {
                            "index": idx,
                            "pattern_type": p_type,
                            "name": name,
                            "raw_text": text,
                        }
                    )
                    break  # on ne prend qu'un pattern par segment

        return transitions

    def apply_transition_hints(
        self,
        mapping: Dict[str, str],
        transitions: List[Dict[str, Any]],
        segments: List[Dict[str, Any]],
        participants: List[str],
    ) -> Dict[str, str]:
        """
        Enrichit le mapping existant avec les indices de transition.

        Règles simples :
        - previous_speaker : si le segment précédent a un speaker SPEAKER_XX
          non encore mappé et que le nom détecté correspond à un participant,
          on complète le mapping.
        - next_speaker : idem pour le segment suivant.
        - On ne remplace PAS un mapping existant (principe de prudence).
        """
        if not segments or not transitions:
            return mapping

        participants_lower = {p.lower(): p for p in participants}
        new_mapping = dict(mapping)  # copie

        for t in transitions:
            idx = t["index"]
            name_mentioned = t["name"]
            p_type = t["pattern_type"]

            # Tenter de faire correspondre le nom détecté à un participant
            candidate_full_name = None
            for p_lower, full in participants_lower.items():
                if name_mentioned.lower() in p_lower or p_lower in name_mentioned.lower():
                    candidate_full_name = full
                    break

            if not candidate_full_name:
                continue

            if p_type == "previous_speaker" and idx > 0:
                prev_seg = segments[idx - 1]
                speaker_code = prev_seg.get("speaker")
            elif p_type == "next_speaker" and idx + 1 < len(segments):
                next_seg = segments[idx + 1]
                speaker_code = next_seg.get("speaker")
            else:
                continue

            if not speaker_code or not str(speaker_code).startswith("SPEAKER_"):
                continue

            if speaker_code in new_mapping:
                # On ne remplace pas un mapping existant
                continue

            new_mapping[speaker_code] = candidate_full_name

        return new_mapping

