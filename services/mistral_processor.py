"""
Service de traitement LLM avec Mistral AI (remplace Anthropic/Claude)
Mapping des locuteurs (Hybride Spacy + Mistral Small), génération pré-CR (Mistral Large)
"""
import json
import logging
import os
from typing import Dict, List, Any, Optional
from mistralai import Mistral
from tenacity import retry, stop_after_attempt, wait_exponential

from services.circuit_breaker import mistral_breaker
from services.speaker_mapper import SpeakerMapper

logger = logging.getLogger(__name__)

class MistralProcessor:
    """Gère les traitements LLM avec Mistral AI"""
    
    def __init__(self, api_key: str):
        """
        Initialise le processeur Mistral
        
        Args:
            api_key: Clé API Mistral AI
        """
        self.client = Mistral(api_key=api_key)
        self.speaker_mapper = SpeakerMapper()
        
        # Configuration des modèles
        # Mistral Large: Pour les tâches complexes (Résumé, Décisions)
        self.model_large = "mistral-large-latest"
        # Mistral Small: Pour les tâches simples et rapides (Mapping fallback)
        self.model_small = "mistral-small-latest"
        
    def map_speakers(self, transcription_result: Dict[str, Any], 
                    liste_participants_path: Optional[str] = None,
                    president_seance: Optional[str] = None) -> Dict[str, str]:
        """
        Mappe les labels SPEAKER_XX vers les noms réels des locuteurs.
        Utilise une stratégie hybride : Spacy d'abord, puis Mistral Small pour les ambiguïtés.
        
        Args:
            transcription_result: Résultat de la transcription avec segments
            liste_participants_path: Chemin vers le fichier liste des participants
            president_seance: Nom du président de séance
            
        Returns:
            dict: Mapping {SPEAKER_00: "Nom", ...}
        """
        try:
            logger.info("Démarrage du mapping des locuteurs (Mode Hybride)")
            
            segments = transcription_result.get('segments', [])
            if not segments:
                logger.warning("Aucun segment à mapper.")
                return {}
            
            # 1. Charger la liste des participants
            participants = []
            if liste_participants_path:
                try:
                    with open(liste_participants_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        # Supposons un nom par ligne ou séparé par virgule
                        participants = [p.strip() for p in content.replace(',', '\n').split('\n') if p.strip()]
                except Exception as e:
                    logger.warning(f"Erreur lecture participants: {e}")
            
            if president_seance:
                participants.append(president_seance)
                
            # 2. Analyse Spacy (Rapide & Gratuite)
            spacy_mapping, ambiguous_speakers = self.speaker_mapper.identify_speakers(segments, participants)
            logger.info(f"Spacy a identifié {len(spacy_mapping)} speakers. Ambigus: {len(ambiguous_speakers)}")
            
            final_mapping = spacy_mapping.copy()
            
            # 3. Analyse Fallback LLM (Mistral Small) pour les ambigus
            if ambiguous_speakers:
                logger.info(f"Lancement du fallback Mistral Small pour: {ambiguous_speakers}")
                llm_mapping = self._map_speakers_with_llm(
                    segments, ambiguous_speakers, participants, president_seance
                )
                final_mapping.update(llm_mapping)
                
            return final_mapping
            
        except Exception as e:
            logger.error(f"Erreur mapping global: {e}", exc_info=True)
            return {}

    def _map_speakers_with_llm(self, segments: List[Dict], target_speakers: List[str], 
                              participants: List[str], president: Optional[str]) -> Dict[str, str]:
        """Utilise Mistral Small pour identifier les speakers ambigus"""
        mapping = {}
        
        # Extraire seulement les segments pertinents pour ces speakers
        # (Pour économiser des tokens)
        relevant_text = []
        for seg in segments:
            speaker = seg.get('speaker')
            text = seg.get('text', '')
            
            # On prend les segments des speakers cibles ET ceux qui les entourent (contexte)
            # Simplification: on prend tout pour l'instant si le transcript n'est pas énorme
            # Pour une optimisation future: fenêtre glissante
            if speaker in target_speakers or len(relevant_text) < 50: # Limite arbitraire pour l'exemple
                relevant_text.append(f"{speaker}: {text}")
        
        context_text = "\n".join(relevant_text[:200]) # Limite contexte
        
        prompt = f"""Tu es un expert en analyse de conversation.
        
        CONTEXTE:
        Voici une liste de participants potentiels: {', '.join(participants)}
        Président de séance: {president or 'Non spécifié'}
        
        TRANSCRIPTION PARTIELLE:
        {context_text}
        
        TÂCHE:
        Identifie qui sont les locuteurs suivants: {', '.join(target_speakers)}.
        Utilise les indices contextuels ("La parole est à M. X", "Merci Y", auto-présentation).
        
        RÉPONSE (JSON uniquement):
        {{
            "SPEAKER_XX": "Nom Identifié",
            "SPEAKER_YY": "Nom Identifié"
        }}
        Si tu ne sais pas, mets "Inconnu".
        """
        
        try:
            with mistral_breaker:
                response = self.client.chat.complete(
                    model=self.model_small,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0.0
                )
                
            content = response.choices[0].message.content
            mapping = json.loads(content)
            
            # Nettoyage
            return {k: v for k, v in mapping.items() if v != "Inconnu" and k in target_speakers}
            
        except Exception as e:
            logger.error(f"Erreur fallback LLM: {e}")
            return {}

    def generate_pre_compte_rendu(self, transcription_text: str, speaker_mapping: Dict[str, str]) -> str:
        """
        Génère un pré-compte rendu avec Mistral Large
        """
        # Remplacer les labels par les noms
        processed_text = transcription_text
        for code, name in speaker_mapping.items():
            processed_text = processed_text.replace(code, name)
            
        prompt = f"""Tu es un secrétaire de séance expert pour une université.
        
        TÂCHE:
        Rédige un pré-compte rendu formel, structuré et synthétique de cette réunion du CFVE.
        
        CONSIGNES:
        1. Utilise un ton neutre et administratif.
        2. Structure par points à l'ordre du jour.
        3. Synthétise les débats en attribuant les idées aux bonnes personnes.
        4. Mets en évidence les votes et décisions.
        
        TRANSCRIPTION:
        {processed_text[:100000]} 
        (Texte tronqué si trop long, concentre-toi sur le début et les points clés)
        """
        
        try:
            with mistral_breaker:
                response = self.client.chat.complete(
                    model=self.model_large,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2
                )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Erreur génération CR: {e}")
            return "Erreur lors de la génération du compte rendu."

    def extract_decisions(self, transcription_text: str, speaker_mapping: Dict[str, str]) -> List[str]:
        """
        Extrait la liste des décisions et votes avec Mistral Large
        """
        processed_text = transcription_text
        for code, name in speaker_mapping.items():
            processed_text = processed_text.replace(code, name)
            
        prompt = """Liste uniquement les DÉCISIONS actées et les RÉSULTATS DES VOTES contenus dans ce texte.
        Format liste à puces. Sois factuel et précis."""
        
        try:
            with mistral_breaker:
                response = self.client.chat.complete(
                    model=self.model_large,
                    messages=[
                        {"role": "system", "content": "Tu es un extracteur de données factuelles."},
                        {"role": "user", "content": f"{prompt}\n\nTEXTE:\n{processed_text[:50000]}"}
                    ],
                    temperature=0.0
                )
            return response.choices[0].message.content.split('\n')
        except Exception as e:
            logger.error(f"Erreur extraction décisions: {e}")
            return []
