"""
Script pour précharger les modèles Pyannote dans le Dockerfile
Évite le téléchargement à chaque exécution du worker
"""
import os
import sys

# Le token Hugging Face doit être passé en argument ou variable d'environnement
HF_TOKEN = os.getenv('HF_TOKEN') or (sys.argv[1] if len(sys.argv) > 1 else None)

if not HF_TOKEN:
    print("ERROR: HF_TOKEN requis pour précharger les modèles")
    print("Usage: python preload_models.py <HF_TOKEN>")
    sys.exit(1)

# Configurer le token
os.environ['HF_TOKEN'] = HF_TOKEN
os.environ['HUGGING_FACE_HUB_TOKEN'] = HF_TOKEN

try:
    from huggingface_hub import login
    from pyannote.audio import Pipeline
    import torch
    
    print("Authentification Hugging Face...")
    login(token=HF_TOKEN, add_to_git_credential=False)
    print("Authentification réussie")
    
    print("Préchargement du modèle Pyannote speaker-diarization-3.1...")
    print("Cela peut prendre plusieurs minutes lors de la première construction...")
    
    # Fix pour PyTorch 2.6+ : autoriser les classes Pyannote dans torch.load()
    import torch.torch_version
    from pyannote.audio.core.task import Specifications, Problem, Resolution
    torch.serialization.add_safe_globals([
        torch.torch_version.TorchVersion,
        Specifications,
        Problem,
        Resolution,
    ])
    
    # Précharger le pipeline (télécharge tous les modèles dans le cache Hugging Face)
    # H3: Vérifier que le préchargement fonctionne
    from huggingface_hub.utils import HfFolder
    cache_dir_before = HfFolder.get_cache_dir()
    print(f"Cache Hugging Face avant: {cache_dir_before}")
    
    pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1")
    
    cache_dir_after = HfFolder.get_cache_dir()
    model_cache_path = os.path.join(cache_dir_after, 'hub', 'models--pyannote--speaker-diarization-3.1')
    
    print("Modèle préchargé avec succès!")
    print(f"Cache Hugging Face: {cache_dir_after}")
    print(f"Chemin du modèle: {model_cache_path}")
    print(f"Modèle existe: {os.path.exists(model_cache_path)}")
    
    # H3: Lister les fichiers du cache pour vérifier
    if os.path.exists(model_cache_path):
        print(f"Fichiers dans le cache:")
        for root, dirs, files in os.walk(model_cache_path):
            level = root.replace(model_cache_path, '').count(os.sep)
            indent = ' ' * 2 * level
            print(f"{indent}{os.path.basename(root)}/")
            subindent = ' ' * 2 * (level + 1)
            for file in files[:5]:  # Limiter à 5 fichiers par répertoire
                print(f"{subindent}{file}")
            if len(files) > 5:
                print(f"{subindent}... et {len(files) - 5} autres fichiers")
    
    # Vérifier que le pipeline est bien chargé
    print(f"Type du pipeline: {type(pipeline)}")
    
except Exception as e:
    print(f"ERROR: Erreur lors du préchargement: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
