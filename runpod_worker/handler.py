"""
Worker RunPod pour la diarisation avec Pyannote 4.0.2
PyTorch 2.5.0 + CUDA 12.1 (versions stables)
"""
import sys
import traceback

# Bloc try/except global pour capturer les erreurs d'import au démarrage
try:
    import os
    import tempfile
    import requests
    import runpod
    import torch
    from huggingface_hub import login
    
    print(f"DEBUG: Torch version: {torch.__version__}")
    print(f"DEBUG: CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"DEBUG: CUDA version: {torch.version.cuda}")
        print(f"DEBUG: Device: {torch.cuda.get_device_name(0)}")

    # Import Pyannote différé ou protégé pour diagnostiquer
    try:
        from pyannote.audio import Pipeline
        print("Import Pyannote.audio réussi")
    except ImportError as e:
        print(f"CRITICAL: Erreur import pyannote.audio: {e}")
        traceback.print_exc()
        raise

except Exception as e:
    print(f"CRITICAL: Erreur au démarrage du worker: {e}")
    traceback.print_exc()
    sys.exit(1)

# Configuration
DIARIZATION_MODEL = "pyannote/speaker-diarization-3.1"
HF_TOKEN = os.getenv("HF_TOKEN")

# Initialisation du pipeline (chargé une seule fois au démarrage)
pipeline = None

def load_pipeline():
    """
    Charge le pipeline Pyannote de manière lazy (au premier appel)
    """
    global pipeline
    if pipeline is not None:
        return pipeline
    
    print("Chargement du modèle Pyannote 4.0...")
    
    if HF_TOKEN:
        os.environ["HUGGING_FACE_HUB_TOKEN"] = HF_TOKEN
        try:
            login(token=HF_TOKEN, add_to_git_credential=False)
            print("Authentification Hugging Face configurée")
        except Exception as e:
            print(f"Warning: Erreur lors de l'authentification Hugging Face: {e}")
    
    try:
        # Dans Pyannote 4.0, pipeline.to(device) est obligatoire pour GPU
        pipeline = Pipeline.from_pretrained(DIARIZATION_MODEL)
        
        if torch.cuda.is_available():
            device = torch.device("cuda")
            pipeline.to(device)
            print(f"Pipeline déplacé sur GPU: {device}")
        else:
            print("Attention: GPU non disponible, utilisation CPU (lent)")
            
        print("Modèle Pyannote chargé avec succès!")
        return pipeline
    except Exception as e:
        error_msg = f"Erreur lors du chargement du pipeline Pyannote: {str(e)}"
        print(f"ERROR: {error_msg}")
        import traceback
        traceback.print_exc()
        raise Exception(error_msg)


def download_audio(audio_url: str) -> str:
    """Télécharge un fichier audio depuis une URL"""
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
    temp_path = temp_file.name
    temp_file.close()
    
    response = requests.get(audio_url, stream=True)
    response.raise_for_status()
    
    with open(temp_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    
    return temp_path


def diarize_audio(audio_path: str, params: dict = None) -> dict:
    """
    Effectue la diarisation avec Pyannote
    Supporte les paramètres min_speakers et max_speakers
    """
    load_pipeline()
    params = params or {}
    
    # Préparation des options d'inférence
    inference_options = {}
    if 'min_speakers' in params:
        inference_options['min_speakers'] = int(params['min_speakers'])
    if 'max_speakers' in params:
        inference_options['max_speakers'] = int(params['max_speakers'])
    if 'num_speakers' in params:
        inference_options['num_speakers'] = int(params['num_speakers'])
        
    print(f"Lancement diarisation avec options: {inference_options}")
    
    # Pyannote 4.0 : appel standard
    if inference_options:
        diarization = pipeline(audio_path, **inference_options)
    else:
        diarization = pipeline(audio_path)
    
    # Formatage des résultats
    # Pyannote 4.0 peut renvoyer des labels différents, on standardise
    segments = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        segments.append({
            "start": float(turn.start),
            "end": float(turn.end),
            "speaker": str(speaker)
        })
    
    return {"segments": segments}


def handler(event):
    """Handler principal du worker RunPod"""
    try:
        input_data = event.get("input", {})
        task = input_data.get("task")
        
        if task != "diarization":
            return {"error": f"Tâche non supportée: {task}. Seule 'diarization' est supportée."}
        
        audio_url = input_data.get("audio_url")
        if not audio_url:
            return {"error": "audio_url est requis"}
            
        # Récupération des paramètres optionnels
        params = {
            'min_speakers': input_data.get('min_speakers'),
            'max_speakers': input_data.get('max_speakers'),
            'num_speakers': input_data.get('num_speakers')
        }
        # Nettoyer les None
        params = {k: v for k, v in params.items() if v is not None}
        
        print(f"Téléchargement de l'audio depuis: {audio_url}")
        audio_path = download_audio(audio_url)
        
        try:
            print("Démarrage de la diarisation...")
            result = diarize_audio(audio_path, params)
            print(f"Diarisation terminée: {len(result['segments'])} segments trouvés")
            return result
            
        finally:
            if os.path.exists(audio_path):
                os.remove(audio_path)
                
    except Exception as e:
        error_msg = f"Erreur lors du traitement: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        return {"error": error_msg}


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
