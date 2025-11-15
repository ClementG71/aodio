"""
Exemple de worker RunPod pour la diarisation et la transcription
Ce fichier sert de référence pour configurer votre worker RunPod
"""

import runpod
from pyannote.audio import Pipeline
import torch
import json
import requests

# Configuration Pyannote
DIARIZATION_MODEL = "pyannote/speaker-diarization-3.1"
HF_TOKEN = "your-huggingface-token"  # Token nécessaire pour télécharger le modèle

# Initialisation du pipeline de diarisation
pipeline = Pipeline.from_pretrained(
    DIARIZATION_MODEL,
    use_auth_token=HF_TOKEN
)
pipeline.to(torch.device("cuda" if torch.cuda.is_available() else "cpu"))


def diarize_audio(audio_path: str):
    """
    Effectue la diarisation avec Pyannote
    
    Args:
        audio_path: Chemin du fichier audio
        
    Returns:
        dict: Résultat de la diarisation avec segments
    """
    # Application du pipeline
    diarization = pipeline(audio_path)
    
    # Formatage des résultats
    segments = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        segments.append({
            "start": turn.start,
            "end": turn.end,
            "speaker": speaker
        })
    
    return {"segments": segments}


def transcribe_with_voxtral(audio_path: str, segments: list, api_key: str, endpoint: str):
    """
    Transcrit l'audio avec Voxtral en respectant les segments de diarisation
    
    Args:
        audio_path: Chemin du fichier audio
        segments: Liste des segments de diarisation
        api_key: Clé API Voxtral
        endpoint: Endpoint Voxtral
        
    Returns:
        list: Liste des transcriptions avec texte et métadonnées
    """
    transcriptions = []
    
    # Traitement par segments pour éviter la surcharge
    for segment in segments:
        # Extraction du segment audio (nécessite pydub ou similaire)
        # segment_audio = extract_audio_segment(audio_path, segment['start'], segment['end'])
        
        # Appel à l'API Voxtral
        prompt = """Objectif:
- Transcription verbatim fidèle de l'audio
- Formatage simple sans identification des locuteurs

Instructions clés:
1. Transcription mot à mot - pas de résumé ni d'interprétation
2. Respect de l'orthographe et ponctuation
3. Inclusion des hésitations naturelles
4. Pas de diarisation - les locuteurs sont déjà identifiés
5. Format de sortie minimal - juste le texte transcrit"""
        
        # Note: L'appel API Voxtral dépend de leur format spécifique
        # À adapter selon leur documentation
        # response = requests.post(
        #     endpoint,
        #     headers={"Authorization": f"Bearer {api_key}"},
        #     files={"audio": segment_audio},
        #     data={"prompt": prompt, "temperature": 0.0}
        # )
        
        # transcription = response.json()
        # transcriptions.append({
        #     "start": segment['start'],
        #     "end": segment['end'],
        #     "speaker": segment['speaker'],
        #     "text": transcription['text']
        # })
        
        pass  # À implémenter selon l'API Voxtral
    
    return transcriptions


def handler(event):
    """
    Handler principal du worker RunPod
    
    Args:
        event: Événement contenant les données de la requête
        
    Returns:
        dict: Résultat du traitement
    """
    input_data = event.get("input", {})
    task = input_data.get("task")
    
    if task == "diarization":
        audio_url = input_data.get("audio_url")
        # Télécharger l'audio depuis l'URL
        # audio_path = download_audio(audio_url)
        
        # Diarisation
        result = diarize_audio(audio_path)
        return result
        
    elif task == "transcription":
        audio_url = input_data.get("audio_url")
        segments = input_data.get("segments", [])
        api_key = input_data.get("voxtral_api_key")
        endpoint = input_data.get("voxtral_endpoint")
        
        # Transcription
        transcriptions = transcribe_with_voxtral(
            audio_url, segments, api_key, endpoint
        )
        
        return {"transcriptions": transcriptions}
    
    else:
        return {"error": f"Tâche inconnue: {task}"}


# Démarrage du worker
if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})

