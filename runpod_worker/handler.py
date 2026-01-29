"""
Worker RunPod pour la diarisation avec Pyannote 3.3.x
Pyannote 3.x + PyTorch 2.x (géré par pyannote.audio)
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
    Charge le pipeline Pyannote de manière lazy (au premier appel).
    Version simplifiée pour Pyannote 2.1.x : pas de gestion avancée de cache ou de timeout.
    """
    global pipeline
    import os  # Import local pour éviter UnboundLocalError
    import json
    import time

    # #region agent log
    log_path = os.getenv('DEBUG_LOG_PATH', '/tmp/debug.log')
    try:
        with open(log_path, 'a') as f:
            f.write(json.dumps({
                "location": "handler.py:load_pipeline:entry",
                "message": "load_pipeline appelé",
                "data": {"pipeline_exists": pipeline is not None},
                "timestamp": time.time(),
                "sessionId": "debug-session",
                "runId": "run1",
                "hypothesisId": "H2"
            }) + '\n')
    except Exception:
        pass
    # #endregion

    if pipeline is not None:
        return pipeline

    print("Chargement du modèle Pyannote 2.1 (speaker-diarization)...", flush=True)

    if not HF_TOKEN:
        print("WARNING: HF_TOKEN non défini, l'accès au modèle Pyannote peut échouer.", flush=True)
    else:
        os.environ["HUGGING_FACE_HUB_TOKEN"] = HF_TOKEN
        try:
            login(token=HF_TOKEN, add_to_git_credential=False)
            print("Authentification Hugging Face configurée", flush=True)
        except Exception as e:
            print(f"Warning: Erreur lors de l'authentification Hugging Face: {e}", flush=True)

    try:
        start_time = time.time()

        # #region agent log
        try:
            with open(log_path, 'a') as f:
                f.write(json.dumps({
                    "location": "handler.py:load_pipeline:before_from_pretrained",
                    "message": "Avant Pipeline.from_pretrained",
                    "data": {"model": DIARIZATION_MODEL},
                    "timestamp": time.time(),
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "H2"
                }) + '\n')
        except Exception:
            pass
        # #endregion

        # Pour Pyannote 3.x, le paramètre standard est `token`
        pipeline_args = {}
        if HF_TOKEN:
            pipeline_args["token"] = HF_TOKEN

        pipeline_local = Pipeline.from_pretrained(DIARIZATION_MODEL, **pipeline_args)
        duration = time.time() - start_time
        print(f"Pipeline.from_pretrained() terminé en {duration:.1f}s", flush=True)

        # #region agent log
        try:
            with open(log_path, 'a') as f:
                f.write(json.dumps({
                    "location": "handler.py:load_pipeline:after_from_pretrained",
                    "message": "Pipeline.from_pretrained terminé",
                    "data": {"pipeline_type": type(pipeline_local).__name__, "duration": duration},
                    "timestamp": time.time(),
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "H2"
                }) + '\n')
        except Exception:
            pass
        # #endregion

        pipeline = pipeline_local
        print("Modèle Pyannote chargé avec succès!", flush=True)
        return pipeline
    except Exception as e:
        error_msg = f"Erreur lors du chargement du pipeline Pyannote: {str(e)}"
        print(f"ERROR: {error_msg}", flush=True)
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
    import os  # Import local pour éviter UnboundLocalError
    import sys
    import time
    import json
    
    # #region agent log
    log_path = os.getenv('DEBUG_LOG_PATH', '/tmp/debug.log')
    try:
        with open(log_path, 'a') as f:
            f.write(json.dumps({"location":"handler.py:diarize_audio:entry","message":"diarize_audio appelé","data":{"audio_path":audio_path,"params":params},"timestamp":__import__('time').time(),"sessionId":"debug-session","runId":"run1","hypothesisId":"H1"}) + '\n')
    except Exception:
        pass
    # #endregion
    
    start_time = time.time()
    
    # #region agent log
    log_path = os.getenv('DEBUG_LOG_PATH', '/tmp/debug.log')
    try:
        with open(log_path, 'a') as f:
            f.write(json.dumps({"location":"handler.py:diarize_audio:before_load_pipeline","message":"Avant load_pipeline()","data":{},"timestamp":__import__('time').time(),"sessionId":"debug-session","runId":"run1","hypothesisId":"H2"}) + '\n')
    except Exception:
        pass
    # #endregion
    
    load_pipeline()
    
    # #region agent log
    log_path = os.getenv('DEBUG_LOG_PATH', '/tmp/debug.log')
    try:
        with open(log_path, 'a') as f:
            f.write(json.dumps({"location":"handler.py:diarize_audio:after_load_pipeline","message":"load_pipeline() terminé","data":{},"timestamp":__import__('time').time(),"sessionId":"debug-session","runId":"run1","hypothesisId":"H2"}) + '\n')
    except Exception:
        pass
    # #endregion
    
    params = params or {}
    
    # Préparation des options d'inférence
    inference_options = {}
    if 'min_speakers' in params:
        inference_options['min_speakers'] = int(params['min_speakers'])
    if 'max_speakers' in params:
        inference_options['max_speakers'] = int(params['max_speakers'])
    if 'num_speakers' in params:
        inference_options['num_speakers'] = int(params['num_speakers'])
        
    import sys
    print(f"Lancement diarisation avec options: {inference_options}", flush=True)
    print(f"Fichier audio: {audio_path}", flush=True)
    print(f"Taille du fichier: {os.path.getsize(audio_path) / (1024*1024):.2f} MB", flush=True)
    sys.stdout.flush()
    
    # Vérifier que le pipeline est bien sur GPU
    if torch.cuda.is_available():
        print(f"Vérification GPU: {torch.cuda.get_device_name(0)}", flush=True)
        print(f"VRAM utilisée avant: {torch.cuda.memory_allocated(0) / 1024**3:.2f} GB", flush=True)
        sys.stdout.flush()
    
    # Vérifier que le fichier audio existe et est accessible
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Fichier audio introuvable: {audio_path}")
    
    file_size = os.path.getsize(audio_path)
    print(f"Fichier audio vérifié: {file_size / (1024*1024):.2f} MB", flush=True)
    sys.stdout.flush()
    
    print("Appel du pipeline Pyannote (cela peut prendre plusieurs minutes pour un fichier de 21 min)...", flush=True)
    print("Note: L'avertissement torchcodec est normal, Pyannote utilisera soundfile en fallback", flush=True)
    sys.stdout.flush()
    
    # #region agent log
    log_path = os.getenv('DEBUG_LOG_PATH', '/tmp/debug.log')
    try:
        with open(log_path, 'a') as f:
            f.write(json.dumps({"location":"handler.py:diarize_audio:before_pipeline_call","message":"Avant appel pipeline()","data":{"audio_path":audio_path,"inference_options":inference_options,"vram_before":torch.cuda.memory_allocated(0) / 1024**3 if torch.cuda.is_available() else 0},"timestamp":__import__('time').time(),"sessionId":"debug-session","runId":"run1","hypothesisId":"H1"}) + '\n')
    except Exception:
        pass
    # #endregion
    
    # Pyannote 3.x : appel standard avec gestion d'erreur améliorée
    try:
        pipeline_start = time.time()
        
        # #region agent log
        log_path = os.getenv('DEBUG_LOG_PATH', '/tmp/debug.log')
        debug_msg = {"location":"handler.py:diarize_audio:pipeline_call_start","message":"Appel pipeline() démarré","data":{"timestamp":pipeline_start},"timestamp":__import__('time').time(),"sessionId":"debug-session","runId":"run1","hypothesisId":"H1"}
        print(f"DEBUG LOG: {json.dumps(debug_msg)}", flush=True)
        try:
            with open(log_path, 'a') as f:
                f.write(json.dumps(debug_msg) + '\n')
        except Exception:
            pass
        # #endregion
        
        print("DEBUG: Appel pipeline() - cela peut prendre plusieurs minutes pour un fichier de 21 min...", flush=True)
        if inference_options:
            print(f"Options d'inférence: {inference_options}", flush=True)
            diarization = pipeline(audio_path, **inference_options)
        else:
            diarization = pipeline(audio_path)
        
        pipeline_call_duration = time.time() - pipeline_start
        vram_after_call = torch.cuda.memory_allocated(0) / 1024**3 if torch.cuda.is_available() else 0
        print(f"DEBUG: pipeline() terminé en {pipeline_call_duration:.1f}s - VRAM après: {vram_after_call:.2f} GB", flush=True)
        
        # #region agent log
        log_path = os.getenv('DEBUG_LOG_PATH', '/tmp/debug.log')
        debug_msg = {"location":"handler.py:diarize_audio:pipeline_call_success","message":"Appel pipeline() terminé","data":{"duration":pipeline_call_duration,"vram_after":vram_after_call},"timestamp":__import__('time').time(),"sessionId":"debug-session","runId":"run1","hypothesisId":"H1"}
        print(f"DEBUG LOG: {json.dumps(debug_msg)}", flush=True)
        try:
            with open(log_path, 'a') as f:
                f.write(json.dumps(debug_msg) + '\n')
        except Exception:
            pass
        # #endregion
        
        pipeline_duration = time.time() - pipeline_start
        print(f"Pipeline Pyannote exécuté avec succès en {pipeline_duration:.1f}s", flush=True)
        sys.stdout.flush()
    except Exception as e:
        # #region agent log
        log_path = os.getenv('DEBUG_LOG_PATH', '/tmp/debug.log')
        try:
            with open(log_path, 'a') as f:
                f.write(json.dumps({"location":"handler.py:diarize_audio:pipeline_call_error","message":"Erreur lors de l'appel pipeline()","data":{"error":str(e),"duration":time.time() - pipeline_start},"timestamp":__import__('time').time(),"sessionId":"debug-session","runId":"run1","hypothesisId":"H1"}) + '\n')
        except Exception:
            pass
        # #endregion
        
        error_msg = f"Erreur lors de l'exécution du pipeline Pyannote: {str(e)}"
        print(f"ERROR: {error_msg}", flush=True)
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
        raise Exception(error_msg)
    
    print("Pipeline terminé, formatage des résultats...", flush=True)
    sys.stdout.flush()
    
    if torch.cuda.is_available():
        print(f"VRAM utilisée après: {torch.cuda.memory_allocated(0) / 1024**3:.2f} GB", flush=True)
        sys.stdout.flush()
    
    # Formatage des résultats
    # Pyannote 3.x peut renvoyer des labels différents, on standardise
    segments = []
    print("Formatage des segments...", flush=True)
    sys.stdout.flush()
    
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        segments.append({
            "start": float(turn.start),
            "end": float(turn.end),
            "speaker": str(speaker)
        })
    
    total_duration = time.time() - start_time
    print(f"Diarisation complète terminée en {total_duration:.1f}s, {len(segments)} segments trouvés", flush=True)
    sys.stdout.flush()
    
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
