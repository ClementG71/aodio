"""
Service d'alignement et distribution du texte de transcription
Extrait de mistral_voxtral.py pour une meilleure modularité
"""
import re
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class TranscriptionAligner:
    """Aligne et distribue le texte de transcription avec les segments de diarisation"""
    
    def __init__(self):
        """Initialise l'aligner"""
        pass
    
    def calculate_optimal_offset(self, transcriptions: List[Dict[str, Any]], 
                                 diarization_segments: List[Dict[str, Any]]) -> float:
        """
        Calcule l'offset optimal pour aligner les transcriptions avec la diarisation
        Teste une plage de décalages et retourne celui qui maximise le chevauchement
        
        Args:
            transcriptions: Segments de transcription
            diarization_segments: Segments de diarisation
            
        Returns:
            float: Offset optimal en secondes
        """
        if not transcriptions or not diarization_segments:
            return 0.0
            
        # Plage de recherche : -3s à +3s par pas de 0.1s
        offsets = [round(x * 0.1, 1) for x in range(-30, 31)]
        best_offset = 0.0
        max_overlap = 0.0
        
        # Pré-calculer les intervalles pour optimiser
        diar_intervals = [(d['start'], d['end']) for d in diarization_segments]
        trans_intervals = [(t['start'], t['end']) for t in transcriptions]
        
        for offset in offsets:
            current_overlap = 0.0
            
            for t_start, t_end in trans_intervals:
                adj_start = t_start + offset
                adj_end = t_end + offset
                
                for d_start, d_end in diar_intervals:
                    if adj_end <= d_start: continue
                    if adj_start >= d_end: continue
                    
                    ov_start = max(adj_start, d_start)
                    ov_end = min(adj_end, d_end)
                    current_overlap += max(0, ov_end - ov_start)
            
            if current_overlap > max_overlap:
                max_overlap = current_overlap
                best_offset = offset
        
        logger.info(f"Offset optimal détecté : {best_offset:+.1f}s (score: {max_overlap:.1f}s)")
        return best_offset
    
    def clean_transcription_segments(self, transcriptions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Nettoie les segments de transcription (fusionne les micro-segments, supprime les vides aberrants)
        
        Args:
            transcriptions: Segments de transcription
            
        Returns:
            list: Segments nettoyés
        """
        if not transcriptions:
            return []
            
        cleaned = []
        current = None
        
        sorted_trans = sorted(transcriptions, key=lambda x: x.get('start', 0))
        
        for seg in sorted_trans:
            if seg.get('start') is None or seg.get('end') is None:
                continue
                
            duration = seg['end'] - seg['start']
            text = seg.get('text', '').strip()
            
            # Si le segment est très court et a peu de texte, essayer de le fusionner
            if duration < 0.1 and len(text) < 5:
                if current:
                    current['end'] = max(current['end'], seg['end'])
                    if text:
                        current['text'] = (current['text'] + " " + text).strip()
                continue
            
            if current:
                cleaned.append(current)
            
            current = seg.copy()
            current['text'] = text
            
        if current:
            cleaned.append(current)
            
        return cleaned
    
    def align_strict_improved(self, transcriptions: List[Dict[str, Any]],
                             diarization_segments: List[Dict[str, Any]],
                             full_text: str = "") -> List[Dict[str, Any]]:
        """
        Alignement Text-First : Fusionne la transcription brute avec la diarisation
        en distribuant les mots selon les chevauchements temporels.
        
        Args:
            transcriptions: Segments de transcription bruts (avec timestamps)
            diarization_segments: Segments de diarisation (buckets temporels)
            full_text: Texte complet (pour validation/complétion)
            
        Returns:
            list: Segments alignés {start, end, speaker, text}
        """
        logger.info(f"Début alignement strict: {len(transcriptions)} segments trans, {len(diarization_segments)} segments diar")
        
        # 1. Nettoyage et tri
        cleaned_transcriptions = self.clean_transcription_segments(transcriptions)
        
        # FALLBACK CRITIQUE: Si pas de segments mais du texte, utiliser la distribution séquentielle
        if not cleaned_transcriptions and full_text:
            logger.warning("Pas de segments de transcription reçus, fallback sur distribution séquentielle du texte complet")
            return self.distribute_by_chronological_order(full_text, diarization_segments)
            
        cleaned_transcriptions.sort(key=lambda x: x.get('start', 0))
        diarization_segments = sorted(diarization_segments, key=lambda x: x.get('start', 0))
        
        if cleaned_transcriptions:
            logger.info(f"Plage trans: {cleaned_transcriptions[0].get('start', 0):.1f}s - {cleaned_transcriptions[-1].get('end', 0):.1f}s")
        if diarization_segments:
            logger.info(f"Plage diar: {diarization_segments[0].get('start', 0):.1f}s - {diarization_segments[-1].get('end', 0):.1f}s")
        
        # 2. Calcul et application de l'offset optimal (alignement temporel global)
        offset = self.calculate_optimal_offset(cleaned_transcriptions, diarization_segments)
        logger.info(f"Offset appliqué: {offset}s")
        
        # Appliquer l'offset aux transcriptions pour les aligner sur la diarisation
        aligned_source = []
        for t in cleaned_transcriptions:
            t_copy = t.copy()
            t_copy['start'] += offset
            t_copy['end'] += offset
            aligned_source.append(t_copy)
            
        # 3. Attribution intelligente (Distribution Séquentielle)
        # On distribue les mots dans les buckets temporels (diarisation)
        
        diar_text_buckets = {i: [] for i in range(len(diarization_segments))}
        words_distributed = 0
        
        for trans in aligned_source:
            t_start = trans.get('start', 0)
            t_end = trans.get('end', 0)
            text = trans.get('text', '').strip()
            if not text: continue
            
            words = text.split()
            if not words: continue
            
            # Trouver quels segments de diarisation chevauchent ce segment de texte
            overlaps = []
            for i, diar_seg in enumerate(diarization_segments):
                d_start = diar_seg['start']
                d_end = diar_seg['end']
                
                # Calcul de l'overlap
                ov_start = max(t_start, d_start)
                ov_end = min(t_end, d_end)
                duration = max(0, ov_end - ov_start)
                
                if duration > 0.05: # Ignorer les micro-overlaps (<50ms)
                    overlaps.append({
                        'index': i,
                        'duration': duration,
                        'start': ov_start
                    })
            
            if not overlaps:
                continue
                
            # Trier les overlaps par ordre chronologique
            overlaps.sort(key=lambda x: x['start'])
            
            # Distribuer les mots proportionnellement à la durée de l'overlap
            total_duration = sum(o['duration'] for o in overlaps)
            if total_duration == 0: continue
            
            current_word_idx = 0
            for i, ov in enumerate(overlaps):
                # Si c'est le dernier overlap, on lui donne tout le reste pour ne rien perdre
                if i == len(overlaps) - 1:
                    chunk = words[current_word_idx:]
                else:
                    ratio = ov['duration'] / total_duration
                    count = int(round(len(words) * ratio))
                    # S'assurer qu'on avance si le ratio est significatif
                    if count == 0 and len(words) > 0 and ratio > 0.2: count = 1
                    
                    chunk = words[current_word_idx : current_word_idx + count]
                    current_word_idx += count
                
                if chunk:
                    diar_text_buckets[ov['index']].append(" ".join(chunk))
                    words_distributed += len(chunk)
                    
        logger.info(f"Mots distribués: {words_distributed}")
                    
        # Construire le résultat final
        total_mapped = 0
        final_segments = []
        for i, diar_seg in enumerate(diarization_segments):
            text_parts = diar_text_buckets[i]
            final_text = " ".join(text_parts).strip()
            
            if final_text:
                total_mapped += 1
            
            final_segments.append({
                "start": diar_seg['start'],
                "end": diar_seg['end'],
                "speaker": diar_seg.get('speaker', 'UNKNOWN'),
                "text": final_text
            })
            
        logger.info(f"Segments mappés avec texte: {total_mapped}/{len(final_segments)}")

        return final_segments
    
    def distribute_by_chronological_order(self, full_text: str,
                                         diarization_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Distribution séquentielle : le texte est distribué dans l'ordre chronologique
        strict des segments de diarisation
        
        Args:
            full_text: Texte complet
            diarization_segments: Segments de diarisation
            
        Returns:
            list: Segments avec texte distribué
        """
        sorted_segments = sorted(diarization_segments, key=lambda x: x.get('start', 0))
        
        # Découper le texte en phrases
        sentence_pattern = r'([.!?])\s+'
        sentences = re.split(sentence_pattern, full_text)
        
        # Reconstruire les phrases complètes
        complete_sentences = []
        i = 0
        while i < len(sentences):
            sentence = sentences[i].strip()
            if i + 1 < len(sentences):
                punctuation = sentences[i + 1]
                sentence += punctuation
                i += 2
            else:
                i += 1
            
            if sentence:
                complete_sentences.append(sentence)
        
        complete_sentences = [s.strip() for s in complete_sentences if s.strip()]
        total_sentences = len(complete_sentences)
        
        logger.info(f"Distribution séquentielle: {total_sentences} phrases sur {len(sorted_segments)} segments")
        
        # Calculer la durée totale de parole
        total_speech_duration = sum(seg.get('end', 0) - seg.get('start', 0) 
                                   for seg in sorted_segments)
        
        if total_speech_duration == 0:
            logger.error("Durée totale de parole = 0, impossible de distribuer")
            return [{"start": seg['start'], "end": seg['end'], 
                    "speaker": seg['speaker'], "text": ""} 
                   for seg in sorted_segments]
        
        # Distribution séquentielle
        transcriptions = []
        sentence_index = 0
        current_speaker = None
        
        for seg_idx, diar_seg in enumerate(sorted_segments):
            diar_start = diar_seg.get('start', 0)
            diar_end = diar_seg.get('end', 0)
            diar_duration = diar_end - diar_start
            seg_speaker = diar_seg.get('speaker', 'UNKNOWN')
            
            # Calculer le nombre de phrases pour ce segment
            if diar_duration > 0 and total_speech_duration > 0:
                sentences_for_segment = (diar_duration / total_speech_duration) * total_sentences
                sentences_count = max(1, int(round(sentences_for_segment)))
            else:
                sentences_count = 0
            
            # Prendre les phrases suivantes dans l'ordre
            segment_sentences = []
            if sentences_count > 0 and sentence_index < total_sentences:
                end_index = min(sentence_index + sentences_count, total_sentences)
                segment_sentences = complete_sentences[sentence_index:end_index]
                sentence_index = end_index
            
            segment_text = " ".join(segment_sentences).strip()
            current_speaker = seg_speaker
            
            transcriptions.append({
                "start": diar_start,
                "end": diar_end,
                "speaker": seg_speaker,
                "text": segment_text
            })
        
        # Distribuer les phrases restantes
        if sentence_index < total_sentences:
            remaining_sentences = complete_sentences[sentence_index:]
            remaining_text = " ".join(remaining_sentences).strip()
            if transcriptions:
                transcriptions[-1]["text"] = (transcriptions[-1]["text"] + " " + remaining_text).strip()
                logger.info(f"Ajout de {len(remaining_sentences)} phrases restantes au dernier segment")
        
        segments_with_text = sum(1 for t in transcriptions if t.get('text', '').strip())
        logger.info(f"Distribution séquentielle terminée: {segments_with_text}/{len(transcriptions)} segments avec texte")
        
        return transcriptions
    
    def distribute_by_linguistic_cues(self, full_text: str,
                                     diarization_segments: List[Dict[str, Any]],
                                     total_speech_duration: float) -> List[Dict[str, Any]]:
        """
        Distribue le texte complet selon les segments de diarisation en utilisant des indices linguistiques
        
        Args:
            full_text: Texte complet de la transcription
            diarization_segments: Segments de diarisation avec speakers
            total_speech_duration: Durée totale de parole en secondes
            
        Returns:
            list: Segments mappés avec speaker et texte distribué par phrases complètes
        """
        logger.info(f"Distribution linguistique: {len(full_text)} caractères sur {len(diarization_segments)} segments")
        
        # Découper le texte en phrases
        sentence_pattern = r'([.!?])\s+'
        sentences = re.split(sentence_pattern, full_text)
        
        # Reconstruire les phrases complètes avec leur ponctuation
        complete_sentences = []
        i = 0
        while i < len(sentences):
            sentence = sentences[i].strip()
            if i + 1 < len(sentences):
                punctuation = sentences[i + 1]
                sentence += punctuation
                i += 2
            else:
                i += 1
            
            if sentence:
                complete_sentences.append(sentence)
        
        complete_sentences = [s.strip() for s in complete_sentences if s.strip()]
        total_sentences = len(complete_sentences)
        logger.info(f"Découpage en phrases: {total_sentences} phrases détectées")
        
        if total_sentences == 0:
            logger.warning("Aucune phrase détectée, utilisation de la distribution par mots")
            return self._distribute_by_words(full_text, diarization_segments, total_speech_duration)
        
        # Distribuer les phrases aux segments proportionnellement
        transcriptions = []
        sentence_index = 0
        
        for seg_idx, diar_seg in enumerate(diarization_segments):
            diar_start = diar_seg.get('start', 0)
            diar_end = diar_seg.get('end', 0)
            diar_duration = diar_end - diar_start
            
            if diar_duration > 0 and total_speech_duration > 0:
                sentences_for_segment = (diar_duration / total_speech_duration) * total_sentences
                sentences_count = max(0, int(round(sentences_for_segment)))
            else:
                sentences_count = 0
            
            segment_sentences = []
            if sentences_count > 0 and sentence_index < total_sentences:
                end_index = min(sentence_index + sentences_count, total_sentences)
                segment_sentences = complete_sentences[sentence_index:end_index]
                sentence_index = end_index
            
            segment_text = " ".join(segment_sentences).strip()
            
            if seg_idx < 3:
                logger.debug(f"Segment {seg_idx + 1}: [{diar_start:.1f}s - {diar_end:.1f}s] speaker={diar_seg.get('speaker', 'UNKNOWN')} -> {len(segment_sentences)} phrases")
            
            transcriptions.append({
                "start": diar_start,
                "end": diar_end,
                "speaker": diar_seg.get('speaker', 'UNKNOWN'),
                "text": segment_text
            })
        
        # Distribuer les phrases restantes
        if sentence_index < total_sentences:
            remaining_sentences = complete_sentences[sentence_index:]
            remaining_text = " ".join(remaining_sentences).strip()
            if transcriptions:
                transcriptions[-1]["text"] = (transcriptions[-1]["text"] + " " + remaining_text).strip()
                logger.info(f"Ajout de {len(remaining_sentences)} phrases restantes au dernier segment")
        
        segments_with_text = sum(1 for t in transcriptions if t.get('text', '').strip())
        logger.info(f"Distribution linguistique terminée: {segments_with_text}/{len(transcriptions)} segments avec texte")
        
        return transcriptions
    
    def fill_missing_segments(self, transcriptions: List[Dict[str, Any]],
                              full_text: str,
                              diarization_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Complète les segments sans texte avec distribution séquentielle
        
        Args:
            transcriptions: Segments de transcription (certains peuvent être vides)
            full_text: Texte complet
            diarization_segments: Segments de diarisation
            
        Returns:
            list: Segments complétés
        """
        segments_without_text = [i for i, t in enumerate(transcriptions) 
                                if not t.get('text', '').strip()]
        
        if not segments_without_text:
            return transcriptions
        
        logger.info(f"Complétion de {len(segments_without_text)} segments sans texte")
        
        remaining_text = full_text
        
        sentences = re.split(r'([.!?])\s+', remaining_text)
        complete_sentences = []
        i = 0
        while i < len(sentences):
            sentence = sentences[i].strip()
            if i + 1 < len(sentences):
                sentence += sentences[i + 1]
                i += 2
            else:
                i += 1
            if sentence:
                complete_sentences.append(sentence)
        
        # Distribuer proportionnellement aux segments vides
        total_duration_empty = sum(diarization_segments[i].get('end', 0) - diarization_segments[i].get('start', 0)
                                  for i in segments_without_text)
        
        if total_duration_empty > 0:
            sentence_index = 0
            for idx in segments_without_text:
                seg = diarization_segments[idx]
                seg_duration = seg.get('end', 0) - seg.get('start', 0)
                
                if seg_duration > 0:
                    sentences_for_seg = int((seg_duration / total_duration_empty) * len(complete_sentences))
                    sentences_for_seg = max(1, sentences_for_seg)
                    
                    if sentence_index < len(complete_sentences):
                        end_idx = min(sentence_index + sentences_for_seg, len(complete_sentences))
                        seg_sentences = complete_sentences[sentence_index:end_idx]
                        transcriptions[idx]["text"] = " ".join(seg_sentences).strip()
                        sentence_index = end_idx
        
        return transcriptions
    
    def _distribute_by_words(self, full_text: str,
                            diarization_segments: List[Dict[str, Any]],
                            total_speech_duration: float) -> List[Dict[str, Any]]:
        """
        Fallback : distribue le texte par mots si aucune phrase détectée
        
        Args:
            full_text: Texte complet
            diarization_segments: Segments de diarisation
            total_speech_duration: Durée totale de parole
            
        Returns:
            list: Segments avec texte distribué
        """
        words = full_text.split()
        total_words = len(words)
        text_index = 0
        transcriptions = []
        
        for diar_seg in diarization_segments:
            diar_start = diar_seg.get('start', 0)
            diar_end = diar_seg.get('end', 0)
            diar_duration = diar_end - diar_start
            
            if diar_duration > 0 and total_speech_duration > 0:
                words_for_segment = int((diar_duration / total_speech_duration) * total_words)
            else:
                words_for_segment = 0
            
            if words_for_segment > 0 and text_index < total_words:
                segment_words = words[text_index:text_index + words_for_segment]
                segment_text = " ".join(segment_words)
                text_index += words_for_segment
            else:
                segment_text = ""
            
            transcriptions.append({
                "start": diar_start,
                "end": diar_end,
                "speaker": diar_seg.get('speaker', 'UNKNOWN'),
                "text": segment_text
            })
        
        # Ajouter les mots restants au dernier segment
        if text_index < total_words and transcriptions:
            remaining_words = words[text_index:]
            remaining_text = " ".join(remaining_words)
            transcriptions[-1]["text"] = (transcriptions[-1]["text"] + " " + remaining_text).strip()
        
        return transcriptions
