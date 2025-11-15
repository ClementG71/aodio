"""
Service de traitement LLM avec Claude Sonnet 4.5
Mapping des locuteurs, génération pré-CR, extraction des décisions
"""
import json
import logging
from typing import Dict, List, Any, Optional
from anthropic import Anthropic

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
            
            # Lecture de la liste des participants si fournie
            participants_list = ""
            if liste_participants_path:
                try:
                    with open(liste_participants_path, 'r', encoding='utf-8') as f:
                        participants_list = f.read()
                except Exception as e:
                    logger.warning(f"Impossible de lire la liste des participants: {e}")
            
            # Préparation de la transcription pour l'analyse
            segments_text = self._format_segments_for_mapping(transcription_result)
            
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
            
            # Formatage de la transcription avec mapping des locuteurs
            formatted_transcription = self._format_transcription_with_speakers(
                transcription_result, speaker_mapping
            )
            
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
                    with open(releves_votes_path, 'r', encoding='utf-8') as f:
                        releves_votes = f.read()
                except Exception as e:
                    logger.warning(f"Impossible de lire les relevés de votes: {e}")
            
            formatted_transcription = self._format_segments_for_mapping(transcription_result)
            
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

TRANSCRIPTION (pour vérification) :
{formatted_transcription[:5000]}  # Limité pour éviter la surcharge
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
        
        for seg in segments:
            speaker = seg.get('speaker', 'UNKNOWN')
            text = seg.get('text', '')
            start = seg.get('start', 0)
            end = seg.get('end', 0)
            
            time_str = f"[{self._format_time(start)} - {self._format_time(end)}]"
            formatted.append(f"{time_str} {speaker}: {text}")
        
        return "\n".join(formatted)
    
    def _format_transcription_with_speakers(self, transcription_result: Dict[str, Any],
                                          speaker_mapping: Dict[str, str]) -> str:
        """Formate la transcription avec les noms réels des locuteurs"""
        segments = transcription_result.get('segments', [])
        formatted = []
        
        for seg in segments:
            speaker_label = seg.get('speaker', 'UNKNOWN')
            speaker_name = speaker_mapping.get(speaker_label, speaker_label)
            text = seg.get('text', '')
            start = seg.get('start', 0)
            
            time_str = self._format_time(start)
            formatted.append(f"[{time_str}] {speaker_name}: {text}")
        
        return "\n".join(formatted)
    
    def _format_time(self, seconds: float) -> str:
        """Formate les secondes en HH:MM:SS"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    def _call_claude_safe(self, prompt: str) -> str:
        """
        Appelle Claude en gérant la limite de tokens
        
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

