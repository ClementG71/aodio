"""
Service de mapping entre segments de transcription et segments de diarisation
Extrait de mistral_voxtral.py pour une meilleure modularité
"""
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class TranscriptionMapper:
    """Mappe les segments de transcription avec les segments de diarisation"""
    
    def __init__(self):
        """Initialise le mapper"""
        pass
    
    def map_to_diarization(self, mistral_segments: List[Dict[str, Any]],
                           diarization_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Mappe les segments de transcription Mistral avec les segments de diarisation
        
        Args:
            mistral_segments: Segments de transcription avec start, end, text
            diarization_segments: Segments de diarisation avec start, end, speaker
            
        Returns:
            list: Segments mappés avec speaker et text
        """
        transcriptions = []
        
        # Convertir tous les segments Mistral en dicts pour faciliter le traitement
        mistral_dicts = self._normalize_segments(mistral_segments)
        
        logger.info(f"Mapping: {len(mistral_dicts)} segments Mistral avec {len(diarization_segments)} segments de diarisation")
        
        # Compter les segments Mistral avec texte
        mistral_with_text = sum(1 for m in mistral_dicts if m.get('text', '').strip())
        logger.info(f"Segments Mistral avec texte: {mistral_with_text}/{len(mistral_dicts)}")
        
        # Log les premiers segments pour déboguer
        self._log_segments_info(mistral_dicts, diarization_segments)
        
        # Trier les segments Mistral par timestamp pour faciliter la recherche
        mistral_dicts.sort(key=lambda x: x.get('start', 0))
        
        matches_found = 0
        for diar_seg in diarization_segments:
            diar_start = diar_seg['start']
            diar_end = diar_seg['end']
            
            # Trouver tous les segments Mistral qui chevauchent avec ce segment de diarisation
            matching_texts = []
            for mistral_seg in mistral_dicts:
                mistral_start = mistral_seg.get('start', 0)
                mistral_end = mistral_seg.get('end', float('inf'))
                mistral_text = mistral_seg.get('text', '').strip()
                
                # Vérifier le chevauchement
                if mistral_start < diar_end and mistral_end > diar_start and mistral_text:
                    overlap_start = max(mistral_start, diar_start)
                    overlap_end = min(mistral_end, diar_end)
                    overlap_duration = overlap_end - overlap_start
                    diar_duration = diar_end - diar_start
                    
                    # Si le chevauchement est significatif
                    min_overlap_ratio = 0.1  # 10% minimum
                    min_overlap_duration = 1.0  # ou au moins 1 seconde
                    
                    if overlap_duration > 0 and (
                        (overlap_duration / diar_duration) >= min_overlap_ratio or 
                        overlap_duration >= min_overlap_duration
                    ):
                        matching_texts.append(mistral_text)
                        
                        # Log détaillé pour les premiers matches
                        if matches_found == 0 and len(matching_texts) == 1:
                            logger.info(f"Premier match trouvé: diarisation [{diar_start:.1f}s-{diar_end:.1f}s] chevauche avec Mistral [{mistral_start:.1f}s-{mistral_end:.1f}s] (overlap: {overlap_duration:.1f}s)")
            
            # Concaténer tous les textes correspondants
            mistral_text = " ".join(matching_texts).strip()
            
            if mistral_text:
                matches_found += 1
                if matches_found <= 3:
                    logger.info(f"Match {matches_found}: segment diarisation [{diar_start:.1f}s - {diar_end:.1f}s] speaker={diar_seg.get('speaker', 'UNKNOWN')} -> texte: '{mistral_text[:50]}...'")
            else:
                if len(transcriptions) < 5:
                    logger.debug(f"Aucun texte trouvé pour segment diarisation [{diar_start:.1f}s - {diar_end:.1f}s] speaker={diar_seg.get('speaker', 'UNKNOWN')}")
            
            transcriptions.append({
                "start": diar_start,
                "end": diar_end,
                "speaker": diar_seg.get('speaker', 'UNKNOWN'),
                "text": mistral_text
            })
        
        # Statistiques de mapping
        segments_with_text = sum(1 for t in transcriptions if t.get('text', '').strip())
        logger.info(f"Mapping terminé: {segments_with_text}/{len(transcriptions)} segments avec texte ({matches_found} matches trouvés)")
        
        if segments_with_text == 0 and mistral_with_text > 0:
            logger.error(f"PROBLÈME: {mistral_with_text} segments Mistral ont du texte mais aucun mapping n'a été trouvé!")
        
        return transcriptions
    
    def map_with_unique_attribution(self, mistral_segments: List[Dict[str, Any]],
                                    diarization_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Mapping temporel amélioré : attribution unique avec meilleur chevauchement
        Chaque segment Mistral n'est attribué qu'à un seul segment de diarisation
        
        Args:
            mistral_segments: Segments de transcription
            diarization_segments: Segments de diarisation
            
        Returns:
            list: Segments mappés
        """
        # Convertir et trier
        mistral_dicts = self._normalize_segments(mistral_segments)
        mistral_dicts = sorted(mistral_dicts, key=lambda x: x.get('start', 0))
        diarization_segments = sorted(diarization_segments, key=lambda x: x.get('start', 0))
        
        # Marquer les segments Mistral comme non utilisés
        mistral_used = [False] * len(mistral_dicts)
        transcriptions = []
        
        for diar_seg in diarization_segments:
            diar_start = diar_seg['start']
            diar_end = diar_seg['end']
            diar_duration = diar_end - diar_start
            
            # Trouver le segment Mistral avec le meilleur chevauchement (non utilisé)
            best_match = None
            best_overlap_ratio = 0
            best_overlap_duration = 0
            
            for idx, mistral_seg in enumerate(mistral_dicts):
                if mistral_used[idx]:
                    continue
                    
                mistral_start = mistral_seg.get('start', 0)
                mistral_end = mistral_seg.get('end', float('inf'))
                mistral_text = mistral_seg.get('text', '').strip()
                
                if not mistral_text:
                    continue
                
                # Calculer le chevauchement
                overlap_start = max(mistral_start, diar_start)
                overlap_end = min(mistral_end, diar_end)
                overlap_duration = max(0, overlap_end - overlap_start)
                
                if overlap_duration <= 0:
                    continue
                
                overlap_ratio = overlap_duration / diar_duration if diar_duration > 0 else 0
                
                # Seuil minimum
                min_overlap_ratio = 0.3
                min_overlap_duration = 1.0
                
                if (overlap_ratio >= min_overlap_ratio or overlap_duration >= min_overlap_duration):
                    # Score combiné
                    normalized_duration = min(overlap_duration / 10.0, 1.0)
                    score = overlap_ratio * 0.7 + normalized_duration * 0.3
                    
                    current_score = best_overlap_ratio * 0.7 + (best_overlap_duration / 10.0) * 0.3
                    
                    if score > current_score:
                        best_overlap_ratio = overlap_ratio
                        best_overlap_duration = overlap_duration
                        best_match = (idx, mistral_seg)
            
            # Attribuer le texte si match trouvé
            if best_match:
                idx, mistral_seg = best_match
                mistral_used[idx] = True
                text = mistral_seg.get('text', '').strip()
                
                if len(transcriptions) < 3:
                    logger.info(f"Match trouvé: diarisation [{diar_start:.1f}s-{diar_end:.1f}s] "
                              f"speaker={diar_seg.get('speaker', 'UNKNOWN')} "
                              f"-> Mistral [{mistral_seg.get('start', 0):.1f}s-{mistral_seg.get('end', 0):.1f}s] "
                              f"(overlap: {best_overlap_ratio*100:.1f}%)")
            else:
                text = ""
                if len(transcriptions) < 5:
                    logger.debug(f"Aucun match pour segment diarisation [{diar_start:.1f}s-{diar_end:.1f}s]")
            
            transcriptions.append({
                "start": diar_start,
                "end": diar_end,
                "speaker": diar_seg.get('speaker', 'UNKNOWN'),
                "text": text
            })
        
        # Statistiques
        segments_with_text = sum(1 for t in transcriptions if t.get('text', '').strip())
        logger.info(f"Mapping temporel terminé: {segments_with_text}/{len(transcriptions)} segments avec texte")
        
        return transcriptions
    
    def validate_mapping(self, transcriptions: List[Dict[str, Any]],
                        diarization_segments: List[Dict[str, Any]]) -> List[str]:
        """
        Valide la cohérence du mapping et retourne les problèmes détectés
        
        Args:
            transcriptions: Segments de transcription mappés
            diarization_segments: Segments de diarisation originaux
            
        Returns:
            list: Liste des problèmes détectés
        """
        issues = []
        
        # Vérifier le nombre de segments
        if len(transcriptions) != len(diarization_segments):
            issues.append(f"Nombre de segments différent: {len(transcriptions)} vs {len(diarization_segments)}")
        
        # Vérifier l'ordre chronologique
        for i in range(len(transcriptions) - 1):
            if transcriptions[i].get('start', 0) > transcriptions[i+1].get('start', 0):
                issues.append(f"Ordre chronologique cassé à l'index {i}")
        
        # Vérifier que les speakers correspondent
        for i, (trans, diar) in enumerate(zip(transcriptions, diarization_segments)):
            if trans.get('speaker') != diar.get('speaker'):
                issues.append(f"Speaker mismatch à l'index {i}: {trans.get('speaker')} vs {diar.get('speaker')}")
        
        # Vérifier les segments sans texte
        segments_without_text = sum(1 for t in transcriptions if not t.get('text', '').strip())
        if segments_without_text > len(transcriptions) * 0.2:  # Plus de 20% sans texte
            issues.append(f"Trop de segments sans texte: {segments_without_text}/{len(transcriptions)}")
        
        # Logger les problèmes
        if issues:
            logger.warning(f"Problèmes détectés dans le mapping: {len(issues)}")
            for issue in issues[:5]:
                logger.warning(f"  - {issue}")
        else:
            logger.info("Validation du mapping: OK")
        
        return issues
    
    def merge_consecutive_segments(self, diarization_segments: List[Dict[str, Any]], 
                                   max_gap_seconds: float = 5.0) -> List[Dict[str, Any]]:
        """
        Regroupe les segments consécutifs de diarisation du même speaker
        
        Args:
            diarization_segments: Liste des segments de diarisation
            max_gap_seconds: Gap maximum en secondes entre deux segments pour les regrouper
            
        Returns:
            list: Segments regroupés
        """
        if not diarization_segments:
            return []
        
        sorted_segments = sorted(diarization_segments, key=lambda x: x.get('start', 0))
        
        merged_segments = []
        current_group = None
        
        avg_duration_before = sum(seg.get('end', 0) - seg.get('start', 0) for seg in sorted_segments) / len(sorted_segments) if sorted_segments else 0
        
        for seg in sorted_segments:
            seg_start = seg.get('start', 0)
            seg_end = seg.get('end', 0)
            seg_speaker = seg.get('speaker', 'UNKNOWN')
            
            if current_group is None:
                current_group = {
                    'start': seg_start,
                    'end': seg_end,
                    'speaker': seg_speaker
                }
            else:
                current_speaker = current_group.get('speaker', 'UNKNOWN')
                current_end = current_group.get('end', 0)
                gap = seg_start - current_end
                
                # Vérifier qu'aucun autre speaker ne parle entre les deux segments
                has_other_speaker_between = False
                if gap > 0:
                    for other_seg in sorted_segments:
                        other_start = other_seg.get('start', 0)
                        other_end = other_seg.get('end', 0)
                        other_speaker = other_seg.get('speaker', 'UNKNOWN')
                        
                        if (other_speaker != current_speaker and 
                            other_start < seg_start and 
                            other_end > current_end):
                            has_other_speaker_between = True
                            break
                
                if (current_speaker == seg_speaker and 
                    gap <= max_gap_seconds and 
                    not has_other_speaker_between):
                    current_group['end'] = seg_end
                else:
                    merged_segments.append(current_group)
                    current_group = {
                        'start': seg_start,
                        'end': seg_end,
                        'speaker': seg_speaker
                    }
        
        if current_group is not None:
            merged_segments.append(current_group)
        
        avg_duration_after = sum(seg.get('end', 0) - seg.get('start', 0) for seg in merged_segments) / len(merged_segments) if merged_segments else 0
        
        logger.info(f"Regroupement segments: {len(sorted_segments)} -> {len(merged_segments)} segments")
        logger.info(f"Durée moyenne avant: {avg_duration_before:.1f}s, après: {avg_duration_after:.1f}s")
        
        return merged_segments
    
    def _normalize_segments(self, segments: List[Any]) -> List[Dict[str, Any]]:
        """
        Normalise les segments en dicts
        
        Args:
            segments: Segments (dicts ou objets)
            
        Returns:
            list: Liste de dicts normalisés
        """
        normalized = []
        for seg in segments:
            if isinstance(seg, dict):
                normalized.append(seg)
            else:
                normalized.append({
                    'start': getattr(seg, 'start', 0),
                    'end': getattr(seg, 'end', 0),
                    'text': getattr(seg, 'text', '')
                })
        return normalized
    
    def _log_segments_info(self, mistral_dicts: List[Dict[str, Any]],
                          diarization_segments: List[Dict[str, Any]]):
        """Log les premiers segments pour déboguer"""
        if mistral_dicts:
            logger.info(f"Premier segment Mistral: start={mistral_dicts[0].get('start', 0):.1f}s, end={mistral_dicts[0].get('end', 0):.1f}s, text_length={len(mistral_dicts[0].get('text', ''))}")
            if len(mistral_dicts) > 1:
                logger.info(f"Dernier segment Mistral: start={mistral_dicts[-1].get('start', 0):.1f}s, end={mistral_dicts[-1].get('end', 0):.1f}s, text_length={len(mistral_dicts[-1].get('text', ''))}")
        
        if diarization_segments:
            logger.info(f"Premier segment diarisation: start={diarization_segments[0].get('start', 0):.1f}s, end={diarization_segments[0].get('end', 0):.1f}s, speaker={diarization_segments[0].get('speaker', 'UNKNOWN')}")
            if len(diarization_segments) > 1:
                logger.info(f"Dernier segment diarisation: start={diarization_segments[-1].get('start', 0):.1f}s, end={diarization_segments[-1].get('end', 0):.1f}s, speaker={diarization_segments[-1].get('speaker', 'UNKNOWN')}")
