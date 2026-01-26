# Guide de déploiement Aodio sur Dokploy

## Prérequis

1. **Compte Dokploy** : Créez un compte sur [https://dokploy.com](https://dokploy.com)
2. **Serveur VPS** : Un serveur avec Docker et Docker Compose installés
3. **Dokploy CLI** : Installé sur votre machine locale
4. **Clés API** : Les mêmes que pour Railway (MISTRAL_API_KEY, RUNPOD_API_KEY, etc.)

## Configuration Dokploy

### 1. Préparer les variables d'environnement

Créez un fichier `.env` à la racine du projet avec les variables suivantes :

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

**Note** : La variable `DOKPLOY_PUBLIC_DOMAIN` est utilisée pour générer les URLs publiques pour les fichiers audio que le worker RunPod doit télécharger.

### 2. Configurer Dokploy

1. **Connectez-vous à Dokploy** :
   ```bash
   dokploy login
   ```

2. **Ajoutez votre serveur** :
   ```bash
   dokploy server add
   ```

3. **Créez une nouvelle application** :
   ```bash
   dokploy app create aodio
   ```

4. **Déployez l'application** :
   ```bash
   dokploy deploy
   ```

### 3. Configuration Docker

Le projet inclut maintenant :

1. **Dockerfile** : Configuration de l'image Docker
2. **docker-compose.yml** : Configuration des services
3. **.dockerignore** : Fichiers à ignorer pour le build

### 4. Configuration spécifique Dokploy

Dokploy utilise les fichiers Docker standard. Aucune configuration spécifique n'est nécessaire au-delà de ce qui est déjà fourni.

### 5. Variables d'environnement dans Dokploy

Dans l'interface Dokploy :

1. Allez dans votre application
2. Onglet "Environment Variables"
3. Ajoutez les variables suivantes :
   - `SECRET_KEY`
   - `MISTRAL_API_KEY`
   - `RUNPOD_API_KEY`
   - `RUNPOD_ENDPOINT_ID`
   - `FLASK_DEBUG=False`
   - `ALLOWED_ORIGINS=votre-domaine.com`
   - `DOKPLOY_ENV=true`
   - `DOKPLOY_PUBLIC_DOMAIN=https://votre-domaine.com`

### 6. Configuration des chemins de fichiers

L'application utilise maintenant des chemins absolus pour les fichiers. Cela est nécessaire pour que le worker RunPod puisse accéder aux fichiers audio.

**Modifications apportées** :

1. **Chemins absolus** : Tous les chemins de fichiers utilisent maintenant des chemins absolus basés sur le répertoire racine de l'application.

2. **Détection de l'environnement** : L'application détecte automatiquement si elle est exécutée dans un environnement Dokploy et configure les chemins en conséquence.

3. **URLs publiques** : Les URLs publiques pour les fichiers audio sont générées en utilisant `DOKPLOY_PUBLIC_DOMAIN` pour s'assurer que le worker RunPod peut accéder aux fichiers.

**Structure des dossiers** :

```
/
├── app/
│   ├── uploads/      # Fichiers audio uploadés
│   ├── processed/    # Documents générés
│   └── logs/         # Logs de traitement
├── Dockerfile
├── docker-compose.yml
└── .env
```

**Permissions** :

Assurez-vous que les dossiers ont les permissions correctes :

```bash
chmod -R 755 uploads processed logs
```

**Vérification** :

Pour vérifier que les chemins sont correctement configurés, vous pouvez ajouter un endpoint de test :

```python
@app.route('/test-paths')
def test_paths():
    return jsonify({
        'UPLOAD_FOLDER': UPLOAD_FOLDER,
        'PROCESSED_FOLDER': PROCESSED_FOLDER,
        'LOGS_FOLDER': LOGS_FOLDER,
        'DOKPLOY_ENV': DOKPLOY_ENV
    })
```

Puis testez avec :

```bash
curl https://votre-domaine.com/test-paths
```

### 6. Configuration du domaine

1. **Ajoutez un domaine personnalisé** :
   ```bash
   dokploy domain add votre-domaine.com
   ```

2. **Configurez le SSL** :
   ```bash
   dokploy ssl enable
   ```

### 7. Configuration des volumes (optionnel)

Si vous souhaitez utiliser des volumes persistants pour les fichiers uploadés :

1. Créez un volume Docker :
   ```bash
   docker volume create aodio-uploads
   docker volume create aodio-processed
   docker volume create aodio-logs
   ```

2. Modifiez le `docker-compose.yml` pour utiliser les volumes :
   ```yaml
   volumes:
     - aodio-uploads:/app/uploads
     - aodio-processed:/app/processed
     - aodio-logs:/app/logs
   ```

## Vérification du déploiement

### 1. Vérifier les logs

```bash
# Voir les logs de l'application
dokploy logs

# Ou directement avec Docker
docker logs aodio-web
```

### 2. Tester l'application

```bash
# Tester la route de santé
curl https://votre-domaine.com/health

# Devrait retourner
# {"status":"ok","message":"Application Aodio is running"}
```

### 3. Tester un upload

```bash
# Tester un upload de fichier
curl -X POST https://votre-domaine.com/upload \
  -H "Content-Type: multipart/form-data" \
  -F "audio_file=@test.wav"
```

## Dépannage

### Problème : L'application ne démarre pas

1. Vérifiez les logs :
   ```bash
   dokploy logs
   ```

2. Vérifiez que toutes les variables d'environnement sont configurées

3. Vérifiez que les ports sont correctement exposés

### Problème : Erreur de connexion à la base de données

L'application n'utilise pas de base de données, donc ce problème ne devrait pas se produire.

### Problème : Erreur de permission sur les fichiers

1. Vérifiez les permissions des dossiers :
   ```bash
   chmod -R 755 uploads processed logs
   ```

2. Vérifiez que l'utilisateur Docker a les permissions nécessaires

### Problème : Timeout lors du traitement

1. Augmentez le timeout dans le `docker-compose.yml` :
   ```yaml
   command: gunicorn -w 4 -b 0.0.0.0:5000 --timeout 3600 --graceful-timeout 180 wsgi:app
   ```

2. Vérifiez que le serveur a suffisamment de ressources

## Migration depuis Railway

### Différences clés

| Fonctionnalité | Railway | Dokploy |
|---------------|---------|---------|
| Configuration | `railway.json` | `docker-compose.yml` |
| Déploiement | Automatique Git | Docker + CLI |
| Variables | Interface Railway | Interface Dokploy |
| Scaling | Automatique | Manuel |
| Volumes | Intégrés | Docker Volumes |

### Étapes de migration

1. **Exportez les variables d'environnement** depuis Railway
2. **Créez le fichier `.env`** pour Dokploy
3. **Déployez avec Dokploy**
4. **Testez l'application**
5. **Mettez à jour le DNS** pour pointer vers Dokploy

## Bonnes pratiques

1. **Sauvegardez vos données** avant la migration
2. **Testez en environnement de staging** avant la production
3. **Surveillez les logs** après le déploiement
4. **Configurez des alertes** pour les erreurs

## Support

Pour toute question ou problème :
- Consultez la [documentation Dokploy](https://docs.dokploy.com)
- Contactez le support Dokploy
- Vérifiez les logs de l'application

## Annexes

### Commandes utiles Dokploy

```bash
# Lister les applications
dokploy apps list

# Voir les logs
dokploy logs

# Redémarrer l'application
dokploy restart

# Mettre à jour l'application
dokploy update

# Supprimer l'application
dokploy app delete
```

### Commandes Docker utiles

```bash
# Lister les conteneurs
docker ps

# Voir les logs d'un conteneur
docker logs aodio-web

# Redémarrer un conteneur
docker restart aodio-web

# Supprimer un conteneur
docker rm aodio-web

# Lister les volumes
docker volume ls
```

---

*Dernière mise à jour : 2024-12-15*