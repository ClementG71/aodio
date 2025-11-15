# Configuration du Worker RunPod

Ce guide explique comment configurer le worker RunPod pour la diarisation Pyannote et la transcription Voxtral.

## Prérequis

- Compte RunPod
- Accès à Hugging Face pour télécharger les modèles Pyannote
- Clé API Voxtral (si utilisée directement)

## Configuration du Worker

### 1. Créer un nouveau worker sur RunPod

1. Connectez-vous à votre compte RunPod
2. Créer un nouveau endpoint serverless
3. Sélectionner une image GPU appropriée (recommandé: NVIDIA A100 ou similaire)

### 2. Code du worker

Le code du worker doit implémenter les fonctions suivantes :

- **Diarisation** : Utiliser Pyannote 4.0.1 pour identifier les locuteurs
- **Transcription** : Appeler Voxtral-small-latest pour transcrire chaque segment

Voir `runpod_worker_example.py` pour un exemple de structure.

### 3. Dépendances du worker

Le worker doit installer :

```python
pyannote.audio==4.0.1
torch
torchaudio
requests
```

### 4. Format des requêtes

#### Diarisation

```json
{
  "input": {
    "task": "diarization",
    "audio_url": "https://...",
    "model": "pyannote/speaker-diarization-3.1"
  }
}
```

**Réponse attendue :**
```json
{
  "segments": [
    {
      "start": 0.0,
      "end": 5.2,
      "speaker": "SPEAKER_00"
    },
    ...
  ]
}
```

#### Transcription

```json
{
  "input": {
    "task": "transcription",
    "audio_url": "https://...",
    "segments": [...],
    "model": "voxtral-small-latest",
    "prompt": "...",
    "temperature": 0.0
  }
}
```

**Réponse attendue :**
```json
{
  "transcriptions": [
    {
      "start": 0.0,
      "end": 5.2,
      "speaker": "SPEAKER_00",
      "text": "Transcription du segment..."
    },
    ...
  ]
}
```

### 5. Configuration Hugging Face

Pour utiliser Pyannote, vous devez :

1. Accepter les conditions d'utilisation des modèles sur Hugging Face
2. Créer un token d'accès Hugging Face
3. Configurer le token dans le worker

### 6. Gestion des fichiers audio

Le worker doit pouvoir :
- Télécharger les fichiers audio depuis une URL
- Ou recevoir les fichiers directement dans la requête

**Recommandation** : Utiliser un service de stockage (S3, etc.) pour les fichiers audio et passer l'URL au worker.

### 7. Limites et optimisations

- **Taille des fichiers** : Gérer les fichiers audio de grande taille (jusqu'à 500 MB)
- **Traitement par batch** : Pour les longues réunions, traiter par segments
- **Limite de tokens Voxtral** : Respecter la limite de 100k tokens par appel

### 8. Variables d'environnement du worker

```env
HF_TOKEN=your-huggingface-token
VOXTRAL_API_KEY=your-voxtral-api-key
VOXTRAL_ENDPOINT=https://api.voxtral.com/v1
```

### 9. Test du worker

Une fois le worker déployé, testez-le avec une requête simple :

```python
import requests

response = requests.post(
    "https://api.runpod.io/v2/YOUR_ENDPOINT_ID/run",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    json={
        "input": {
            "task": "diarization",
            "audio_url": "https://example.com/test.wav"
        }
    }
)
```

### 10. Intégration avec l'application Flask

Une fois le worker configuré, mettez à jour les variables d'environnement dans votre application Flask :

```env
RUNPOD_API_KEY=your-runpod-api-key
RUNPOD_ENDPOINT_ID=your-endpoint-id
```

## Dépannage

### Erreur : "Model not found"
- Vérifiez que le token Hugging Face est correctement configuré
- Vérifiez que vous avez accepté les conditions d'utilisation des modèles

### Erreur : "Out of memory"
- Réduisez la taille des batches
- Utilisez un GPU avec plus de mémoire

### Erreur : "API timeout"
- Augmentez le timeout dans la configuration RunPod
- Optimisez le traitement pour réduire le temps d'exécution

