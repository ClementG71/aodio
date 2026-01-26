"""
Orchestrateur principal pour le pipeline de traitement audio
"""
import os
import json
import logging
import concurrent.futures
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime

from core.interfaces import (
    AudioProcessingService,
    DiarizationService,
    TranscriptionService,
    LLMSpeakerMappingService,
    DocumentGenerationService,
    LogManagementService
)

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """Orchestre le pipeline complet de traitement audio"""
    
    def __init__(self, 
                 audio_processor: AudioProcessingService,
                 diarization_service: DiarizationService,
                 transcription_service: TranscriptionService,
                 llm_speaker_mapper: LLMSpeakerMappingService,
                 document_generator: DocumentGenerationService,
                 log_manager: LogManagementService,
                 app_base_url: str):
        """
        Initialise l'orchestrateur
        
        Args:
            audio_processor: Service de traitement audio
            diarization_service: Service de diarisation
            transcription_service: Service de transcription
            llm_speaker_mapper: Service de mapping des locuteurs
            document_generator: Service de génération de documents
            log_manager: Service de gestion des logs
            app_base_url: URL de base de l'application
        """
        self.audio_processor = audio_processor
        self.diarization_service = diarization_service
        self.transcription_service = transcription_service
        self.llm_speaker_mapper = llm_speaker_mapper
        self.document_generator = document_generator
        self.log_manager = log_manager
        self.app_base_url = app_base_url
        
    def _run_diarization_with_timeout(self, session_id: str, audio_path: str, timeout: int = 900) -> Dict[str, Any]:
        """
        Exécute la diarisation avec gestion de timeout et fallback
        
        Args:
            session_id: ID de la session
            audio_path: Chemin du fichier audio
            timeout: Timeout en secondes (15 minutes par défaut)
            
        Returns:
            dict: Résultat de la diarisation
            
        Raises:
            TimeoutError: Si la diarisation prend trop de temps
            Exception: En cas d'erreur critique
        """
        import concurrent.futures
        
        self.log_manager.log_status(session_id, 'diarization', 'Démarrage de la diarisation avec timeout...')
        
        try:
            # Utiliser un ThreadPoolExecutor avec timeout pour la diarisation
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as diar_executor:
                future = diar_executor.submit(
                    self.diarization_service.diarize_audio, 
                    audio_path
                )
                
                try:
                    # Attendre le résultat avec timeout
                    diarization_result = future.result(timeout=timeout)
                    self.log_manager.log_status(session_id, 'diarization', 'Diarisation terminée avec succès')
                    return diarization_result
                    
                except concurrent.futures.TimeoutError:
                    self.log_manager.log_status(session_id, 'diarization', 'Timeout atteint pour la diarisation')
                    logger.warning(f"Diarization timeout après {timeout}s pour la session {session_id}")
                    
                    # Annuler le job en cours
                    future.cancel()
                    
                    # Retourner un résultat vide pour permettre la continuation
                    return {
                        'segments': [],
                        'speakers': [],
                        'status': 'timeout',
                        'message': f'Diarization timeout après {timeout}s'
                    }
                    
        except Exception as e:
            error_msg = f"Erreur critique lors de la diarisation: {str(e)}"
            self.log_manager.log_status(session_id, 'diarization', error_msg)
            logger.error(error_msg, exc_info=True)
            
            # Retourner un résultat d'erreur pour permettre la continuation
            return {
                'segments': [],
                'speakers': [],
                'status': 'error',
                'message': error_msg
            }
    
    def process_audio_pipeline(self, session_id: str, metadata: Dict[str, Any]):
        """
        Pipeline complet de traitement audio
        
        Args:
            session_id: ID de la session
            metadata: Métadonnées de la session
        """
        try:
            self.log_manager.log_status(session_id, 'processing', 'Démarrage du traitement')
            
            # 1. Diarisation et Transcription en parallèle (Text-First)
            self.log_manager.log_status(session_id, 'processing', 'Lancement Diarisation et Transcription en parallèle...')
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                # Diarisation (RunPod) - avec timeout et gestion d'erreurs
                future_diar = executor.submit(
                    self._run_diarization_with_timeout, 
                    session_id, 
                    metadata['processed_audio']
                )
                
                # Transcription Text-First (Mistral)
                future_trans = executor.submit(
                    self.transcription_service.transcribe_file_full, 
                    metadata['processed_audio'], "fr"
                )
                
                # Attente résultats
                diarization_result = future_diar.result()
                
                # Vérifier si la diarisation a réussi
                if diarization_result.get('status') in ['timeout', 'error']:
                    self.log_manager.log_status(session_id, 'diarization', 'Diarisation en erreur ou timeout', diarization_result)
                    logger.warning(f"Diarization issue: {diarization_result.get('message', 'Unknown error')}")
                    
                    # Continuer avec un résultat vide plutôt que de bloquer
                    diarization_result = {
                        'segments': [],
                        'speakers': []
                    }
                else:
                    self.log_manager.log_status(session_id, 'diarization', 'Diarisation terminée', diarization_result)
                
                raw_transcription = future_trans.result()
                self.log_manager.log_status(session_id, 'transcription', 'Transcription brute terminée (Text-First)')
            
            # 2. Alignement (Fusion)
            self.log_manager.log_status(session_id, 'processing', 'Alignement Audio/Texte en cours...')
            
            aligned_segments = self.transcription_service.aligner.align_strict_improved(
                raw_transcription.get('segments', []),
                diarization_result.get('segments', []),
                raw_transcription.get('full_text', '')
            )
            
            # Validation finale
            self.transcription_service.mapper.validate_mapping(aligned_segments, diarization_result.get('segments', []))
            
            # Reconstruction résultat standard
            transcription_result = {
                "segments": aligned_segments,
                "full_text": raw_transcription.get('full_text', '')
            }
            self.log_manager.log_status(session_id, 'transcription', 'Transcription alignée et validée', transcription_result)
            
            # 3. Traitement LLM (Full Mistral)
            self.log_manager.log_status(session_id, 'llm_processing', 'Démarrage du traitement LLM (Mistral)')
            
            # Mapping des locuteurs (Hybride Spacy + Mistral Small)
            speaker_mapping = self.llm_speaker_mapper.map_speakers(
                transcription_result,
                metadata.get('context_files', {}).get('liste_participants'),
                metadata.get('president_seance')
            )
            self.log_manager.log_status(session_id, 'llm_processing', 'Mapping des locuteurs terminé', speaker_mapping)
            
            # Génération du pré-compte rendu (Mistral Large)
            pre_cr = self.llm_speaker_mapper.generate_pre_compte_rendu(
                transcription_result.get('full_text', ''),
                speaker_mapping
            )
            self.log_manager.log_status(session_id, 'llm_processing', 'Pré-compte rendu généré')
            
            # Extraction des décisions (Mistral Large)
            decisions = self.llm_speaker_mapper.extract_decisions(
                transcription_result.get('full_text', ''),
                speaker_mapping
            )
            self.log_manager.log_status(session_id, 'llm_processing', 'Décisions extraites', decisions)
            
            # 4. Génération des documents
            self.log_manager.log_status(session_id, 'document_generation', 'Génération des documents')
            date_seance = metadata.get('date_seance', datetime.now().strftime('%Y-%m-%d'))
            
            documents = self.document_generator.generate_all_documents(
                session_id=session_id,
                transcription=transcription_result,
                speaker_mapping=speaker_mapping,
                pre_cr=pre_cr,
                decisions=decisions,
                date_seance=date_seance,
                output_folder=os.getenv('PROCESSED_FOLDER', 'processed')
            )
            
            self.log_manager.log_status(session_id, 'completed', 'Traitement terminé avec succès', documents)
            
            # Mise à jour des métadonnées
            metadata['status'] = 'completed'
            metadata['documents'] = documents
            metadata_path = Path(os.getenv('UPLOAD_FOLDER', 'uploads')) / session_id / 'metadata.json'
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
                
            return documents
            
        except Exception as e:
            logger.error(f"Erreur dans le pipeline pour {session_id}: {str(e)}", exc_info=True)
            self.log_manager.log_status(session_id, 'error', f'Erreur: {str(e)}')
            raise


class AudioPipelineOrchestrator:
    """Orchestre le traitement audio et lance le pipeline complet"""
    
    def __init__(self, audio_processor: AudioProcessingService, log_manager: LogManagementService):
        """
        Initialise l'orchestrateur audio
        
        Args:
            audio_processor: Service de traitement audio
            log_manager: Service de gestion des logs
        """
        self.audio_processor = audio_processor
        self.log_manager = log_manager
    
    def process_audio_and_pipeline(self, session_id: str, metadata: Dict[str, Any], audio_path: str):
        """
        Traite l'audio puis lance le pipeline complet
        
        Args:
            session_id: ID de la session
            metadata: Métadonnées de la session
            audio_path: Chemin du fichier audio
        """
        try:
            # Traitement de l'audio (normalisation et compression)
            logger.info(f"Début du traitement audio pour la session {session_id}")
            processed_audio_path = self.audio_processor.process_audio(
                audio_path,
                str(Path(os.getenv('UPLOAD_FOLDER', 'uploads')) / session_id / 'audio_processed.wav')
            )
            
            # Mise à jour des métadonnées avec le chemin du fichier traité
            metadata['processed_audio'] = processed_audio_path
            metadata['status'] = 'audio_processed'
            metadata_path = Path(os.getenv('UPLOAD_FOLDER', 'uploads')) / session_id / 'metadata.json'
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Traitement audio terminé pour la session {session_id}, démarrage du pipeline...")
            
        except Exception as e:
            logger.error(f"Erreur lors du traitement audio pour {session_id}: {str(e)}", exc_info=True)
            # Mettre à jour le statut en cas d'erreur
            try:
                self.log_manager.log_status(session_id, 'error', f'Erreur lors du traitement audio: {str(e)}')
            except Exception as log_error:
                logger.warning(f"Erreur non critique lors de la journalisation: {log_error}")
            raise