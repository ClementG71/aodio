# Configuration d'un Volume Railway pour Aodio

## 📦 Pourquoi utiliser un volume Railway ?

Pour les fichiers audio très longs (jusqu'à 4h15), un volume Railway peut offrir :
- **Stockage persistant** : Les fichiers ne sont pas perdus lors des redéploiements
- **Performance I/O** : Potentiellement meilleure que le système de fichiers éphémère
- **Partage entre instances** : Si vous scalez horizontalement (limité avec volumes)

**Note importante** : Les volumes Railway ont une limite de **3000 IOPS** (opérations par seconde), ce qui peut ne pas suffire pour des traitements audio très intensifs. Pour des fichiers de 4h15, le traitement avec `ffmpeg` optimisé devrait rester acceptable.

## 🚀 Configuration du Volume

### Étape 1 : Créer le volume dans Railway

1. Dans votre projet Railway, allez dans **"Volumes"**
2. Cliquez sur **"New Volume"**
3. Configurez :
   - **Name** : `aodio-storage` (ou un nom de votre choix)
   - **Size** : Au moins 20 GB (pour stocker plusieurs fichiers audio longs)
   - **Mount Path** : `/data` (ou `/storage`, selon votre préférence)

### Étape 2 : Configurer le service Flask

1. Dans votre service Flask, allez dans **"Settings"**
2. Dans **"Volumes"**, sélectionnez le volume créé
3. Le volume sera monté au chemin spécifié (ex: `/data`)

### Étape 3 : Modifier le code pour utiliser le volume

Le code détecte automatiquement si un volume Railway est monté via la variable d'environnement `RAILWAY_VOLUME_MOUNT_PATH` ou utilise le chemin par défaut.

**Option A : Utiliser la variable d'environnement**

Dans Railway, ajoutez la variable d'environnement :
```
RAILWAY_VOLUME_MOUNT_PATH=/data
```

**Option B : Modifier directement dans le code**

Modifiez `app.py` pour utiliser le volume :

```python
# Utiliser le volume Railway si disponible, sinon utiliser le dossier local
VOLUME_PATH = os.getenv('RAILWAY_VOLUME_MOUNT_PATH', '/data')
if Path(VOLUME_PATH).exists():
    UPLOAD_FOLDER = str(Path(VOLUME_PATH) / 'uploads')
    PROCESSED_FOLDER = str(Path(VOLUME_PATH) / 'processed')
    LOGS_FOLDER = str(Path(VOLUME_PATH) / 'logs')
else:
    # Fallback sur le système de fichiers local
    UPLOAD_FOLDER = 'uploads'
    PROCESSED_FOLDER = 'processed'
    LOGS_FOLDER = 'logs'
```

## ⚡ Optimisations de Performance

### 1. Optimisation ffmpeg

Le code utilise déjà des optimisations :
- `-threads 0` : Utilise tous les CPU disponibles
- `-loglevel error` : Réduit les logs pour améliorer les performances
- Traitement direct avec ffmpeg (pas de chargement en mémoire)

### 2. Traitement Asynchrone

Le traitement audio est maintenant **asynchrone** :
- L'upload retourne immédiatement
- Le traitement audio se fait en arrière-plan
- Le pipeline complet (diarisation, transcription, LLM) démarre après le traitement audio

### 3. Utilisation du Volume

Pour maximiser les performances avec un volume :
- Stockez les fichiers temporaires sur le volume
- Utilisez le volume uniquement pour les fichiers en cours de traitement
- Nettoyez les fichiers après traitement pour libérer l'espace

## 📊 Performance Attendue

Pour un fichier audio de **4h15** (15 300 secondes) :

- **Sans volume** (système de fichiers éphémère) :
  - Traitement : ~10-20 minutes
  - Risque de perte lors des redéploiements

- **Avec volume Railway** :
  - Traitement : ~10-20 minutes (similaire)
  - Persistance garantie
  - Limitation : 3000 IOPS (peut être un goulot d'étranglement pour des opérations très intensives)

## ⚠️ Limitations des Volumes Railway

1. **IOPS limitées** : 3000 opérations par seconde maximum
2. **Pas de scaling horizontal** : Un volume ne peut être monté que sur un seul service à la fois
3. **Coût** : Les volumes sont facturés selon leur taille

## 🔧 Alternative : Traitement Asynchrone Sans Volume

Si les limitations des volumes sont problématiques, le traitement asynchrone actuel permet déjà :
- ✅ Pas de timeout HTTP (traitement en arrière-plan)
- ✅ Utilisation optimale des CPU avec ffmpeg
- ✅ Pas de blocage de la requête HTTP

Le volume Railway est **optionnel** et principalement utile pour :
- Persistance des fichiers entre redéploiements
- Partage de fichiers entre plusieurs services (si nécessaire)

## 📝 Configuration Recommandée

Pour la plupart des cas d'usage, **le traitement asynchrone actuel est suffisant** sans volume Railway. Le volume est recommandé uniquement si :
- Vous avez besoin de persistance entre redéploiements
- Vous traitez des fichiers très volumineux (>500 MB)
- Vous avez besoin de partager des fichiers entre services

