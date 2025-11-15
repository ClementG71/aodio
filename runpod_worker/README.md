# Worker RunPod - Pyannote Diarization

Ce dossier contient le code du worker RunPod pour la diarisation avec Pyannote.

## Structure

```
runpod_worker/
├── handler.py          # Code principal du worker
├── requirements.txt    # Dépendances Python
├── Dockerfile         # Image Docker (optionnel)
└── README.md          # Ce fichier
```

## Déploiement

Voir `../RUNPOD_SETUP.md` pour les instructions complètes de déploiement.

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

