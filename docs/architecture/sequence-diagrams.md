# Diagrammes de séquence

## Pipeline complet de traitement

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant Orchestrator
    participant RunPod
    participant Mistral
    participant AudioProcessor
    participant DocumentGenerator

    User->>Frontend: Upload audio + context files
    Frontend->>Orchestrator: Start processing (async)
    
    Orchestrator->>AudioProcessor: Process audio
    AudioProcessor-->>Orchestrator: Processed audio path
    
    Orchestrator->>RunPod: Diarization request (async)
    Orchestrator->>Mistral: Transcription request (async)
    
    RunPod-->>Orchestrator: Diarization results
    Mistral-->>Orchestrator: Transcription results
    
    Orchestrator->>Orchestrator: Align transcription with diarization
    Orchestrator->>Mistral: Speaker mapping request
    Mistral-->>Orchestrator: Speaker mapping results
    
    Orchestrator->>Mistral: Generate pre-CR request
    Mistral-->>Orchestrator: Pre-CR text
    
    Orchestrator->>Mistral: Extract decisions request
    Mistral-->>Orchestrator: Decisions list
    
    Orchestrator->>DocumentGenerator: Generate all documents
    DocumentGenerator-->>Orchestrator: Documents paths
    
    Orchestrator-->>Frontend: Processing complete
    User->>Frontend: Download documents
```

## Upload et traitement initial

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant Orchestrator
    participant AudioProcessor
    
    User->>Frontend: POST /upload (audio + metadata)
    Frontend->>Frontend: Validate audio file
    alt Invalid file
        Frontend-->>User: 400 Bad Request
    else Valid file
        Frontend->>Frontend: Create session folder
        Frontend->>Frontend: Save audio file
        Frontend->>Frontend: Save context files
        Frontend->>Frontend: Create metadata.json
        Frontend->>Orchestrator: process_audio_and_pipeline (async)
        Frontend-->>User: 200 OK (session_id)
        
        Orchestrator->>AudioProcessor: process_audio
        AudioProcessor->>AudioProcessor: Normalize audio
        AudioProcessor->>AudioProcessor: Convert format
        AudioProcessor-->>Orchestrator: processed_audio_path
        
        Orchestrator->>Frontend: Update metadata
    end
```

## Diarisation et transcription parallèle

```mermaid
sequenceDiagram
    participant Orchestrator
    participant RunPod
    participant Mistral
    
    Orchestrator->>RunPod: diarize_audio(audio_path)
    Orchestrator->>Mistral: transcribe_file_full(audio_path)
    
    RunPod->>RunPod: Download audio from URL
    RunPod->>RunPod: Apply Pyannote pipeline
    RunPod-->>Orchestrator: {"segments": [...]}
    
    Mistral->>Mistral: Split audio if needed
    Mistral->>Mistral: Transcribe with Voxtral
    Mistral-->>Orchestrator: {"segments": [...], "full_text": "..."}
```

## Alignement et mapping des locuteurs

```mermaid
sequenceDiagram
    participant Orchestrator
    participant TranscriptionAligner
    participant SpeakerMapper
    participant Mistral
    
    Orchestrator->>TranscriptionAligner: align_strict_improved(transcription_segments, diarization_segments)
    TranscriptionAligner-->>Orchestrator: aligned_segments
    
    Orchestrator->>TranscriptionAligner: validate_mapping(aligned_segments, diarization_segments)
    
    Orchestrator->>SpeakerMapper: identify_speakers(segments, participants_list)
    SpeakerMapper-->>Orchestrator: spacy_mapping, ambiguous_speakers
    
    alt ambiguous_speakers not empty
        Orchestrator->>Mistral: _map_speakers_with_llm(segments, ambiguous_speakers)
        Mistral-->>Orchestrator: llm_mapping
        Orchestrator->>Orchestrator: Merge mappings
    end
```

## Génération des documents

```mermaid
sequenceDiagram
    participant Orchestrator
    participant DocumentGenerator
    
    Orchestrator->>DocumentGenerator: generate_all_documents(session_id, transcription, speaker_mapping, pre_cr, decisions, date_seance)
    
    DocumentGenerator->>DocumentGenerator: _generate_minutes_txt
    DocumentGenerator->>DocumentGenerator: _generate_minutes_docx
    DocumentGenerator->>DocumentGenerator: _generate_minutes_pdf
    
    DocumentGenerator->>DocumentGenerator: _generate_pre_cr_txt
    DocumentGenerator->>DocumentGenerator: _generate_pre_cr_docx
    DocumentGenerator->>DocumentGenerator: _generate_pre_cr_pdf
    
    DocumentGenerator->>DocumentGenerator: _generate_decisions_txt
    DocumentGenerator->>DocumentGenerator: _generate_decisions_docx
    DocumentGenerator->>DocumentGenerator: _generate_decisions_pdf
    
    DocumentGenerator-->>Orchestrator: {"minutes_txt": "path", "minutes_docx": "path", ...}
```

## Récupération du statut et téléchargement

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant LogManager
    
    loop Polling
        User->>Frontend: GET /status/{session_id}
        Frontend->>LogManager: get_status(session_id)
        LogManager-->>Frontend: status_data
        Frontend-->>User: status JSON
    end
    
    User->>Frontend: GET /download/{session_id}/{document_type}
    Frontend->>Frontend: Load metadata
    Frontend->>Frontend: Check status == 'completed'
    Frontend->>Frontend: Get document path
    Frontend-->>User: File download
```