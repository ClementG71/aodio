# Compatibilité Dokploy - Partie sans RunPod

## Résumé des vérifications

L'application a été vérifiée et adaptée pour fonctionner correctement sur Dokploy **sans RunPod** (utilisant uniquement Mistral pour la transcription).

## Corrections apportées

### 1. Configuration des URLs publiques

**Problème identifié :** Les URLs publiques pour Mistral ne vérifiaient pas `DOKPLOY_PUBLIC_DOMAIN` en priorité.

**Correction :** 
- `services/mistral_voxtral.py` : Méthode `_get_audio_url()` vérifie maintenant `DOKPLOY_PUBLIC_DOMAIN` en premier
- `routes/main_routes.py` : `app_base_url` vérifie maintenant `DOKPLOY_PUBLIC_DOMAIN` en priorité

**Ordre de priorité :**
1. `DOKPLOY_PUBLIC_DOMAIN` (pour Dokploy)
2. `RAILWAY_PUBLIC_DOMAIN` (pour Railway)
3. `APP_BASE_URL` (fallback)
4. `http://localhost:5000` (développement local)

### 2. Chemins de fichiers

**Problème identifié :** Utilisation de `Path(app.root_path).parent` qui peut être incorrect dans Dokploy.

**Correction :**
- Utilisation directe de `UPLOAD_FOLDER` depuis `config.py` (déjà en chemin absolu)
- Tous les chemins utilisent maintenant les variables de `config.py` qui sont déjà configurées pour Dokploy

**Fichiers modifiés :**
- `routes/main_routes.py` : Routes `/files/`, `/upload`, `/download`

### 3. Configuration centralisée

**Amélioration :** 
- Tous les chemins sont maintenant centralisés dans `config.py`
- Détection automatique de l'environnement Dokploy via `DOKPLOY_ENV=true`
- Chemins absolus utilisés automatiquement en mode Dokploy

## Fonctionnement sans RunPod

### Services requis

Pour fonctionner **sans RunPod**, l'application nécessite uniquement :

1. **Mistral API** (`MISTRAL_API_KEY`) - ✅ Requis
2. **RunPod** (`RUNPOD_API_KEY`, `RUNPOD_ENDPOINT_ID`) - ❌ Optionnel

### Comportement sans RunPod

Si RunPod n'est pas configuré :
- ✅ L'application démarre normalement
- ✅ Les uploads fonctionnent
- ✅ La transcription avec Mistral fonctionne
- ⚠️ La diarisation n'est pas disponible (pas de séparation des locuteurs)
- ⚠️ Le pipeline complet ne peut pas s'exécuter (nécessite diarisation)

### Mode de fonctionnement sans RunPod

L'application peut fonctionner en mode **transcription simple** :
- Upload audio → Traitement audio → Transcription Mistral → Génération documents
- **Sans** identification des locuteurs (pas de diarisation)
- **Sans** mapping SPEAKER_XX → noms réels

## Configuration Dokploy requise

### Variables d'environnement minimales (sans RunPod)

```bash
# Configuration Dokploy
DOKPLOY_ENV=true
DOKPLOY_PUBLIC_DOMAIN=https://votre-domaine.com

# Application
SECRET_KEY=votre-secret-key
FLASK_DEBUG=False

# Mistral (requis)
MISTRAL_API_KEY=votre-cle-mistral

# RunPod (optionnel - laisser vide si non utilisé)
# RUNPOD_API_KEY=
# RUNPOD_ENDPOINT_ID=

# CORS (recommandé)
ALLOWED_ORIGINS=https://votre-domaine.com
```

### Volumes Docker

Dokploy gère automatiquement la persistance des volumes. Les dossiers suivants sont créés dans le conteneur :
- `/app/uploads` - Fichiers audio uploadés
- `/app/processed` - Documents générés
- `/app/logs` - Logs de l'application

**Note :** Pour une persistance permanente, configurez un volume Docker dans Dokploy pour ces dossiers.

## Points d'attention

### 1. Port

Le Dockerfile expose le port 5000. Dokploy gère le reverse proxy automatiquement, donc pas de modification nécessaire.

### 2. Timeout

Le timeout Gunicorn est configuré à 1800 secondes (30 minutes) pour gérer les longs traitements audio. C'est adapté pour Dokploy.

### 3. Workers

4 workers Gunicorn par défaut. Ajustez selon les ressources de votre VPS :
- VPS avec 2 CPU : `-w 2`
- VPS avec 4+ CPU : `-w 4` (défaut)

### 4. Mémoire

L'application charge Spacy en mémoire (~150 MB). Avec 4 workers, prévoyez au moins 1 GB de RAM disponible.

## Tests recommandés

### 1. Test de santé

```bash
curl https://votre-domaine.com/health
```

Doit retourner :
```json
{
  "status": "ok",
  "services": {
    "mistral_available": true,
    "runpod_available": false
  }
}
```

### 2. Test d'upload (sans RunPod)

L'upload devrait fonctionner, mais le traitement complet échouera si RunPod n'est pas configuré. Vérifiez les logs pour confirmer.

### 3. Vérification des chemins

```bash
# Dans Dokploy, vérifier les logs au démarrage
# Doit afficher les chemins configurés
```

## Limitations sans RunPod

1. **Pas de diarisation** : Impossible de séparer les locuteurs
2. **Pas de mapping speakers** : Les noms des locuteurs ne peuvent pas être identifiés
3. **Transcription simple uniquement** : Transcription brute sans attribution aux locuteurs
4. **Documents limités** : Les documents générés n'auront pas d'attribution de locuteurs

## Recommandations

Pour une utilisation complète, il est recommandé de :
1. Configurer RunPod pour la diarisation
2. OU utiliser une alternative locale pour la diarisation (si disponible)

Pour une utilisation minimale (transcription simple), l'application fonctionne sans RunPod.
