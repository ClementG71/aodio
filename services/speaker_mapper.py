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
        """Initialise le modèle Spacy - chargement lazy"""
        self._nlp = None
        self._model_loaded = False
        logger.info("SpeakerMapper initialisé - modèle Spacy sera chargé à la première utilisation")
    
    def _get_nlp(self):
        """Charge le modèle Spacy de manière lazy (thread-safe)"""
        if self._model_loaded:
            return self._nlp
        
        # Double-checked locking pattern pour thread-safety
        if self._nlp is None:
            try:
                # Utilisation de md au lieu de lg pour économiser de la mémoire
                self._nlp = spacy.load("fr_core_news_md")
                self._model_loaded = True
                logger.info("Modèle Spacy 'fr_core_news_md' chargé avec succès")
            except OSError:
                logger.warning("Modèle Spacy 'fr_core_news_md' non trouvé. Tentative de téléchargement...")
                try:
                    from spacy.cli import download
                    download("fr_core_news_md")
                    self._nlp = spacy.load("fr_core_news_md")
                    self._model_loaded = True
                except Exception as e:
                    logger.error(f"Impossible de charger Spacy: {e}")
                    self._nlp = None
                    self._model_loaded = True
        
        return self._nlp

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
        nlp = self._get_nlp()
        if not nlp or not participants_list:
            logger.warning("Spacy non initialisé ou liste participants vide. Mapping impossible.")
            return {}, list(set(s.get('speaker') for s in transcription_segments if s.get('speaker')))

        # 1. Initialiser les scores
        speaker_scores = {
            s.get('speaker'): {} 
            for s in transcription_segments 
            if s.get('speaker') and s.get('speaker').startswith('SPEAKER_')
        }
        
        # File d'attente des locuteurs annoncés (Nom, Contexte Sémantique)
        # Contexte = doc Spacy de la phrase d'annonce pour comparaison
        expected_speakers = [] 
        
        identified_speakers = set() # Pour éviter de réattribuer un speaker déjà trouvé
        
        # 2. Analyser chaque segment
        for i, segment in enumerate(transcription_segments):
            text = segment.get('text', '')
            current_speaker = segment.get('speaker')
            
            if not text or not current_speaker:
                continue
                
            doc = nlp(text)
            
            # A. Vérification de la file d'attente (Attribution Différée)
            # Si on a des locuteurs attendus et que le speaker change
            if expected_speakers:
                prev_speaker = transcription_segments[i-1].get('speaker') if i > 0 else None
                
                # Si c'est un nouveau bloc de parole (changement de speaker ou début)
                if current_speaker != prev_speaker and current_speaker not in identified_speakers:
                    candidate_name, announcement_doc = expected_speakers[0]
                    
                    # Critères de validation
                    # 1. Marqueurs d'intro ("Bonjour", "Merci", "Alors")
                    is_intro = self._has_intro_markers(text)
                    
                    # 2. Similarité sémantique avec l'annonce (Sujet)
                    # On compare les 2 premières phrases du speaker avec l'annonce
                    intro_text = " ".join([s.text for s in list(doc.sents)[:2]])
                    intro_doc = nlp(intro_text)
                    similarity = intro_doc.similarity(announcement_doc) if announcement_doc.vector_norm else 0
                    
                    logger.info(f"Check différé: {candidate_name} pour {current_speaker} ? Intro={is_intro}, Sim={similarity:.2f}")
                    
                    if is_intro or similarity > 0.4: # Seuil de similarité empirique
                        self._add_score(speaker_scores, current_speaker, candidate_name, 50) # Score décisif
                        logger.info(f" Attribution différée réussie : {current_speaker} -> {candidate_name}")
                        identified_speakers.add(current_speaker)
                        expected_speakers.pop(0) # On retire de la file
            
            # B. Analyse NER (Détection Noms)
            for ent in doc.ents:
                if ent.label_ == "PER":
                    # Trouver le participant le plus proche
                    match, score = process.extractOne(ent.text, participants_list, scorer=fuzz.token_set_ratio)
                    
                    if score >= 80: 
                        # Analyse contextuelle
                        
                        # Cas 1 : Auto-nomination ("Je suis [Nom]")
                        if self._is_self_introduction(text, ent.text):
                            self._add_score(speaker_scores, current_speaker, match, 30)
                            identified_speakers.add(current_speaker)
                            
                        # Cas 2 : Hétéro-nomination / Annonce ("C'est [Nom] qui va...", "La parole est à [Nom]")
                        elif self._is_hetero_introduction(text, ent.text):
                            # On ajoute à la file d'attente, PAS au score du speaker courant
                            # On sauvegarde le contexte (la phrase entière)
                            expected_speakers.append((match, doc))
                            logger.info(f"Annonce détectée : {match} attendu (contexte: '{text[:50]}...')")
                            
                            # Score négatif pour le speaker courant (ce n'est pas lui)
                            self._add_score(speaker_scores, current_speaker, match, -10)
                                
                        # Cas 3 : Mention simple
                        else:
                            # Si ce n'est pas une intro explicite, on ignore ou score faible
                            # pour éviter les faux positifs (ex: "Comme disait X...")
                            pass

        # 3. Décision finale
        final_mapping = {}
        ambiguous_speakers = []
        CONFIDENCE_THRESHOLD = 15 
        
        for speaker, candidates in speaker_scores.items():
            if not candidates:
                ambiguous_speakers.append(speaker)
                continue
                
            sorted_candidates = sorted(candidates.items(), key=lambda x: x[1], reverse=True)
            top_name, top_score = sorted_candidates[0]
            
            is_clear_winner = True
            if len(sorted_candidates) > 1:
                second_name, second_score = sorted_candidates[1]
                if top_score - second_score < 5:
                    is_clear_winner = False
            
            if top_score >= CONFIDENCE_THRESHOLD and is_clear_winner:
                final_mapping[speaker] = top_name
            else:
                ambiguous_speakers.append(speaker)
                
        return final_mapping, ambiguous_speakers

    def _add_score(self, scores: Dict, speaker: str, name: str, points: int):
        if speaker not in scores:
            scores[speaker] = {}
        scores[speaker][name] = scores[speaker].get(name, 0) + points

    def _is_self_introduction(self, text: str, name: str) -> bool:
        """Détecte si le texte est une auto-présentation"""
        text_lower = text.lower()
        name_lower = name.lower().split()[0] # Prénom seulement souvent utilisé
        patterns = [
            f"je suis {name_lower}",
            f"m'appelle {name_lower}",
            f"ici {name_lower}",
            f"c'est {name_lower} à", # "C'est Antoine à l'appareil"
            f"moi c'est {name_lower}"
        ]
        return any(p in text_lower for p in patterns)

    def _is_hetero_introduction(self, text: str, name: str) -> bool:
        """Détecte si le texte annonce quelqu'un d'autre"""
        text_lower = text.lower()
        name_lower = name.lower().split()[0]
        patterns = [
            f"parole est à {name_lower}",
            f"laisse la parole à {name_lower}",
            f"la main à {name_lower}",
            f"merci {name_lower}",
            f"c'est {name_lower} qui", # "C'est Antoine qui va présenter"
            f"appeler {name_lower}",
            f"inviter {name_lower}"
        ]
        return any(p in text_lower for p in patterns)
        
    def _has_intro_markers(self, text: str) -> bool:
        """Vérifie si le texte commence par des marqueurs d'introduction"""
        intro_markers = ["bonjour", "merci", "alors", "donc", "tout d'abord", "pour commencer"]
        doc = nlp(text[:100].lower())
        # Vérifier les 3 premiers mots
        for token in list(doc)[:5]:
            if token.text in intro_markers:
                return True
        return False
