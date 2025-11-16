"""
Worker RunPod pour la diarisation avec Pyannote 3.3.1+
Ce fichier doit être déployé sur RunPod
"""
import os
import tempfile
import requests
import runpod
from pyannote.audio import Pipeline
import torch

# Configuration
DIARIZATION_MODEL = "pyannote/speaker-diarization-3.1"
HF_TOKEN = os.getenv("HF_TOKEN")

# Initialisation du pipeline (chargé une seule fois au démarrage)
print("Chargement du modèle Pyannote...")
# Note: Dans pyannote.audio 3.3.1+, le paramètre est 'token' (pas 'use_auth_token')
# pyannote.audio 3.3.1+ est compatible avec NumPy 2.0
pipeline = Pipeline.from_pretrained(
    DIARIZATION_MODEL,
    token=HF_TOKEN
)
pipeline.to(torch.device("cuda" if torch.cuda.is_available() else "cpu"))
print("Modèle Pyannote chargé avec succès!")


def download_audio(audio_url: str) -> str:
    """
    Télécharge un fichier audio depuis une URL
    
    Args:
        audio_url: URL du fichier audio
        
    Returns:
        str: Chemin local du fichier téléchargé
    """
    # Créer un fichier temporaire
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
    temp_path = temp_file.name
    temp_file.close()
    
    # Télécharger le fichier
    response = requests.get(audio_url, stream=True)
    response.raise_for_status()
    
    with open(temp_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    
    return temp_path


def diarize_audio(audio_path: str) -> dict:
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
            "start": float(turn.start),
            "end": float(turn.end),
            "speaker": speaker
        })
    
    return {"segments": segments}


def handler(event):
    """
    Handler principal du worker RunPod
    
    Args:
        event: Événement contenant les données de la requête
        
    Returns:
        dict: Résultat du traitement
    """
    try:
        input_data = event.get("input", {})
        task = input_data.get("task")
        
        if task != "diarization":
            return {"error": f"Tâche non supportée: {task}. Seule 'diarization' est supportée."}
        
        audio_url = input_data.get("audio_url")
        if not audio_url:
            return {"error": "audio_url est requis"}
        
        # Télécharger l'audio
        print(f"Téléchargement de l'audio depuis: {audio_url}")
        audio_path = download_audio(audio_url)
        
        try:
            # Diarisation
            print("Démarrage de la diarisation...")
            result = diarize_audio(audio_path)
            print(f"Diarisation terminée: {len(result['segments'])} segments trouvés")
            
            return result
            
        finally:
            # Nettoyer le fichier temporaire
            if os.path.exists(audio_path):
                os.remove(audio_path)
                
    except Exception as e:
        error_msg = f"Erreur lors du traitement: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        return {"error": error_msg}


# Démarrage du worker
if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})

