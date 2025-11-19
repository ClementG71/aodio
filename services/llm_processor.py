"""
Service de traitement LLM avec Claude Sonnet 4.5
Mapping des locuteurs, génération pré-CR, extraction des décisions
"""
import json
import logging
from typing import Dict, List, Any, Optional
from anthropic import Anthropic, RateLimitError, APIError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)


class LLMProcessor:
    """Gère les traitements LLM avec Claude Sonnet 4.5"""
    
    def __init__(self, api_key: str):
        self.client = Anthropic(api_key=api_key)
        # Claude Sonnet 4.5 - utiliser le modèle le plus récent disponible
        self.model = "claude-sonnet-4-20250514"  # À adapter selon la version disponible
        self.max_tokens = 4096  # Limite par appel pour éviter la surcharge
    
    def map_speakers(self, transcription_result: Dict[str, Any], 
                    liste_participants_path: Optional[str] = None,
                    president_seance: Optional[str] = None) -> Dict[str, str]:
        """
        Mappe les labels SPEAKER_XX vers les noms réels des locuteurs
        
        Args:
            transcription_result: Résultat de la transcription avec segments
            liste_participants_path: Chemin vers le fichier liste des participants
            president_seance: Nom du président de séance
            
        Returns:
            dict: Mapping {SPEAKER_00: "Nom", ...}
        """
        try:
            logger.info("Démarrage du mapping des locuteurs")
            
            # Vérifier que la transcription contient des segments
            segments = transcription_result.get('segments', [])
            if not segments:
                logger.error("Aucun segment dans le résultat de transcription!")
                return {}
            
            # Vérifier qu'il y a du texte dans au moins quelques segments
            segments_with_text = sum(1 for seg in segments if seg.get('text', '').strip())
            logger.info(f"Segments pour mapping: {len(segments)} total, {segments_with_text} avec texte")
            
            if segments_with_text == 0:
                logger.error("Aucun segment ne contient de texte! Le mapping ne peut pas fonctionner.")
                # Retourner un mapping vide ou basé uniquement sur les labels
                return {}
            
            # Lecture de la liste des participants si fournie
            participants_list = ""
            if liste_participants_path:
                try:
                    # Essayer UTF-8 d'abord, puis fallback sur latin-1 (Windows-1252 compatible)
                    try:
                        with open(liste_participants_path, 'r', encoding='utf-8') as f:
                            participants_list = f.read()
                    except UnicodeDecodeError:
                        # Fallback sur latin-1 si UTF-8 échoue
                        with open(liste_participants_path, 'r', encoding='latin-1') as f:
                            participants_list = f.read()
                except Exception as e:
                    logger.warning(f"Impossible de lire la liste des participants: {e}")
            
            # Préparation de la transcription pour l'analyse
            segments_text = self._format_segments_for_mapping(transcription_result)
            
            # Log du texte formaté pour déboguer (premiers 500 caractères)
            logger.debug(f"Texte formaté pour mapping (premiers 500 caractères): {segments_text[:500]}")
            
            # Construction du prompt
            prompt = f"""Tu es un assistant qui analyse des transcriptions de réunions pour identifier les locuteurs.

CONTEXTE IMPORTANT :
- Les labels SPEAKER_00, SPEAKER_01, etc. sont COHÉRENTS dans toute la transcription
- Si SPEAKER_00 est identifié comme "Antoine Picard" à 00:05:00, alors SPEAKER_00 est TOUJOURS "Antoine Picard" dans toute la réunion
- Pyannote garantit qu'un même label = même personne tout au long de la session

TÂCHE :
Identifie QUI est CHAQUE SPEAKER en analysant :
1. Les présentations directes ("Je m'appelle X", "Bonjour, je suis X", "Ici X")
2. Le contexte conversationnel ("comme disait Antoine", "Marie a raison")
3. Les rôles mentionnés ("le directeur", "l'ingénieur", "le client")
4. La liste des participants si fournie

RÈGLES :
- Un SPEAKER = UN nom (mapping 1:1 persistant)
- Si incertain, garde le label générique (SPEAKER_XX)
- Retourne UNIQUEMENT un JSON valide, sans texte avant/après

FORMAT DE RÉPONSE (JSON uniquement) :
{{
"SPEAKER_00": "Antoine Picard",
"SPEAKER_01": "Marie Dubois",
"SPEAKER_02": "SPEAKER_02"
}}

TRANSCRIPTION :
{segments_text}

{f"LISTE DES PARTICIPANTS :\n{participants_list}" if participants_list else ""}
{f"PRÉSIDENT DE SÉANCE : {president_seance}" if president_seance else ""}
"""
            
            # Appel à Claude avec gestion de la limite de tokens
            response = self._call_claude_safe(prompt)
            
            # Extraction du JSON de la réponse
            mapping = self._extract_json_from_response(response)
            
            logger.info(f"Mapping terminé: {len(mapping)} locuteurs identifiés")
            return mapping
            
        except Exception as e:
            logger.error(f"Erreur lors du mapping des locuteurs: {str(e)}", exc_info=True)
            # Retour d'un mapping vide en cas d'erreur
            return {}
    
    def generate_pre_cr(self, transcription_result: Dict[str, Any],
                       speaker_mapping: Dict[str, str],
                       president_seance: Optional[str] = None) -> str:
        """
        Génère le pré-compte rendu à partir de la transcription
        
        Args:
            transcription_result: Résultat de la transcription
            speaker_mapping: Mapping des locuteurs
            president_seance: Nom du président de séance
            
        Returns:
            str: Pré-compte rendu formaté
        """
        try:
            logger.info("Génération du pré-compte rendu")
            
            # Vérifier que la transcription contient des segments
            segments = transcription_result.get('segments', [])
            if not segments:
                logger.error("Aucun segment dans le résultat de transcription pour le pré-CR!")
                return "Aucune transcription disponible."
            
            # Formatage de la transcription avec mapping des locuteurs
            # Utiliser une version limitée pour éviter les erreurs de rate limit
            formatted_transcription = self._format_segments_with_text_only(
                transcription_result, max_segments=100, max_chars=50000
            )
            
            # Vérifier que le texte formaté n'est pas vide
            if not formatted_transcription or formatted_transcription.strip() == "":
                logger.error("Le texte formaté pour le pré-CR est vide!")
                return "Aucune transcription textuelle disponible. Les segments de diarisation ont été détectés mais aucun texte n'a été transcrit."
            
            # Log du texte formaté pour déboguer (premiers 1000 caractères)
            logger.debug(f"Texte formaté pour pré-CR (premiers 1000 caractères): {formatted_transcription[:1000]}")
            
            prompt = f"""Objectif :
- Transformer la transcription brute verbatim en un document professionnel lisible
- Conserver toutes les informations importantes tout en éliminant le langage oral informel

Instructions clés :

1. Conservation stricte :
- Tous les locuteurs et leur identification
- Toutes les informations, décisions, votes, actions
- Structure chronologique des échanges

2. Nettoyage :
- Suppression des mots parasites : "euh", "ben", "voilà", "donc", "alors"
- Élimination des hésitations, répétitions, faux départs
- Suppression des réponses courtes sans valeur ajoutée ("oui", "d'accord")
- Correction des phrases mal construites

3. Reformulation :
- Clarification et concision des interventions
- Français professionnel et soigné
- Ton neutre et factuel
- Préservation des nuances et positions

4. Format de sortie :
- Même structure que l'entrée avec locuteurs
- Conservation des segments temporels si présents
- Interventions reformulées en phrases complètes

TRANSCRIPTION :
{formatted_transcription}

{f"PRÉSIDENT DE SÉANCE : {president_seance}" if president_seance else ""}
"""
            
            # Traitement par chunks si nécessaire
            pre_cr = self._call_claude_safe(prompt)
            
            logger.info("Pré-compte rendu généré avec succès")
            return pre_cr
            
        except Exception as e:
            logger.error(f"Erreur lors de la génération du pré-CR: {str(e)}", exc_info=True)
            return "Erreur lors de la génération du pré-compte rendu."
    
    def extract_decisions(self, transcription_result: Dict[str, Any],
                         releves_votes_path: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Extrait les décisions de la réunion basées sur la feuille de relevés de votes
        
        Args:
            transcription_result: Résultat de la transcription
            releves_votes_path: Chemin vers le fichier de relevés de votes
            
        Returns:
            list: Liste des décisions extraites
        """
        try:
            logger.info("Extraction des décisions")
            
            # Lecture des relevés de votes si fournis
            releves_votes = ""
            if releves_votes_path:
                try:
                    # Essayer UTF-8 d'abord, puis fallback sur latin-1 (Windows-1252 compatible)
                    try:
                        with open(releves_votes_path, 'r', encoding='utf-8') as f:
                            releves_votes = f.read()
                    except UnicodeDecodeError:
                        # Fallback sur latin-1 si UTF-8 échoue
                        with open(releves_votes_path, 'r', encoding='latin-1') as f:
                            releves_votes = f.read()
                except Exception as e:
                    logger.warning(f"Impossible de lire les relevés de votes: {e}")
            
            # Utiliser uniquement les segments avec texte pour éviter les prompts trop longs
            formatted_transcription = self._format_segments_with_text_only(
                transcription_result, max_segments=100, max_chars=50000
            )
            
            prompt = f"""Extrais les décisions prises durant la réunion en te basant strictement sur la feuille des relevés de votes fournie.

INSTRUCTIONS :
1. Utilise UNIQUEMENT la feuille des relevés de votes comme source de vérité
2. Vérifie dans la transcription que chaque décision mentionnée dans les relevés a bien été discutée
3. Retourne un JSON avec la liste des décisions

FORMAT DE RÉPONSE (JSON uniquement) :
{{
"decisions": [
    {{
        "numero": "1",
        "titre": "Titre de la décision",
        "description": "Description détaillée",
        "vote": "Adopté à l'unanimité",
        "timestamp": "00:15:30"
    }},
    ...
]
}}

FEUILLE DES RELEVÉS DE VOTES :
{releves_votes if releves_votes else "Aucune feuille de relevés de votes fournie"}

TRANSCRIPTION (pour vérification - segments avec texte uniquement) :
{formatted_transcription}
"""
            
            response = self._call_claude_safe(prompt)
            decisions_data = self._extract_json_from_response(response)
            
            decisions = decisions_data.get('decisions', [])
            logger.info(f"{len(decisions)} décisions extraites")
            return decisions
            
        except Exception as e:
            logger.error(f"Erreur lors de l'extraction des décisions: {str(e)}", exc_info=True)
            return []
    
    def _format_segments_for_mapping(self, transcription_result: Dict[str, Any]) -> str:
        """Formate les segments pour l'analyse de mapping"""
        segments = transcription_result.get('segments', [])
        formatted = []
        segments_with_text = 0
        segments_without_text = 0
        
        for seg in segments:
            speaker = seg.get('speaker', 'UNKNOWN')
            text = seg.get('text', '').strip()
            start = seg.get('start', 0)
            end = seg.get('end', 0)
            
            # Compter les segments avec/sans texte
            if text:
                segments_with_text += 1
            else:
                segments_without_text += 1
            
            time_str = f"[{self._format_time(start)} - {self._format_time(end)}]"
            # Inclure même les segments vides pour le contexte temporel
            formatted.append(f"{time_str} {speaker}: {text if text else '[silence ou texte non transcrit]'}")
        
        logger.info(f"Formatage segments pour mapping: {segments_with_text} avec texte, {segments_without_text} sans texte sur {len(segments)} total")
        
        if segments_with_text == 0:
            logger.warning("ATTENTION: Aucun segment ne contient de texte! Le mapping ne pourra pas fonctionner correctement.")
        
        return "\n".join(formatted)
    
    def _format_segments_with_text_only(self, transcription_result: Dict[str, Any],
                                        max_segments: int = 100,
                                        max_chars: int = 50000) -> str:
        """
        Formate uniquement les segments avec texte, avec limites pour éviter les prompts trop longs
        
        Args:
            transcription_result: Résultat de la transcription
            max_segments: Nombre maximum de segments à inclure
            max_chars: Nombre maximum de caractères à inclure
            
        Returns:
            str: Texte formaté avec uniquement les segments contenant du texte
        """
        segments = transcription_result.get('segments', [])
        
        # Filtrer uniquement les segments avec texte
        segments_with_text = [seg for seg in segments if seg.get('text', '').strip()]
        
        logger.info(f"Formatage segments avec texte uniquement: {len(segments_with_text)} segments avec texte sur {len(segments)} total")
        
        if not segments_with_text:
            logger.warning("Aucun segment avec texte trouvé!")
            return "Aucune transcription textuelle disponible."
        
        # Limiter le nombre de segments
        if len(segments_with_text) > max_segments:
            logger.warning(f"Trop de segments avec texte ({len(segments_with_text)}), limitation à {max_segments}")
            segments_with_text = segments_with_text[:max_segments]
        
        # Formater les segments
        formatted = []
        total_chars = 0
        
        for seg in segments_with_text:
            speaker = seg.get('speaker', 'UNKNOWN')
            text = seg.get('text', '').strip()
            start = seg.get('start', 0)
            end = seg.get('end', 0)
            
            time_str = f"[{self._format_time(start)} - {self._format_time(end)}]"
            line = f"{time_str} {speaker}: {text}"
            
            # Vérifier la limite de caractères
            if total_chars + len(line) > max_chars:
                logger.warning(f"Limite de caractères atteinte ({max_chars}), troncature du texte")
                remaining_chars = max_chars - total_chars
                if remaining_chars > 100:  # Au moins 100 caractères pour le dernier segment
                    line = line[:remaining_chars - 50] + "... [texte tronqué]"
                    formatted.append(line)
                break
            
            formatted.append(line)
            total_chars += len(line) + 1  # +1 pour le \n
        
        result = "\n".join(formatted)
        logger.info(f"Formatage terminé: {len(formatted)} segments, {len(result)} caractères")
        return result
    
    def _format_transcription_with_speakers(self, transcription_result: Dict[str, Any],
                                          speaker_mapping: Dict[str, str]) -> str:
        """Formate la transcription avec les noms réels des locuteurs"""
        segments = transcription_result.get('segments', [])
        formatted = []
        segments_with_text = 0
        total_text_length = 0
        
        for seg in segments:
            speaker_label = seg.get('speaker', 'UNKNOWN')
            speaker_name = speaker_mapping.get(speaker_label, speaker_label)
            text = seg.get('text', '').strip()
            start = seg.get('start', 0)
            
            if text:
                segments_with_text += 1
                total_text_length += len(text)
            
            time_str = self._format_time(start)
            # Ne pas inclure les segments complètement vides dans le pré-CR
            if text:
                formatted.append(f"[{time_str}] {speaker_name}: {text}")
        
        logger.info(f"Formatage transcription pour pré-CR: {segments_with_text} segments avec texte ({total_text_length} caractères) sur {len(segments)} total")
        
        if segments_with_text == 0:
            logger.error("ERREUR CRITIQUE: Aucun segment ne contient de texte! Le pré-CR sera vide.")
            return "Aucune transcription textuelle disponible. Les segments de diarisation ont été détectés mais aucun texte n'a été transcrit."
        
        return "\n".join(formatted)
    
    def _format_time(self, seconds: float) -> str:
        """Formate les secondes en HH:MM:SS"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        retry=retry_if_exception_type((RateLimitError, APIError))
    )
    def _call_claude_safe(self, prompt: str) -> str:
        """
        Appelle Claude en gérant la limite de tokens et les rate limits avec backoff
        
        Args:
            prompt: Prompt à envoyer
            
        Returns:
            str: Réponse de Claude
        """
        try:
            # Estimation de la taille du prompt (approximatif)
            prompt_tokens = len(prompt.split()) * 1.3  # Approximation
            
            # Si le prompt est trop long, on le tronque
            if prompt_tokens > 100000:  # Limite de sécurité
                logger.warning("Prompt trop long, troncature nécessaire")
                # Tronquer intelligemment (garder le début et la fin)
                max_chars = 200000  # Limite approximative
                if len(prompt) > max_chars:
                    prompt = prompt[:max_chars//2] + "\n\n[... contenu tronqué ...]\n\n" + prompt[-max_chars//2:]
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=0.3,  # Pour le pré-CR, légère créativité
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            
            return response.content[0].text
            
        except RateLimitError:
            logger.warning("Rate limit atteint (429), tentative de retry automatique...")
            raise  # Laisser tenacity gérer le retry
        except Exception as e:
            logger.error(f"Erreur lors de l'appel à Claude: {str(e)}", exc_info=True)
            raise
    
    def _extract_json_from_response(self, response: str) -> Dict[str, Any]:
        """Extrait le JSON de la réponse de Claude"""
        try:
            # Recherche du JSON dans la réponse
            start_idx = response.find('{')
            end_idx = response.rfind('}') + 1
            
            if start_idx == -1 or end_idx == 0:
                raise ValueError("Aucun JSON trouvé dans la réponse")
            
            json_str = response[start_idx:end_idx]
            return json.loads(json_str)
            
        except Exception as e:
            logger.error(f"Erreur lors de l'extraction du JSON: {str(e)}")
            logger.debug(f"Réponse reçue: {response[:500]}")
            return {}

