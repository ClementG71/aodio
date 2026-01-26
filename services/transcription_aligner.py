"""
Service d'alignement et distribution du texte de transcription
Extrait de mistral_voxtral.py pour une meilleure modularité
"""
import re
import logging
from typing import Dict, List, Any

from services.nlp_service import get_nlp

logger = logging.getLogger(__name__)


class TranscriptionAligner:
    """Aligne et distribue le texte de transcription avec les segments de diarisation"""
    
    def __init__(self):
        """Initialise l'aligner - utilise le singleton Spacy"""
        logger.info("TranscriptionAligner initialisé - utilisera le singleton Spacy")
    
    def _get_nlp(self):
        """Retourne l'instance Spacy partagée (singleton)"""
        return get_nlp()
    
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
        Alignement Text-First avec Spacy :
        1. Analyse linguistique pour préserver l'intégrité des phrases
        2. Distribution temporelle intelligente ("Snap-to-Grid" linguistique)
        
        Args:
            transcriptions: Segments de transcription bruts (avec timestamps)
            diarization_segments: Segments de diarisation (buckets temporels)
            full_text: Texte complet (pour validation/complétion)
            
        Returns:
            list: Segments alignés {start, end, speaker, text}
        """
        logger.info(f"Début alignement NLP: {len(transcriptions)} segments trans, {len(diarization_segments)} segments diar")
        
        # 1. Nettoyage et tri
        cleaned_transcriptions = self.clean_transcription_segments(transcriptions)
        
        if not cleaned_transcriptions and full_text:
            logger.warning("Pas de segments de transcription reçus, fallback sur distribution séquentielle du texte complet")
            return self.distribute_by_chronological_order(full_text, diarization_segments)
            
        cleaned_transcriptions.sort(key=lambda x: x.get('start', 0))
        diarization_segments = sorted(diarization_segments, key=lambda x: x.get('start', 0))
        
        # 2. Calcul et application de l'offset optimal
        offset = self.calculate_optimal_offset(cleaned_transcriptions, diarization_segments)
        logger.info(f"Offset appliqué: {offset}s")
        
        # Appliquer l'offset aux transcriptions
        aligned_source = []
        for t in cleaned_transcriptions:
            t_copy = t.copy()
            t_copy['start'] += offset
            t_copy['end'] += offset
            aligned_source.append(t_copy)
            
        # 3. Alignement avec Spacy (Sentence-Level)
        nlp = self._get_nlp()
        if nlp:
            return self._align_with_spacy(aligned_source, diarization_segments)
        else:
            return self._align_statistical(aligned_source, diarization_segments)

    def _align_with_spacy(self, transcriptions: List[Dict[str, Any]], 
                         diarization_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Alignement fin utilisant la détection de phrases de Spacy
        """
        # Préparer les buckets
        diar_text_buckets = {i: [] for i in range(len(diarization_segments))}
        
        for trans in transcriptions:
            t_start = trans.get('start', 0)
            t_end = trans.get('end', 0)
            text = trans.get('text', '').strip()
            
            if not text: continue
            
            t_duration = t_end - t_start
            if t_duration <= 0: continue
            
            # Analyser le segment avec Spacy
            nlp = self._get_nlp()
            doc = nlp(text)
            sentences = list(doc.sents)
            
            if not sentences: # Cas rare, traiter comme un bloc
                sentences = [doc] # Traiter tout le doc comme une span
            
            # Pour chaque phrase, estimer son timestamp
            # Hypothèse : distribution linéaire des caractères
            total_chars = len(text)
            char_duration = t_duration / total_chars if total_chars > 0 else 0
            
            for sent in sentences:
                sent_text = sent.text.strip()
                if not sent_text: continue
                
                # Calculer offset relatif
                sent_start_char = sent.start_char
                sent_end_char = sent.end_char
                
                sent_start_time = t_start + (sent_start_char * char_duration)
                sent_end_time = t_start + (sent_end_char * char_duration)
                sent_mid_time = (sent_start_time + sent_end_time) / 2
                
                # Trouver le meilleur segment de diarisation
                best_diar_idx = -1
                best_overlap = 0
                max_center_in = False
                
                for i, diar_seg in enumerate(diarization_segments):
                    d_start = diar_seg['start']
                    d_end = diar_seg['end']
                    
                    # Chevauchement
                    ov_start = max(sent_start_time, d_start)
                    ov_end = min(sent_end_time, d_end)
                    overlap = max(0, ov_end - ov_start)
                    
                    # Si le centre de la phrase est dans le segment, c'est un candidat fort
                    if d_start <= sent_mid_time <= d_end:
                        max_center_in = True
                        best_diar_idx = i
                        break # On privilégie le segment central
                    
                    if overlap > best_overlap:
                        best_overlap = overlap
                        best_diar_idx = i
                
                if best_diar_idx != -1:
                    diar_text_buckets[best_diar_idx].append(sent_text)
                else:
                    # Si pas d'overlap trouvé (ex: trou dans la diarisation),
                    # on l'assigne au segment le plus proche temporellement
                    closest_idx = -1
                    min_dist = float('inf')
                    
                    for i, diar_seg in enumerate(diarization_segments):
                        dist = min(abs(diar_seg['start'] - sent_end_time), 
                                   abs(diar_seg['end'] - sent_start_time))
                        if dist < min_dist:
                            min_dist = dist
                            closest_idx = i
                    
                    if closest_idx != -1:
                        diar_text_buckets[closest_idx].append(sent_text)

        # Reconstruire les segments
        final_segments = []
        for i, diar_seg in enumerate(diarization_segments):
            text_parts = diar_text_buckets[i]
            final_text = " ".join(text_parts).strip()
            
            final_segments.append({
                "start": diar_seg['start'],
                "end": diar_seg['end'],
                "speaker": diar_seg.get('speaker', 'UNKNOWN'),
                "text": final_text
            })
            
        return final_segments

    def _align_statistical(self, transcriptions: List[Dict[str, Any]], 
                          diarization_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Ancienne méthode statistique (fallback)
        """
        diar_text_buckets = {i: [] for i in range(len(diarization_segments))}
        
        for trans in transcriptions:
            t_start = trans.get('start', 0)
            t_end = trans.get('end', 0)
            text = trans.get('text', '').strip()
            if not text: continue
            
            words = text.split()
            if not words: continue
            
            overlaps = []
            for i, diar_seg in enumerate(diarization_segments):
                d_start = diar_seg['start']
                d_end = diar_seg['end']
                ov_start = max(t_start, d_start)
                ov_end = min(t_end, d_end)
                duration = max(0, ov_end - ov_start)
                
                if duration > 0.05:
                    overlaps.append({'index': i, 'duration': duration, 'start': ov_start})
            
            if not overlaps: continue
            overlaps.sort(key=lambda x: x['start'])
            
            total_duration = sum(o['duration'] for o in overlaps)
            if total_duration == 0: continue
            
            current_word_idx = 0
            for i, ov in enumerate(overlaps):
                if i == len(overlaps) - 1:
                    chunk = words[current_word_idx:]
                else:
                    ratio = ov['duration'] / total_duration
                    count = int(round(len(words) * ratio))
                    if count == 0 and len(words) > 0 and ratio > 0.2: count = 1
                    chunk = words[current_word_idx : current_word_idx + count]
                    current_word_idx += count
                
                if chunk:
                    diar_text_buckets[ov['index']].append(" ".join(chunk))
                    
        final_segments = []
        for i, diar_seg in enumerate(diarization_segments):
            final_text = " ".join(diar_text_buckets[i]).strip()
            final_segments.append({
                "start": diar_seg['start'],
                "end": diar_seg['end'],
                "speaker": diar_seg.get('speaker', 'UNKNOWN'),
                "text": final_text
            })
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
    
    def fill_missing_segments(self, transcriptions: List[Dict[str, Any]],
                              full_text: str,
                              diarization_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Complète les segments sans texte avec distribution séquentielle
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
