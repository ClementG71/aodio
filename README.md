# Aodio

Application de transcription audio et préparation de comptes rendus de réunions pour le Conseil de la Formation et Vie Étudiante d'une université.

## Fonctionnalités

- **Upload et traitement audio** : Normalisation et compression des fichiers audio
- **Diarisation** : Identification des locuteurs avec Pyannote 4.0.1
- **Transcription** : Transcription verbatim avec Voxtral-small-latest
- **Traitement LLM** : Mapping des locuteurs, génération de pré-compte rendu, extraction des décisions avec Mistral AI
- **Génération de documents** : Création de documents en formats TXT, DOCX et PDF
- **Historique** : Suivi de tous les traitements effectués
- **Interface web** : Interface Flask avec Tailwind CSS

## Stack technique

- **Frontend** : Flask avec Tailwind CSS (hébergé sur Railway)
- **Traitement audio** : Pyannote 4.0.1 (via RunPod) et Voxtral-small-latest
- **LLM** : Mistral AI (Mistral Small et Large)
- **Génération de documents** : python-docx, reportlab

## Installation

### Prérequis

- Python 3.9+
- FFmpeg (pour le traitement audio)
- Clés API :
  - Mistral AI (LLM)
  - RunPod
  - Voxtral (si utilisé directement)

### Installation locale

1. Cloner le repository :
```bash
git clone <repository-url>
cd aodio
```

2. Créer un environnement virtuel :
```bash
python -m venv venv
source venv/bin/activate  # Sur Windows: venv\Scripts\activate
```

3. Installer les dépendances :
```bash
# Pour l'application Flask (Railway)
pip install -r requirements.txt

# Pour le worker RunPod (si vous développez le worker)
pip install -r requirements-worker.txt
```

**Note** : `requirements.txt` est optimisé pour Railway (sans PyTorch/Pyannote, ~500 MB). `requirements-worker.txt` contient toutes les dépendances nécessaires pour le worker RunPod (~3.5 GB avec PyTorch).

4. Configurer les variables d'environnement :
```bash
cp .env.example .env
# Éditer .env et ajouter vos clés API
```

5. Lancer l'application :
```bash
python app.py
```

L'application sera accessible sur `http://localhost:5000`

## Configuration

### Variables d'environnement

Créer un fichier `.env` avec les variables suivantes :

```env
SECRET_KEY=your-secret-key-here
MISTRAL_API_KEY=your-mistral-api-key
RUNPOD_API_KEY=your-runpod-api-key
RUNPOD_ENDPOINT_ID=your-runpod-endpoint-id
MISTRAL_API_KEY=your-mistral-api-key
```

**Note** : `MISTRAL_ENDPOINT` n'est pas nécessaire (valeur par défaut utilisée).

### Architecture

L'application utilise une architecture hybride optimisée :

- **Pyannote (Diarisation)** : Exécuté sur RunPod (nécessite GPU)
  - Le worker RunPod doit être configuré pour exécuter Pyannote 4.0.1
  - Voir `RUNPOD_SETUP.md` pour la configuration du worker

- **Voxtral (Transcription)** : Appel direct à l'API Mistral AI
  - Pas besoin de vLLM sur RunPod
  - Utilise l'API officielle Mistral AI (`voxtral-small-latest`)
  - Plus simple à maintenir et à déployer

### Déploiement sur Railway

1. Créer un nouveau projet sur Railway
2. Connecter le repository GitHub
3. Ajouter les variables d'environnement dans les paramètres du projet
4. Railway détectera automatiquement le `Procfile` et déploiera l'application

### Déploiement sur Dokploy

1. **Prérequis** :
   - Compte Dokploy
   - Serveur VPS avec Docker et Docker Compose
   - Clés API (MISTRAL_API_KEY, RUNPOD_API_KEY, etc.)

2. **Configuration** :
   - Copier `.env.example` en `.env` et configurer les variables
   - Ajouter les variables spécifiques à Dokploy :
     ```env
     DOKPLOY_ENV=true
     DOKPLOY_PUBLIC_DOMAIN=https://votre-domaine.com
     ```

3. **Déploiement** :
   - Suivre les instructions dans `DOKPLOY_SETUP.md`
   - Déployer avec `dokploy deploy`

4. **Vérification** :
   - Tester la route de santé : `curl https://votre-domaine.com/health`
   - Vérifier les logs : `dokploy logs`

Pour plus de détails, voir `DOKPLOY_SETUP.md` et `DOKPLOY_FIX.md`.

## Utilisation

### Workflow de traitement

1. **Upload** : Uploader le fichier audio et les documents contextuels (ordre du jour, liste des participants, relevés de votes)
2. **Traitement** : L'application effectue automatiquement :
   - Normalisation et compression de l'audio
   - Diarisation avec Pyannote
   - Transcription avec Voxtral
   - Mapping des locuteurs avec Mistral AI
   - Génération du pré-compte rendu
   - Extraction des décisions
3. **Téléchargement** : Télécharger les documents générés (Minutes, Pré-CR, Relevé des décisions)

### Formats de documents générés

Tous les documents sont préfixés par la date de la séance au format `YYYYMMDD` :

- `YYYYMMDD_Minutes.txt/docx/pdf` : Transcription verbatim avec mapping des locuteurs
- `YYYYMMDD_Pre-Compte-rendu.txt/docx/pdf` : Pré-compte rendu condensé et reformulé
- `YYYYMMDD_Releve-des-decisions.txt/docx/pdf` : Liste des décisions extraites

## Structure du projet

```
aodio/
├── app.py                 # Application Flask principale
├── requirements.txt       # Dépendances Python (Railway - sans PyTorch)
├── requirements-worker.txt  # Dépendances pour le worker RunPod (avec PyTorch)
├── Procfile              # Configuration Railway
├── railway.json          # Configuration Railway
├── services/            # Services de traitement
│   ├── audio_processor.py
│   ├── runpod_worker.py
│   ├── llm_processor.py
│   ├── document_generator.py
│   └── log_manager.py
├── templates/            # Templates HTML
│   ├── base.html
│   ├── index.html
│   ├── history.html
│   └── confidentialite.html
├── uploads/             # Fichiers uploadés (créé automatiquement)
├── processed/           # Documents générés (créé automatiquement)
└── logs/                # Logs de traitement (créé automatiquement)
```

## Limitations et optimisations

- **Limite de tokens** : Les appels API sont limités pour éviter la surcharge (100k tokens par appel pour Voxtral, 4k tokens pour Mistral Small, 8k tokens pour Mistral Large)
- **Traitement par batch** : La transcription est effectuée par batches de segments pour optimiser les appels API
- **Taille de fichier** : Limite de 500 MB par fichier audio

## Développement

### Tests locaux

Pour tester localement sans RunPod, vous pouvez modifier `services/runpod_worker.py` pour utiliser des mocks ou des services locaux.

### Améliorations futures

- Utilisation d'embeddings vocaux pour améliorer le mapping des locuteurs
- Traitement asynchrone avec Celery
- Interface de gestion des sessions
- Export vers d'autres formats

## Licence

[À définir]

## Contact

Pour toute question ou problème, contactez : contact@aodio.fr

