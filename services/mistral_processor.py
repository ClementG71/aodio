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
from services.temporal_speaker_mapper import TemporalSpeakerMapper
from services.transition_analyzer import TransitionAnalyzer

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
        self.temporal_mapper = TemporalSpeakerMapper()
        self.transition_analyzer = TransitionAnalyzer()
        
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
            
            # 2. Analyse comportementale globale (pour identifier le président)
            logger.info("Analyse des caractéristiques comportementales (globale)...")
            global_speaker_stats = self.enhanced_mapper.analyze_speaker_characteristics(
                segments, participants, president_seance
            )
            
            # 3. Identification du président en premier (ancrage)
            president_speaker = None
            if president_seance:
                president_speaker = self._identify_president_speaker(
                    global_speaker_stats, president_seance
                )
                if president_speaker:
                    logger.info(f"Président identifié: {president_speaker} -> {president_seance}")
            
            # 4. Découpage temporel en blocs + multi-pass LLM par bloc
            logger.info("Découpage temporel en blocs pour le mapping progressif...")
            blocks = self.temporal_mapper.split_into_blocks(segments)

            all_block_mappings: List[Dict[str, str]] = []
            all_confidences: Dict[str, float] = {}

            for block_index, block_segments in enumerate(blocks):
                logger.info(f"Traitement du bloc {block_index + 1}/{len(blocks)} "
                            f"({len(block_segments)} segments)")
                block_stats = self.enhanced_mapper.analyze_speaker_characteristics(
                    block_segments, participants, president_seance
                )
                block_mapping, block_conf = self._map_speakers_multipass(
                    block_segments, block_stats, participants, president_seance, president_speaker
                )
                all_block_mappings.append(block_mapping)

                # Agréger les confiances (on garde la meilleure pour chaque speaker)
                for spk, conf in block_conf.items():
                    if spk not in all_confidences or conf > all_confidences[spk]:
                        all_confidences[spk] = conf

            # Consolidation des mappings entre blocs (stabilité temporelle)
            llm_mapping = self.temporal_mapper.consolidate_mappings(all_block_mappings)

            # Exposer les confiances via le résultat de transcription (side-channel pour l'orchestrateur)
            transcription_result["_speaker_confidence"] = all_confidences  # type: ignore[index]

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
    
    def _map_speakers_multipass(
        self,
        segments: List[Dict],
        speaker_stats: Dict[str, Dict[str, Any]],
        participants: List[str],
        president: Optional[str],
        president_speaker: Optional[str],
    ) -> (Dict[str, str], Dict[str, float]):
        """
        Identification en plusieurs passes avec Mistral Small.

        Pass 1 : identifier uniquement les locuteurs « évidents » (ancrages) avec forte confiance.
        Pass 2 : compléter le mapping en utilisant les ancrages comme contexte.
        Pass 3 : vérification de cohérence basique côté Python (sans nouvel appel LLM).

        Retourne:
            mapping global {SPEAKER_XX: Nom}, confidence {SPEAKER_XX: score 0-1}
        """
        # Construire le contexte enrichi commun
        context = self.enhanced_mapper.build_llm_context(speaker_stats, participants, president)

        # ---------- Pass 1 : ancrages ----------
        anchors_mapping: Dict[str, str] = {}
        anchors_confidence: Dict[str, float] = {}

        prompt_pass1 = f"""Tu es un expert en analyse de réunions universitaires.

{context}

TÂCHE:
Identifie UNIQUEMENT les locuteurs (SPEAKER_XX) dont tu es presque certain de l'identité
parmi la liste des participants. Ne propose rien pour les cas incertains.

INDICES IMPORTANTS:
- Le président parle en premier et donne souvent la parole.
- Les locuteurs qui donnent souvent la parole sont souvent le président ou les modérateurs.
- La durée de parole, la position temporelle et les noms mentionnés dans les extraits sont des indices clés.

{"ATTENTION: " + president_speaker + " a été identifié comme le président (" + president + "). Utilise cette information pour les ancrages." if president_speaker and president else ""}

RÉPONSE (JSON strict, aucun texte avant/après):
{{
  "mapping": {{
    "SPEAKER_00": "Nom du participant",
    "...": "..."
  }},
  "confidence": {{
    "SPEAKER_00": 0.95
  }}
}}

Inclue uniquement les speakers avec une confiance >= 0.9.
"""
        try:
            with mistral_breaker:
                response = self.client.chat.complete(
                    model=self.model_small,
                    messages=[{"role": "user", "content": prompt_pass1}],
                    response_format={"type": "json_object"},
                    temperature=0.0,
                )
            content = response.choices[0].message.content
            result = json.loads(content)
            anchors_mapping = result.get("mapping", {}) or {}
            anchors_confidence = result.get("confidence", {}) or {}
        except Exception as e:
            logger.warning(f"Pass 1 (ancrages) échoué ou vide: {e}")
            anchors_mapping = {}
            anchors_confidence = {}

        # Forcer éventuellement le président si détecté par les stats
        if president_speaker and president:
            anchors_mapping[president_speaker] = president
            anchors_confidence[president_speaker] = max(anchors_confidence.get(president_speaker, 0.0), 0.95)
            logger.info(f"Ancrage président forcé: {president_speaker} -> {president}")

        # ---------- Pass 2 : mapping complet guidé par les ancrages ----------
        prompt_pass2 = f"""Tu es un expert en analyse de réunions universitaires.

{context}

ANCRAGES CONNUS (fiables):
{json.dumps(anchors_mapping, ensure_ascii=False, indent=2)}

TÂCHE:
En te basant sur les ancrages ci-dessus et les caractéristiques des locuteurs,
propose l'identité des AUTRES locuteurs (SPEAKER_XX) parmi les participants.

INSTRUCTIONS:
- Garde les mêmes identités pour les speakers déjà présents dans les ancrages.
- Pour les autres speakers, propose un nom uniquement si tu es raisonnablement confiant.
- Si tu ne sais pas, indique "Inconnu" avec une confiance 0.0.

RÉPONSE (JSON strict, aucun texte avant/après):
{{
  "mapping": {{
    "SPEAKER_00": "Nom",
    "SPEAKER_01": "Nom ou Inconnu"
  }},
  "confidence": {{
    "SPEAKER_00": 0.95,
    "SPEAKER_01": 0.7
  }}
}}
"""
        global_mapping: Dict[str, str] = {}
        global_confidence: Dict[str, float] = {}

        # Commencer par les ancrages
        global_mapping.update(anchors_mapping)
        global_confidence.update(anchors_confidence)

        try:
            with mistral_breaker:
                response = self.client.chat.complete(
                    model=self.model_small,
                    messages=[{"role": "user", "content": prompt_pass2}],
                    response_format={"type": "json_object"},
                    temperature=0.0,
                )
            content = response.choices[0].message.content
            result = json.loads(content)

            mapping = result.get("mapping", {}) or {}
            confidence = result.get("confidence", {}) or {}

            for speaker, name in mapping.items():
                conf = float(confidence.get(speaker, 0.0))
                if name != "Inconnu" and conf >= 0.5:
                    # Ne pas écraser un ancrage existant
                    if speaker not in global_mapping:
                        global_mapping[speaker] = name
                        global_confidence[speaker] = conf
                elif name != "Inconnu":
                    logger.warning(
                        f"Mapping {speaker} -> {name} rejeté en pass 2 (confiance trop faible: {conf:.2f})"
                    )
        except Exception as e:
            logger.error(f"Erreur LLM en pass 2: {e}", exc_info=True)

        # ---------- Hints de transition (Merci Jean, Jean vous avez la parole, etc.) ----------
        try:
            transitions = self.transition_analyzer.analyze_transitions(segments)
            if transitions:
                logger.info(f"{len(transitions)} transitions explicites détectées pour affiner le mapping.")
                hinted_mapping = self.transition_analyzer.apply_transition_hints(
                    global_mapping, transitions, segments, participants
                )
                # Les nouveaux mappings issus des transitions reçoivent une confiance par défaut moyenne (0.8)
                for spk, name in hinted_mapping.items():
                    if spk not in global_mapping:
                        global_mapping[spk] = name
                        global_confidence[spk] = max(global_confidence.get(spk, 0.0), 0.8)
        except Exception as e:
            logger.warning(f"Erreur lors de l'application des hints de transition: {e}")

        # ---------- Pass 3 : vérification de cohérence simple ----------
        # Ici, on applique une vérification basique côté Python :
        # - si un même nom est associé à plusieurs SPEAKER_XX avec des confiances très différentes,
        #   on garde le speaker avec la meilleure confiance.
        name_to_best: Dict[str, Tuple[str, float]] = {}
        for speaker, name in global_mapping.items():
            conf = global_confidence.get(speaker, 0.0)
            prev = name_to_best.get(name)
            if not prev or conf > prev[1]:
                name_to_best[name] = (speaker, conf)

        # Si un nom est associé à plusieurs speakers, on ne garde que le meilleur
        speakers_to_remove: List[str] = []
        for name, (best_speaker, _) in name_to_best.items():
            for speaker, mapped_name in global_mapping.items():
                if mapped_name == name and speaker != best_speaker:
                    speakers_to_remove.append(speaker)

        for speaker in speakers_to_remove:
            logger.warning(
                f"Conflit de cohérence: le speaker {speaker} partage le même nom "
                f"que un autre speaker avec meilleure confiance, suppression de ce mapping."
            )
            global_mapping.pop(speaker, None)
            global_confidence.pop(speaker, None)

        return global_mapping, global_confidence
    
    def _map_speakers_with_llm(self, segments: List[Dict], target_speakers: List[str], 
                              participants: List[str], president: Optional[str]) -> Dict[str, str]:
        """
        Méthode legacy conservée pour compatibilité.
        Utilise maintenant la méthode enrichie.
        """
        logger.warning("Utilisation de _map_speakers_with_llm (legacy), migration vers _map_speakers_multipass recommandée")
        
        # Extraire les stats pour les speakers cibles
        speaker_stats = self.enhanced_mapper.analyze_speaker_characteristics(
            [s for s in segments if s.get('speaker') in target_speakers],
            participants,
            president
        )
        
        mapping, _ = self._map_speakers_multipass(
            segments, speaker_stats, participants, president, None
        )
        return mapping

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
