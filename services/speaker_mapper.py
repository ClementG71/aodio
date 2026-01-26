"""
Service de mapping des locuteurs utilisant Spacy et Fuzzy Matching
Permet d'identifier les locuteurs sans utiliser systématiquement un LLM
"""
import logging
import re
from fuzzywuzzy import process, fuzz
from typing import Dict, List, Any, Tuple, Optional

from services.nlp_service import get_nlp

logger = logging.getLogger(__name__)

class SpeakerMapper:
    """
    Identifie les locuteurs en analysant le texte avec Spacy (NER)
    et en matchant avec une liste de participants connue.
    """
    
    def __init__(self):
        """Initialise le mapper - utilise le singleton Spacy"""
        logger.info("SpeakerMapper initialisé - utilisera le singleton Spacy")
    
    def _get_nlp(self):
        """Retourne l'instance Spacy partagée (singleton)"""
        return get_nlp()

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
        nlp = self._get_nlp()
        if not nlp:
            return False
        doc = nlp(text[:100].lower())
        # Vérifier les 3 premiers mots
        for token in list(doc)[:5]:
            if token.text in intro_markers:
                return True
        return False


class EnhancedSpeakerMapper:
    """
    Mapper amélioré qui analyse les caractéristiques comportementales de chaque speaker
    pour améliorer l'identification des locuteurs avec un LLM.
    """
    
    def __init__(self):
        """Initialise le mapper amélioré"""
        pass
    
    def analyze_speaker_characteristics(self, 
                                      segments: List[Dict[str, Any]], 
                                      participants: List[str],
                                      president: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """
        Analyse chaque SPEAKER_XX pour extraire des caractéristiques comportementales.
        
        Args:
            segments: Liste des segments de transcription
            participants: Liste des participants connus
            president: Nom du président de séance (optionnel)
            
        Returns:
            dict: Statistiques par speaker avec caractéristiques extraites
        """
        if not segments:
            return {}
        
        # Grouper les segments par speaker
        speaker_segments = {}
        for seg in segments:
            speaker = seg.get('speaker', 'UNKNOWN')
            if speaker.startswith('SPEAKER_'):
                if speaker not in speaker_segments:
                    speaker_segments[speaker] = []
                speaker_segments[speaker].append(seg)
        
        # Calculer la durée totale de la réunion
        all_starts = [s.get('start', 0) for s in segments if s.get('start')]
        all_ends = [s.get('end', 0) for s in segments if s.get('end')]
        total_duration = max(all_ends) - min(all_starts) if all_starts and all_ends else 0
        
        speaker_stats = {}
        
        for speaker, segs in speaker_segments.items():
            if not segs:
                continue
            
            # Calculer les durées
            durations = [s.get('end', 0) - s.get('start', 0) for s in segs if s.get('start') and s.get('end')]
            total_duration_speaker = sum(durations)
            
            # Extraire les timestamps
            starts = [s.get('start', 0) for s in segs if s.get('start')]
            ends = [s.get('end', 0) for s in segs if s.get('end')]
            
            # Extraire les textes
            texts = [s.get('text', '').strip() for s in segs if s.get('text', '').strip()]
            
            # Analyser les patterns de langage
            gives_floor_count = sum(1 for text in texts 
                                   if re.search(r'(parole est à|la parole à|laisse la parole|donne la parole)', 
                                               text.lower()))
            asks_questions_count = sum(1 for text in texts if '?' in text)
            
            # Extraire les noms mentionnés (approximation simple)
            mentioned_names = []
            for text in texts[:10]:  # Limiter pour performance
                # Chercher des patterns de noms (majuscules suivies de minuscules)
                name_patterns = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', text)
                for name in name_patterns:
                    # Vérifier si c'est un participant
                    for participant in participants:
                        if name.lower() in participant.lower() or participant.lower() in name.lower():
                            if name not in mentioned_names:
                                mentioned_names.append(name)
            
            # Position temporelle dans la réunion
            first_appearance = min(starts) if starts else 0
            last_appearance = max(ends) if ends else 0
            position_in_meeting = "début" if first_appearance < total_duration * 0.2 else \
                                  "fin" if first_appearance > total_duration * 0.8 else "milieu"
            
            # Extraits représentatifs (premiers segments avec texte)
            sample_texts = texts[:5]  # Premiers 5 segments
            
            speaker_stats[speaker] = {
                'total_duration': total_duration_speaker,
                'duration_percentage': (total_duration_speaker / total_duration * 100) if total_duration > 0 else 0,
                'segment_count': len(segs),
                'first_appearance': first_appearance,
                'last_appearance': last_appearance,
                'position_in_meeting': position_in_meeting,
                'sample_texts': sample_texts,
                'gives_floor_count': gives_floor_count,
                'asks_questions_count': asks_questions_count,
                'mentioned_names': mentioned_names[:5],  # Limiter à 5
                'avg_segment_duration': total_duration_speaker / len(segs) if segs else 0
            }
        
        return speaker_stats
    
    def build_llm_context(self, 
                         speaker_stats: Dict[str, Dict[str, Any]], 
                         participants: List[str],
                         president: Optional[str] = None) -> str:
        """
        Construit un prompt riche pour le LLM avec toutes les caractéristiques extraites.
        
        Args:
            speaker_stats: Statistiques par speaker
            participants: Liste des participants
            president: Nom du président
            
        Returns:
            str: Contexte formaté pour le prompt LLM
        """
        lines = []
        lines.append("PARTICIPANTS CONNUS:")
        for p in participants:
            if president and p == president:
                lines.append(f"  - {p} (PRÉSIDENT DE SÉANCE)")
            else:
                lines.append(f"  - {p}")
        lines.append("")
        
        lines.append("ANALYSE DES LOCUTEURS:")
        lines.append("")
        
        # Trier les speakers par ordre d'apparition
        sorted_speakers = sorted(speaker_stats.items(), 
                                key=lambda x: x[1].get('first_appearance', 0))
        
        for speaker, stats in sorted_speakers:
            lines.append(f"{speaker}:")
            lines.append(f"  - Durée totale de parole: {stats['total_duration']:.1f}s ({stats['duration_percentage']:.1f}% de la réunion)")
            lines.append(f"  - Nombre de segments: {stats['segment_count']}")
            lines.append(f"  - Position dans la réunion: {stats['position_in_meeting']} (apparition à {stats['first_appearance']:.1f}s)")
            lines.append(f"  - Donne la parole: {stats['gives_floor_count']} fois")
            lines.append(f"  - Pose des questions: {stats['asks_questions_count']} fois")
            if stats['mentioned_names']:
                lines.append(f"  - Noms mentionnés: {', '.join(stats['mentioned_names'])}")
            lines.append(f"  - Extraits représentatifs:")
            for i, text in enumerate(stats['sample_texts'][:3], 1):
                text_preview = text[:150] + "..." if len(text) > 150 else text
                lines.append(f"    {i}. \"{text_preview}\"")
            lines.append("")
        
        return "\n".join(lines)
