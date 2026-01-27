# Worker RunPod - Pyannote Diarization

Ce dossier contient le code du worker RunPod pour la diarisation avec Pyannote.

## ⚠️ IMPORTANT : Préchargement des modèles

**Les modèles Pyannote doivent être préchargés lors de la construction de l'image Docker** pour éviter les blocages de 30+ minutes lors du téléchargement.

### Construction avec préchargement (RECOMMANDÉ)

```bash
docker build \
  --build-arg HF_TOKEN=votre_token_huggingface \
  -f runpod_worker/Dockerfile.runpod \
  -t votre-image:tag \
  .
```

**Note** : Le `HF_TOKEN` est requis pour accéder aux modèles Pyannote sur Hugging Face. Sans ce token, les modèles seront téléchargés au runtime, ce qui peut causer des blocages.

### Structure

```
runpod_worker/
├── handler.py          # Code principal du worker
├── preload_models.py   # Script de préchargement des modèles
├── requirements.txt    # Dépendances Python
├── Dockerfile.runpod   # Image Docker avec préchargement
└── README.md          # Ce fichier
```

## Déploiement

1. **Construire l'image avec préchargement** :
   ```bash
   docker build --build-arg HF_TOKEN=$HF_TOKEN -f runpod_worker/Dockerfile.runpod -t votre-registry/runpod-worker:latest .
   ```

2. **Pousser l'image** :
   ```bash
   docker push votre-registry/runpod-worker:latest
   ```

3. **Configurer l'endpoint RunPod** avec cette image

4. **Configurer la variable d'environnement `HF_TOKEN`** dans l'endpoint RunPod

## Test local (optionnel)

Pour tester localement avant de déployer :

```bash
# Installer les dépendances
pip install -r requirements.txt

# Configurer le token Hugging Face
export HF_TOKEN=votre-token

# Tester le handler
python handler.py
```

Note: Le test local nécessite un GPU ou sera très lent sur CPU.

