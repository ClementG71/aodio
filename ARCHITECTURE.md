# Architecture de l'application Aodio

## Vue d'ensemble

L'application utilise une architecture hybride optimisée pour la performance et la simplicité :

```
┌─────────────┐
│   Railway   │  Flask App (Frontend + Orchestration)
│  (Serverless)│
└──────┬──────┘
       │
       ├─────────────────┐
       │                 │
       ▼                 ▼
┌─────────────┐   ┌──────────────┐
│   RunPod    │   │ Mistral AI   │
│  (GPU)      │   │   (API)      │
│             │   │              │
│ Pyannote    │   │ Voxtral      │
│ Diarisation │   │ Transcription│
└─────────────┘   └──────────────┘
       │                 │
       └────────┬────────┘
                │
                ▼
         ┌─────────────┐
         │   Claude    │
         │  (Anthropic)│
         │   LLM       │
         └─────────────┘
```

## Composants

### 1. Railway (Flask Application)
- **Rôle** : Frontend web + Orchestration du pipeline
- **Technologies** : Flask, Tailwind CSS
- **Fonctions** :
  - Upload de fichiers audio et documents contextuels
  - Orchestration du pipeline de traitement
  - Génération de documents (TXT, DOCX, PDF)
  - Interface utilisateur

### 2. RunPod (Worker GPU)
- **Rôle** : Diarisation avec Pyannote
- **Pourquoi RunPod** : Pyannote nécessite un GPU et des modèles lourds
- **Configuration** : Voir `RUNPOD_SETUP.md`
- **Modèle** : `pyannote/speaker-diarization-3.1`

### 3. Mistral AI (API)
- **Rôle** : Transcription audio avec Voxtral
- **Pourquoi API directe** : Plus simple que de déployer vLLM sur RunPod
- **Modèle** : `voxtral-small-latest`
- **Avantages** :
  - Pas de gestion d'infrastructure GPU
  - Pas de configuration vLLM
  - Maintenance simplifiée
  - Scalabilité automatique

### 4. Anthropic (Claude)
- **Rôle** : Traitement LLM (mapping speakers, pré-CR, décisions)
- **Modèle** : `claude-sonnet-4-20250514`
- **Fonctions** :
  - Mapping des locuteurs (SPEAKER_XX → noms réels)
  - Génération du pré-compte rendu
  - Extraction des décisions

## Flux de traitement

1. **Upload** : L'utilisateur upload un fichier audio + documents contextuels
2. **Normalisation audio** : Traitement local avec `pydub` et `librosa`
3. **Diarisation** : Appel à RunPod pour identifier les locuteurs
4. **Transcription** : Appel direct à l'API Mistral AI (Voxtral)
5. **Mapping** : Claude mappe les speakers aux noms réels
6. **Pré-CR** : Claude génère le pré-compte rendu
7. **Décisions** : Claude extrait les décisions depuis les relevés de votes
8. **Génération** : Création des documents finaux (TXT, DOCX, PDF)

## Pourquoi cette architecture ?

### RunPod pour Pyannote uniquement
- Pyannote nécessite vraiment un GPU
- Modèles lourds (~500 MB)
- Nécessite PyTorch et dépendances CUDA

### API Mistral AI pour Voxtral
- **Plus simple** : Pas besoin de configurer vLLM
- **Moins cher** : Pay-per-use au lieu de GPU dédié
- **Plus rapide** : Pas de cold start GPU
- **Maintenance** : Géré par Mistral AI

### Alternative (si besoin)
Si vous préférez tout sur RunPod, vous pouvez :
1. Déployer vLLM sur RunPod
2. Modifier `app.py` pour utiliser `RunPodWorker.transcribe_audio()`
3. Mais cela ajoute de la complexité sans réel avantage

## Variables d'environnement requises

### Railway
- `SECRET_KEY` : Clé secrète Flask
- `ANTHROPIC_API_KEY` : Pour Claude
- `RUNPOD_API_KEY` : Pour Pyannote
- `RUNPOD_ENDPOINT_ID` : ID de l'endpoint RunPod
- `MISTRAL_API_KEY` : Pour Voxtral (obligatoire)

### RunPod Worker
- `HF_TOKEN` : Token Hugging Face pour Pyannote
- Configuration GPU (voir `RUNPOD_SETUP.md`)

## Coûts estimés

- **Railway** : ~$5-20/mois (selon usage)
- **RunPod** : ~$0.20-0.50/heure GPU (pay-per-use)
- **Mistral AI** : ~$0.01-0.05/minute audio (selon modèle)
- **Anthropic** : ~$0.003-0.015/1k tokens (selon modèle)

Pour une réunion de 1h :
- RunPod (diarisation) : ~$0.10-0.20
- Mistral AI (transcription) : ~$0.60-3.00
- Anthropic (traitement) : ~$0.50-2.00
- **Total** : ~$1.20-5.20 par réunion

