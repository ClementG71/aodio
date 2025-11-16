# Guide complet : Configuration de l'endpoint RunPod pour Pyannote

Ce guide vous explique étape par étape comment créer et configurer un endpoint RunPod pour la diarisation avec Pyannote 4.0.1.

## 📋 Prérequis

1. **Compte RunPod** : Créez un compte sur [https://www.runpod.io](https://www.runpod.io)
2. **Compte Hugging Face** : Créez un compte sur [https://huggingface.co](https://huggingface.co)
3. **Crédits RunPod** : Ajoutez des crédits à votre compte RunPod (minimum $10 recommandé)

## 🔑 Étape 1 : Configuration Hugging Face

### 1.1 Accepter les conditions d'utilisation Pyannote

1. Allez sur [https://huggingface.co/pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
2. Cliquez sur "Agree and access repository"
3. Acceptez les conditions d'utilisation

### 1.2 Créer un token d'accès

1. Allez sur [https://huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
2. Cliquez sur "New token"
3. Donnez un nom (ex: "runpod-pyannote")
4. Sélectionnez le type "Read"
5. Copiez le token généré (vous en aurez besoin plus tard)

## 🚀 Étape 2 : Créer l'endpoint RunPod

### 2.1 Accéder à RunPod

1. Connectez-vous sur [https://www.runpod.io/console](https://www.runpod.io/console)
2. Allez dans l'onglet "Serverless" (menu de gauche)

### 2.2 Créer un nouvel endpoint

1. Cliquez sur "New Endpoint"
2. Vous avez le choix entre 3 options :
   - **Git** : Si vous avez déjà un repository GitHub avec le code
   - **Docker** : Si vous voulez utiliser une image Docker existante
   - **Template** : Templates pré-configurés (non utilisé ici)

#### Option recommandée : Git (si vous avez un repo GitHub)

Si vous avez déjà créé un repository GitHub avec le dossier `runpod_worker/` :

1. **Sélectionnez "Git"**
2. Remplissez :
   - **Nom** : `aodio` (ou `pyannote-diarization`)
   - **GPU Type** : RTX 3090 ou A100 (minimum 16 GB VRAM)
   - **Repository URL** : URL de votre repo GitHub (ex: `https://github.com/ClementG71/aodio`)
   - **Branch** : `main` (ou votre branche)
   - **Dockerfile Path** : `runpod_worker/Dockerfile.runpod` (le Dockerfile pour RunPod est dans le dossier runpod_worker/)
   - **Handler Path** : **LAISSER VIDE** (le Dockerfile gère le chemin via CMD)
   - **Container Disk** : 20 GB
   
   **Note importante** : 
   - Si vous obtenez une erreur `path "/app/.../temp/app/handler.py" not found`, **laissez le Handler Path vide**
   - Le Dockerfile copie `runpod_worker/handler.py` vers `/app/handler.py` dans l'image Docker
   - Le CMD du Dockerfile (`CMD ["python", "handler.py"]`) exécute le handler
   - RunPod utilisera automatiquement le CMD du Dockerfile si le Handler Path est vide

#### Option alternative : Docker (code inline)

Si vous préférez coller le code directement dans RunPod :

1. **Sélectionnez "Docker"**
2. Remplissez :
   - **Nom** : `pyannote-diarization`
   - **GPU Type** : RTX 3090 ou A100 (minimum 16 GB VRAM)
   - **Docker Image** : `runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel`
   - **Container Disk** : 20 GB
   - **Handler Path** : `/app/handler.py` (sera configuré après)

### 2.3 Configurer les variables d'environnement

Dans la section "Environment Variables", ajoutez :

```
HF_TOKEN=votre-token-huggingface-ici
```

Remplacez `votre-token-huggingface-ici` par le token créé à l'étape 1.2.

### 2.4 Note importante

Pour le déploiement du code, vous avez deux options :
- **Option A (Recommandée)** : Utiliser un repository Git (voir étape 4)
- **Option B** : Utiliser le code inline dans l'interface RunPod

Nous recommandons l'Option A car elle est plus maintenable.

## 💻 Étape 3 : Code du worker

### 3.1 Créer le fichier worker

Créez un fichier `handler.py` avec le code suivant :

```python
"""
Worker RunPod pour la diarisation avec Pyannote 4.0.1
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
pipeline = Pipeline.from_pretrained(
    DIARIZATION_MODEL,
    use_auth_token=HF_TOKEN
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
```

### 3.2 Créer le fichier requirements.txt

Créez un fichier `requirements.txt` :

```txt
runpod>=1.0.0
pyannote.audio==4.0.1
torch>=2.2.0
torchaudio>=2.2.0
requests>=2.31.0
```

### 3.3 Créer un Dockerfile (optionnel mais recommandé)

Créez un fichier `Dockerfile` :

```dockerfile
FROM runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel

# Installer les dépendances système
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Copier les fichiers
WORKDIR /app
COPY requirements.txt .
COPY handler.py .

# Installer les dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# Commande de démarrage
CMD ["python", "handler.py"]
```

## 📦 Étape 4 : Déployer le worker

### Option A : Déploiement via GitHub (recommandé)

**Note importante** : Le Dockerfile est configuré pour fonctionner depuis la racine du repo. Si vous utilisez votre repo `aodio` existant, c'est parfait !

1. **Dans RunPod, lors de la création de l'endpoint** :
   - Sélectionnez l'option **"Git"**
   - Remplissez :
     - **Repository URL** : `https://github.com/ClementG71/aodio`
     - **Branch** : `main`
     - **Dockerfile Path** : `runpod_worker/Dockerfile.runpod` (dans le dossier runpod_worker/)
     - **Handler Path** : **LAISSER VIDE**
   - RunPod construira automatiquement l'image Docker

2. **Le Dockerfile est déjà configuré** pour copier les fichiers depuis `runpod_worker/` :
   ```dockerfile
   COPY runpod_worker/requirements.txt ./requirements.txt
   COPY runpod_worker/handler.py ./handler.py
   ```

3. **Si vous préférez créer un repo séparé** (optionnel) :
   - Créez un nouveau repository GitHub
   - Copiez uniquement le contenu du dossier `runpod_worker/` à la racine
   - Dans ce cas, utilisez `Dockerfile` (sans le préfixe `runpod_worker/`)

### Option B : Déploiement via Docker Hub

1. **Construire l'image Docker localement** :
   ```bash
   cd runpod_worker
   docker build -t votre-nom/pyannote-worker:latest .
   docker push votre-nom/pyannote-worker:latest
   ```

2. **Dans RunPod** :
   - Lors de la création, choisissez "Docker"
   - Dans "Docker Image", entrez : `votre-nom/pyannote-worker:latest`
   - Handler path : `/app/handler.py`

### Option C : Déploiement via code inline (plus simple mais moins maintenable)

**Note** : Cette option est utile si vous n'avez pas de repository GitHub ou si vous voulez tester rapidement.

1. **Dans RunPod, lors de la création de l'endpoint** :
   - Choisissez "Docker"
   - Docker Image : `runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel`
   - Créez l'endpoint (vous le configurerez après)
   
2. **Après la création, modifiez l'endpoint** :
   - Allez dans les paramètres de votre endpoint (icône ⚙️)
   - Section "Handler" :
     - Collez le code complet de `runpod_worker/handler.py` dans le champ "Handler Code"
   - Section "Requirements" :
     - Collez le contenu de `runpod_worker/requirements.txt`
   - Section "Docker Command" :
     - Ajoutez cette commande pour installer les dépendances système et Python :
     ```bash
     apt-get update && apt-get install -y ffmpeg libsndfile1 && pip install --no-cache-dir -r /requirements.txt && python /handler.py
     ```
   - **Important** : Dans cette configuration, le handler doit être à la racine `/handler.py` et requirements à `/requirements.txt`

## ✅ Étape 5 : Tester l'endpoint

### 5.1 Récupérer l'ID de l'endpoint

Une fois l'endpoint créé, notez son **Endpoint ID** (visible dans l'URL ou dans les détails de l'endpoint).

### 5.2 Tester avec Python

Créez un fichier `test_runpod.py` :

```python
import requests
import time

# Configuration
RUNPOD_API_KEY = "votre-api-key-runpod"
ENDPOINT_ID = "votre-endpoint-id"
AUDIO_URL = "https://example.com/test-audio.wav"  # URL d'un fichier audio de test

# Préparer la requête
url = f"https://api.runpod.io/v2/{ENDPOINT_ID}/run"
headers = {
    "Authorization": f"Bearer {RUNPOD_API_KEY}",
    "Content-Type": "application/json"
}

payload = {
    "input": {
        "task": "diarization",
        "audio_url": AUDIO_URL
    }
}

# Envoyer la requête
print("Envoi de la requête...")
response = requests.post(url, headers=headers, json=payload)
response.raise_for_status()

job_data = response.json()
job_id = job_data["id"]
print(f"Job créé: {job_id}")

# Attendre la complétion
status_url = f"https://api.runpod.io/v2/{ENDPOINT_ID}/status/{job_id}"
max_wait = 600  # 10 minutes

start_time = time.time()
while time.time() - start_time < max_wait:
    status_response = requests.get(status_url, headers=headers)
    status_response.raise_for_status()
    status_data = status_response.json()
    
    status = status_data.get("status")
    print(f"Status: {status}")
    
    if status == "COMPLETED":
        output = status_data.get("output", {})
        segments = output.get("segments", [])
        print(f"\n✅ Succès! {len(segments)} segments trouvés:")
        for seg in segments[:5]:  # Afficher les 5 premiers
            print(f"  - {seg['speaker']}: {seg['start']:.2f}s - {seg['end']:.2f}s")
        break
    elif status == "FAILED":
        error = status_data.get("error", "Erreur inconnue")
        print(f"\n❌ Échec: {error}")
        break
    
    time.sleep(5)

if time.time() - start_time >= max_wait:
    print("\n⏱️ Timeout: Le job n'a pas terminé dans le délai imparti")
```

### 5.3 Tester avec cURL

```bash
# Créer le job
curl -X POST "https://api.runpod.io/v2/VOTRE_ENDPOINT_ID/run" \
  -H "Authorization: Bearer VOTRE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "task": "diarization",
      "audio_url": "https://example.com/test-audio.wav"
    }
  }'

# Vérifier le status (remplacez JOB_ID)
curl "https://api.runpod.io/v2/VOTRE_ENDPOINT_ID/status/JOB_ID" \
  -H "Authorization: Bearer VOTRE_API_KEY"
```

## 🔧 Étape 6 : Configurer les Warm Workers (Workers toujours actifs)

Par défaut, RunPod Serverless crée les workers à la demande. Pour avoir des workers toujours disponibles (recommandé pour éviter le cold start) :

### 6.1 Accéder aux paramètres de l'endpoint

1. Allez sur [https://www.runpod.io/console/serverless](https://www.runpod.io/console/serverless)
2. Cliquez sur votre endpoint `aodio`
3. Allez dans l'onglet **"Settings"** (ou cliquez sur le bouton "Manage" → "Settings")

### 6.2 Configurer les Warm Workers

1. Dans la section **"Worker Configuration"** ou **"Scaling"** :
   - Trouvez **"Idle Workers"** ou **"Warm Workers"** ou **"Minimum Workers"**
   - Définissez le nombre à **1** (ou plus si vous avez beaucoup de trafic)
   - Cela gardera au moins 1 worker toujours actif

2. **Optionnel - Max Workers** :
   - Définissez **"Max Workers"** à 2-3 pour gérer les pics de charge
   - Cela limite les coûts tout en permettant la scalabilité

3. **Timeout des workers inactifs** :
   - Configurez **"Idle Timeout"** (ex: 5-10 minutes)
   - Les workers inactifs seront arrêtés après ce délai pour économiser

4. Cliquez sur **"Save"** ou **"Update"**

### 6.3 Vérifier que les workers démarrent

1. Après avoir sauvegardé, retournez dans l'onglet **"Workers"**
2. Vous devriez voir un worker en cours de démarrage
3. Attendez 1-2 minutes que le worker soit **"Ready"** (statut vert)
4. Le premier démarrage peut prendre 2-3 minutes (chargement du modèle Pyannote)

### 6.4 Coûts des Warm Workers

- **1 worker RTX 3090** : ~$0.29/heure = ~$7/jour si toujours actif
- **Recommandation** : Gardez 1 warm worker pour éviter le cold start (~2-3 minutes)
- Les workers inactifs coûtent moins cher que les workers actifs

## 🔧 Étape 7 : Configuration dans l'application Flask

Une fois l'endpoint testé et fonctionnel, ajoutez les variables d'environnement sur Railway :

```
RUNPOD_API_KEY=votre-api-key-runpod
RUNPOD_ENDPOINT_ID=votre-endpoint-id
```

Vous pouvez trouver votre API key sur [https://www.runpod.io/console/user/settings](https://www.runpod.io/console/user/settings)

## 📊 Format des requêtes et réponses

### Requête

```json
{
  "input": {
    "task": "diarization",
    "audio_url": "https://example.com/audio.wav"
  }
}
```

### Réponse (succès)

```json
{
  "status": "COMPLETED",
  "output": {
    "segments": [
      {
        "start": 0.0,
        "end": 5.2,
        "speaker": "SPEAKER_00"
      },
      {
        "start": 5.2,
        "end": 12.8,
        "speaker": "SPEAKER_01"
      }
    ]
  }
}
```

### Réponse (erreur)

```json
{
  "status": "FAILED",
  "error": "Description de l'erreur"
}
```

## 🐛 Dépannage

### Erreur : "Model not found" ou "401 Unauthorized"

- Vérifiez que le token Hugging Face (`HF_TOKEN`) est correct
- Vérifiez que vous avez accepté les conditions d'utilisation sur Hugging Face
- Vérifiez que le token a les permissions "Read"

### Erreur : "Out of memory" ou "CUDA out of memory"

- Utilisez un GPU avec plus de VRAM (minimum 16 GB recommandé)
- Réduisez la taille des fichiers audio (normalisez avant l'envoi)

### Erreur : "Timeout"

- Augmentez le timeout dans la configuration RunPod
- Vérifiez que l'URL audio est accessible publiquement
- Les fichiers audio longs (>30 min) peuvent prendre du temps

### Le worker ne démarre pas

- Vérifiez les logs dans RunPod (section "Logs")
- Vérifiez que toutes les dépendances sont installées
- Vérifiez que le Dockerfile est correct

## 💰 Coûts estimés

- **GPU RTX 3090** : ~$0.29/heure
- **GPU A100** : ~$1.79/heure
- **Temps moyen par réunion (1h)** : ~2-5 minutes de traitement
- **Coût par réunion** : ~$0.01-0.15 selon le GPU

## 📝 Notes importantes

1. **Cold Start** : Le premier appel peut prendre 1-2 minutes (chargement du modèle)
2. **Taille des fichiers** : Les fichiers audio doivent être accessibles via URL publique
3. **Format audio** : WAV, MP3, M4A sont supportés (Pyannote gère la conversion)
4. **Limite de durée** : Pas de limite théorique, mais les très longs fichiers (>2h) peuvent être lents

## 🔗 Ressources utiles

- [Documentation RunPod](https://docs.runpod.io/)
- [Documentation Pyannote](https://github.com/pyannote/pyannote-audio)
- [Modèle Pyannote sur Hugging Face](https://huggingface.co/pyannote/speaker-diarization-3.1)
