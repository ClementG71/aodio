"""
Service de mapping des locuteurs utilisant Spacy et Fuzzy Matching
Permet d'identifier les locuteurs sans utiliser systématiquement un LLM
"""
import logging
import spacy
from fuzzywuzzy import process, fuzz
from typing import Dict, List, Any, Tuple, Optional

logger = logging.getLogger(__name__)

class SpeakerMapper:
    """
    Identifie les locuteurs en analysant le texte avec Spacy (NER)
    et en matchant avec une liste de participants connue.
    """
    
    def __init__(self):
        """Initialise le modèle Spacy"""
        try:
            # Charger le modèle français large pour une meilleure précision NER
            self.nlp = spacy.load("fr_core_news_lg")
            logger.info("Modèle Spacy 'fr_core_news_lg' chargé avec succès")
        except OSError:
            logger.warning("Modèle Spacy 'fr_core_news_lg' non trouvé. Tentative de téléchargement...")
            # Fallback si l'installation via requirements.txt a échoué (rare en prod)
            try:
                from spacy.cli import download
                download("fr_core_news_lg")
                self.nlp = spacy.load("fr_core_news_lg")
            except Exception as e:
                logger.error(f"Impossible de charger Spacy: {e}")
                self.nlp = None

    def identify_speakers(self, 
                         transcription_segments: List[Dict[str, Any]], 
                         participants_list: List[str]) -> Tuple[Dict[str, str], List[str]]:
        """
        Identifie les locuteurs à partir des segments de transcription.
        
        Args:
            transcription_segments: Liste des segments (text, speaker, ...)
            participants_list: Liste des noms réels des participants
            
        Returns:
            Tuple contenant:
            - Dict[str, str]: Mapping validé {SPEAKER_XX: "Nom Réel"}
            - List[str]: Liste des SPEAKER_XX ambigus nécessitant un fallback LLM
        """
        if not self.nlp or not participants_list:
            logger.warning("Spacy non initialisé ou liste participants vide. Mapping impossible.")
            return {}, list(set(s.get('speaker') for s in transcription_segments if s.get('speaker')))

        # 1. Initialiser les scores
        # Structure: { "SPEAKER_00": { "Jean Dupont": 15, "Marie Curie": 5 } }
        speaker_scores = {
            s.get('speaker'): {} 
            for s in transcription_segments 
            if s.get('speaker') and s.get('speaker').startswith('SPEAKER_')
        }
        
        # 2. Analyser chaque segment
        for i, segment in enumerate(transcription_segments):
            text = segment.get('text', '')
            current_speaker = segment.get('speaker')
            
            if not text or not current_speaker:
                continue
                
            doc = self.nlp(text)
            
            # Détection d'auto-présentation ("Je suis Jean") ou d'adresse ("Merci Jean")
            for ent in doc.ents:
                if ent.label_ == "PER":
                    # Trouver le participant le plus proche
                    # Utiliser token_set_ratio pour mieux gérer les noms partiels (ex: "Einstein" vs "Albert Einstein")
                    match, score = process.extractOne(ent.text, participants_list, scorer=fuzz.token_set_ratio)
                    
                    if score >= 80: # Seuil de confiance ajusté (85 -> 80) pour accepter "M. Einstein" -> "Albert Einstein"
                        # Analyse contextuelle basique
                        
                        # Cas A : Auto-nomination ("Je suis [Nom]")
                        if self._is_self_introduction(text, ent.text):
                            self._add_score(speaker_scores, current_speaker, match, 20)
                            
                        # Cas B : Nomination directe ("La parole est à [Nom]")
                        # Si le speaker actuel nomme quelqu'un, c'est probablement le SUIVANT qui parle
                        elif self._is_giving_floor(text, ent.text) and i + 1 < len(transcription_segments):
                            next_speaker = transcription_segments[i+1].get('speaker')
                            if next_speaker and next_speaker != current_speaker:
                                self._add_score(speaker_scores, next_speaker, match, 15)
                                
                        # Cas C : Mention simple ("Comme disait [Nom]")
                        # Peut indiquer que [Nom] a parlé juste avant ou va parler
                        else:
                            # Indice faible, on l'ajoute quand même
                            self._add_score(speaker_scores, current_speaker, match, 2)

        # 3. Décision finale
        final_mapping = {}
        ambiguous_speakers = []
        
        # Seuil pour valider une identification sans LLM
        CONFIDENCE_THRESHOLD = 15 
        
        for speaker, candidates in speaker_scores.items():
            if not candidates:
                ambiguous_speakers.append(speaker)
                continue
                
            # Trouver le meilleur candidat
            sorted_candidates = sorted(candidates.items(), key=lambda x: x[1], reverse=True)
            top_name, top_score = sorted_candidates[0]
            
            # Vérifier l'écart avec le second (s'il existe)
            is_clear_winner = True
            if len(sorted_candidates) > 1:
                second_name, second_score = sorted_candidates[1]
                if top_score - second_score < 5: # Écart trop faible
                    is_clear_winner = False
            
            if top_score >= CONFIDENCE_THRESHOLD and is_clear_winner:
                final_mapping[speaker] = top_name
                logger.info(f"Speaker identifié (Spacy): {speaker} -> {top_name} (Score: {top_score})")
            else:
                ambiguous_speakers.append(speaker)
                logger.info(f"Speaker ambigu: {speaker} (Top: {top_name} avec {top_score} pts)")
                
        return final_mapping, ambiguous_speakers

    def _add_score(self, scores: Dict, speaker: str, name: str, points: int):
        """Ajoute des points à un candidat pour un speaker donné"""
        if speaker not in scores:
            scores[speaker] = {}
        scores[speaker][name] = scores[speaker].get(name, 0) + points

    def _is_self_introduction(self, text: str, name: str) -> bool:
        """Détecte si le texte est une auto-présentation"""
        text_lower = text.lower()
        patterns = [
            f"je suis {name.lower()}",
            f"je m'appelle {name.lower()}",
            f"ici {name.lower()}",
            f"c'est {name.lower()}"
        ]
        return any(p in text_lower for p in patterns)

    def _is_giving_floor(self, text: str, name: str) -> bool:
        """Détecte si le texte donne la parole à quelqu'un"""
        text_lower = text.lower()
        patterns = [
            f"parole est à {name.lower()}",
            f"parole est à monsieur {name.lower()}",
            f"parole est à madame {name.lower()}",
            f"merci {name.lower()}",
            f"allez-y {name.lower()}"
        ]
        return any(p in text_lower for p in patterns)
