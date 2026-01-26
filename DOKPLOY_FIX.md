# Corrections pour le déploiement Dokploy

## Problème initial

Le worker RunPod ne pouvait pas accéder aux fichiers audio car les chemins de fichiers n'étaient pas correctement configurés. Les chemins relatifs étaient utilisés, ce qui causait des problèmes d'accès aux fichiers.

## Solution implémentée

### 1. Chemins absolus

Tous les chemins de fichiers utilisent maintenant des chemins absolus basés sur le répertoire racine de l'application. Cela garantit que les fichiers sont toujours accessibles, quel que soit le répertoire de travail actuel.

**Fichiers modifiés** :
- `app.py`
- `routes/main_routes.py`
- `services/runpod_worker.py`

### 2. Détection de l'environnement

L'application détecte automatiquement si elle est exécutée dans un environnement Dokploy en utilisant la variable d'environnement `DOKPLOY_ENV`.

**Code ajouté** :
```python
DOKPLOY_ENV = os.getenv('DOKPLOY_ENV', 'false').lower() == 'true'
```

### 3. URLs publiques

Les URLs publiques pour les fichiers audio sont générées en utilisant `DOKPLOY_PUBLIC_DOMAIN` pour s'assurer que le worker RunPod peut accéder aux fichiers.

**Modifications** :
- Ajout de la variable `DOKPLOY_PUBLIC_DOMAIN`
- Mise à jour de la logique de génération des URLs dans `services/runpod_worker.py`

### 4. Configuration Docker

Le fichier `docker-compose.yml` a été mis à jour pour inclure les variables d'environnement nécessaires pour Dokploy.

**Variables ajoutées** :
- `DOKPLOY_ENV=true`
- `DOKPLOY_PUBLIC_DOMAIN=${DOKPLOY_PUBLIC_DOMAIN}`

## Fichiers modifiés

### app.py

- Ajout de la détection de l'environnement Dokploy
- Utilisation de chemins absolus pour les dossiers
- Configuration des chemins en fonction de l'environnement

### routes/main_routes.py

- Ajout de la détection de l'environnement Dokploy
- Utilisation de chemins absolus pour les dossiers
- Configuration des chemins en fonction de l'environnement

### services/runpod_worker.py

- Mise à jour de la logique de génération des URLs
- Ajout de la prise en charge de `DOKPLOY_PUBLIC_DOMAIN`
- Amélioration de la détection de l'URL de base

### docker-compose.yml

- Ajout des variables d'environnement pour Dokploy
- Configuration des volumes pour les dossiers de fichiers

### DOKPLOY_SETUP.md

- Mise à jour de la documentation pour inclure les nouvelles variables d'environnement
- Ajout d'une section sur la configuration des chemins de fichiers

## Variables d'environnement nécessaires

Pour que l'application fonctionne correctement dans Dokploy, les variables d'environnement suivantes doivent être configurées :

```env
# Clé secrète Flask
SECRET_KEY=votre-cle-secrete-ici

# Configuration Flask
FLASK_DEBUG=False
ALLOWED_ORIGINS=https://votre-domaine.com,https://app.votre-domaine.com

# API Mistral AI (LLM)
MISTRAL_API_KEY=votre-cle-mistral

# RunPod
RUNPOD_API_KEY=votre-cle-runpod
RUNPOD_ENDPOINT_ID=votre-endpoint-id

# Configuration Dokploy
DOKPLOY_ENV=true
DOKPLOY_PUBLIC_DOMAIN=https://votre-domaine.com
```

## Vérification

Pour vérifier que les corrections fonctionnent, vous pouvez :

1. **Tester les chemins** :
   ```bash
   curl https://votre-domaine.com/test-paths
   ```

2. **Tester l'upload** :
   ```bash
   curl -X POST https://votre-domaine.com/upload \
     -H "Content-Type: multipart/form-data" \
     -F "audio_file=@test.wav"
   ```

3. **Vérifier les logs** :
   ```bash
   dokploy logs
   ```

## Résolution du problème

Avec ces corrections, le worker RunPod devrait maintenant pouvoir accéder aux fichiers audio sans problème. Les chemins de fichiers sont correctement configurés et les URLs publiques sont générées avec le bon domaine.

## Prochaines étapes

1. **Déployer les corrections** : Déployez les fichiers modifiés sur Dokploy
2. **Tester le déploiement** : Vérifiez que tout fonctionne correctement
3. **Documenter les corrections** : Mettez à jour la documentation si nécessaire

---

*Dernière mise à jour : 2024-12-15*