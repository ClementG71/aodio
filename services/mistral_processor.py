"""
Service de traitement LLM avec Mistral AI
Mapping des locuteurs (Hybride Spacy + Mistral Small), génération pré-CR (Mistral Large)
"""
import json
import logging
import os
from typing import Dict, List, Any, Optional
from mistralai import Mistral
from tenacity import retry, stop_after_attempt, wait_exponential

from services.circuit_breaker import mistral_breaker
from services.speaker_mapper import SpeakerMapper, EnhancedSpeakerMapper

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
        self.enhanced_mapper = EnhancedSpeakerMapper()
        
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
        Utilise une stratégie améliorée : Analyse comportementale + LLM enrichi.
        
        Args:
            transcription_result: Résultat de la transcription avec segments
            liste_participants_path: Chemin vers le fichier liste des participants
            president_seance: Nom du président de séance
            
        Returns:
            dict: Mapping {SPEAKER_00: "Nom", ...}
        """
        try:
            logger.info("Démarrage du mapping des locuteurs (Mode Amélioré)")
            
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
            
            # S'assurer que le président est dans la liste
            if president_seance and president_seance not in participants:
                participants.append(president_seance)
            
            if not participants:
                logger.warning("Aucun participant fourni, mapping impossible")
                return {}
            
            # 2. Analyse comportementale avec EnhancedSpeakerMapper
            logger.info("Analyse des caractéristiques comportementales des speakers...")
            speaker_stats = self.enhanced_mapper.analyze_speaker_characteristics(
                segments, participants, president_seance
            )
            
            # 3. Identification du président en premier (ancrage)
            president_speaker = None
            if president_seance:
                president_speaker = self._identify_president_speaker(
                    speaker_stats, president_seance
                )
                if president_speaker:
                    logger.info(f"Président identifié: {president_speaker} -> {president_seance}")
            
            # 4. Appel LLM enrichi avec toutes les caractéristiques
            logger.info("Appel LLM enrichi pour identification complète...")
            llm_mapping = self._map_speakers_with_enhanced_llm(
                segments, speaker_stats, participants, president_seance, president_speaker
            )
            
            return llm_mapping
            
        except Exception as e:
            logger.error(f"Erreur mapping global: {e}", exc_info=True)
            return {}

    def _identify_president_speaker(self, 
                                   speaker_stats: Dict[str, Dict[str, Any]], 
                                   president_name: str) -> Optional[str]:
        """
        Identifie le speaker qui correspond au président en utilisant les caractéristiques.
        
        Args:
            speaker_stats: Statistiques par speaker
            president_name: Nom du président
            
        Returns:
            str: ID du speaker (SPEAKER_XX) ou None
        """
        if not speaker_stats:
            return None
        
        # Critères pour identifier le président:
        # 1. Parle en premier (début de réunion)
        # 2. Donne souvent la parole
        # 3. Parle relativement beaucoup
        
        best_candidate = None
        best_score = 0
        
        for speaker, stats in speaker_stats.items():
            score = 0
            
            # Critère 1: Position temporelle (début = +30 points)
            if stats.get('position_in_meeting') == 'début':
                score += 30
            elif stats.get('first_appearance', float('inf')) < 60:  # Parle dans la première minute
                score += 20
            
            # Critère 2: Donne la parole (chaque fois = +10 points)
            score += stats.get('gives_floor_count', 0) * 10
            
            # Critère 3: Volume de parole (normalisé)
            duration_pct = stats.get('duration_percentage', 0)
            if duration_pct > 15:  # Parle plus que la moyenne
                score += 15
            
            if score > best_score:
                best_score = score
                best_candidate = speaker
        
        # Seuil minimum pour valider
        if best_score >= 30:
            return best_candidate
        
        return None
    
    def _map_speakers_with_enhanced_llm(self, 
                                       segments: List[Dict], 
                                       speaker_stats: Dict[str, Dict[str, Any]],
                                       participants: List[str], 
                                       president: Optional[str],
                                       president_speaker: Optional[str]) -> Dict[str, str]:
        """
        Utilise Mistral Small avec un prompt enrichi pour identifier tous les speakers.
        
        Args:
            segments: Segments de transcription
            speaker_stats: Statistiques comportementales par speaker
            participants: Liste des participants
            president: Nom du président
            president_speaker: Speaker identifié comme président (si connu)
            
        Returns:
            dict: Mapping {SPEAKER_XX: "Nom", ...}
        """
        # Construire le contexte enrichi
        context = self.enhanced_mapper.build_llm_context(speaker_stats, participants, president)
        
        # Construire le prompt structuré
        prompt = f"""Tu es un expert en analyse de réunions universitaires.

{context}

TÂCHE:
Identifie qui est chaque locuteur (SPEAKER_XX) parmi les participants connus.

INDICES IMPORTANTS:
- Le président de séance parle généralement en premier et donne souvent la parole
- Les participants qui donnent la parole sont souvent des modérateurs ou le président
- La position temporelle (début/milieu/fin) peut aider à identifier le président
- Les noms mentionnés dans les extraits peuvent indiquer qui parle

{"ATTENTION: " + president_speaker + " a été identifié comme le président (" + president + "). Utilise cette information pour identifier les autres." if president_speaker and president else ""}

INSTRUCTIONS:
1. Analyse les caractéristiques de chaque speaker
2. Compare avec la liste des participants
3. Explique ton raisonnement pour chaque identification
4. Fournis le mapping final avec un niveau de confiance

RÉPONSE (JSON strict, aucun texte avant/après):
{{
  "reasoning": {{
    "SPEAKER_00": "Parle en premier, donne la parole 3 fois, position début -> probablement le président",
    "SPEAKER_01": "Mentionne 'M. Dupont' dans ses extraits, pose des questions -> probablement participant actif"
  }},
  "mapping": {{
    "SPEAKER_00": "Nom Identifié",
    "SPEAKER_01": "Nom Identifié"
  }},
  "confidence": {{
    "SPEAKER_00": 0.9,
    "SPEAKER_01": 0.7
  }}
}}

Si tu ne peux pas identifier un speaker avec confiance, mets "Inconnu" dans le mapping et 0.0 dans confidence.
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
            result = json.loads(content)
            
            # Extraire le mapping
            mapping = result.get('mapping', {})
            confidence = result.get('confidence', {})
            
            # Logger le raisonnement pour debug
            if 'reasoning' in result:
                logger.info("Raisonnement LLM:")
                for speaker, reasoning in result['reasoning'].items():
                    conf = confidence.get(speaker, 0)
                    logger.info(f"  {speaker}: {reasoning} (confiance: {conf:.2f})")
            
            # Filtrer les mappings avec faible confiance (< 0.5)
            filtered_mapping = {}
            for speaker, name in mapping.items():
                if name != "Inconnu" and confidence.get(speaker, 0) >= 0.5:
                    filtered_mapping[speaker] = name
                elif name != "Inconnu":
                    logger.warning(f"Mapping {speaker} -> {name} rejeté (confiance trop faible: {confidence.get(speaker, 0):.2f})")
            
            # Forcer le mapping du président si identifié
            if president_speaker and president:
                filtered_mapping[president_speaker] = president
                logger.info(f"Mapping président forcé: {president_speaker} -> {president}")
            
            return filtered_mapping
            
        except json.JSONDecodeError as e:
            logger.error(f"Erreur parsing JSON LLM: {e}")
            if 'content' in locals():
                logger.error(f"Réponse reçue (premiers 500 caractères): {content[:500]}")
            return {}
        except Exception as e:
            logger.error(f"Erreur LLM enrichi: {e}", exc_info=True)
            return {}
    
    def _map_speakers_with_llm(self, segments: List[Dict], target_speakers: List[str], 
                              participants: List[str], president: Optional[str]) -> Dict[str, str]:
        """
        Méthode legacy conservée pour compatibilité.
        Utilise maintenant la méthode enrichie.
        """
        logger.warning("Utilisation de _map_speakers_with_llm (legacy), migration vers _map_speakers_with_enhanced_llm recommandée")
        
        # Extraire les stats pour les speakers cibles
        speaker_stats = self.enhanced_mapper.analyze_speaker_characteristics(
            [s for s in segments if s.get('speaker') in target_speakers],
            participants,
            president
        )
        
        return self._map_speakers_with_enhanced_llm(
            segments, speaker_stats, participants, president, None
        )

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
