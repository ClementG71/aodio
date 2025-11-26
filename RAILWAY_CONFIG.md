# Configuration Railway - Guide étape par étape

Ce guide vous aide à configurer toutes les variables d'environnement nécessaires sur Railway.

## 📋 Checklist avant de commencer

- [ ] Endpoint RunPod créé et fonctionnel
- [ ] Endpoint ID RunPod noté
- [ ] API Key RunPod récupérée
- [ ] Clé API Anthropic (Claude) obtenue
- [ ] Clé API Mistral AI obtenue

## 🔑 Étape 1 : Récupérer les identifiants RunPod

### 1.1 Endpoint ID

1. Allez sur [https://www.runpod.io/console/serverless](https://www.runpod.io/console/serverless)
2. Cliquez sur votre endpoint `pyannote-diarization`
3. L'**Endpoint ID** est visible :
   - Dans l'URL : `https://www.runpod.io/console/serverless/YOUR_ENDPOINT_ID`
   - Ou dans la section "Endpoint Details" → "Endpoint ID"
4. **Copiez cet ID** (ex: `abc123def456ghi789`)

### 1.2 API Key RunPod

1. Allez sur [https://www.runpod.io/console/user/settings](https://www.runpod.io/console/user/settings)
2. Section "API Keys"
3. Si vous n'avez pas de clé, cliquez sur "Create API Key"
4. Donnez un nom (ex: "aodio-production")
5. **Copiez la clé** (elle commence généralement par `...`)
6. ⚠️ **Important** : Vous ne pourrez plus voir cette clé après, sauvegardez-la !

## 🔑 Étape 2 : Récupérer la clé API Anthropic (Claude)

1. Allez sur [https://console.anthropic.com/](https://console.anthropic.com/)
2. Connectez-vous ou créez un compte
3. Allez dans "API Keys" (menu de gauche)
4. Cliquez sur "Create Key"
5. Donnez un nom (ex: "aodio-claude")
6. **Copiez la clé** (commence par `sk-ant-...`)

## 🔑 Étape 3 : Récupérer la clé API Mistral AI

1. Allez sur [https://console.mistral.ai/](https://console.mistral.ai/)
2. Connectez-vous ou créez un compte
3. Allez dans "API Keys" (menu de gauche ou dans Settings)
4. Cliquez sur "Create API Key"
5. Donnez un nom (ex: "aodio-voxtral")
6. **Copiez la clé** (format: `...`)

## 🔑 Étape 4 : Générer une SECRET_KEY

La SECRET_KEY est utilisée par Flask pour sécuriser les sessions. Générez-en une sécurisée :

### Option A : En ligne de commande (recommandé)

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### Option B : En ligne

Utilisez un générateur en ligne : [https://randomkeygen.com/](https://randomkeygen.com/)
- Choisissez "CodeIgniter Encryption Keys"
- Copiez une des clés générées

## 🚂 Étape 5 : Configurer les variables sur Railway

### 5.1 Accéder aux variables d'environnement

1. Allez sur [https://railway.app/](https://railway.app/)
2. Connectez-vous
3. Sélectionnez votre projet `aodio`
4. Cliquez sur votre service (celui qui héberge l'application Flask)
5. Allez dans l'onglet **"Variables"**

### 5.2 Ajouter chaque variable

Cliquez sur **"New Variable"** et ajoutez les variables suivantes **une par une** :

#### Variable 1 : SECRET_KEY

- **Nom** : `SECRET_KEY`
- **Valeur** : La clé générée à l'étape 4
- Cliquez sur **"Add"**

#### Variable 2 : ANTHROPIC_API_KEY

- **Nom** : `ANTHROPIC_API_KEY`
- **Valeur** : La clé API Anthropic copiée à l'étape 2
- Cliquez sur **"Add"**

#### Variable 3 : RUNPOD_API_KEY

- **Nom** : `RUNPOD_API_KEY`
- **Valeur** : La clé API RunPod copiée à l'étape 1.2
- Cliquez sur **"Add"**

#### Variable 4 : RUNPOD_ENDPOINT_ID

- **Nom** : `RUNPOD_ENDPOINT_ID`
- **Valeur** : L'Endpoint ID copié à l'étape 1.1
- Cliquez sur **"Add"**

#### Variable 5 : MISTRAL_API_KEY

- **Nom** : `MISTRAL_API_KEY`
- **Valeur** : La clé API Mistral AI copiée à l'étape 3
- Cliquez sur **"Add"**

#### Variable 6 : FLASK_DEBUG (recommandé)

- **Nom** : `FLASK_DEBUG`
- **Valeur** : `False` (pour la production)
- **Note** : Contrôle le mode debug de Flask. En production, toujours mettre `False` pour la sécurité. Si non configuré, le mode debug est désactivé par défaut.

#### Variable 7 : ALLOWED_ORIGINS (recommandé pour la sécurité)

- **Nom** : `ALLOWED_ORIGINS`
- **Valeur** : Liste des domaines autorisés pour CORS, séparés par des virgules (ex: `https://votre-app.railway.app,https://www.votre-domaine.com`)
- **Note** : Si vide ou non configuré, tous les domaines sont autorisés (avec avertissement dans les logs). Recommandé en production de limiter aux domaines nécessaires. Pour RunPod, vous pouvez ajouter les domaines RunPod si nécessaire.

#### Variable 8 : RAILWAY_PUBLIC_DOMAIN (optionnel)

- **Nom** : `RAILWAY_PUBLIC_DOMAIN`
- **Valeur** : Railway définit automatiquement cette variable, mais vous pouvez la vérifier
- **Note** : Cette variable est automatiquement définie par Railway. Si vous voulez la forcer, vous pouvez l'ajouter manuellement avec la valeur de votre domaine Railway (ex: `votre-app.railway.app`)

## ✅ Étape 6 : Vérifier la configuration

### 6.1 Vérifier que toutes les variables sont présentes

Dans Railway, dans l'onglet "Variables", vous devriez voir :

```
✅ SECRET_KEY
✅ ANTHROPIC_API_KEY
✅ RUNPOD_API_KEY
✅ RUNPOD_ENDPOINT_ID
✅ MISTRAL_API_KEY
✅ FLASK_DEBUG=False          (recommandé)
✅ ALLOWED_ORIGINS=...        (recommandé)
```

### 6.2 Tester l'application

1. Une fois toutes les variables ajoutées, Railway redéploiera automatiquement
2. Attendez que le déploiement soit terminé (icône verte)
3. Testez la route de santé :
   ```
   https://votre-app.railway.app/health
   ```
4. Vous devriez voir :
   ```json
   {
     "status": "ok",
     "message": "Application Aodio is running"
   }
   ```

### 6.3 Tester l'endpoint RunPod

Pour vérifier que RunPod fonctionne, vous pouvez utiliser le script de test dans `RUNPOD_SETUP.md` (section 5.2) ou tester directement depuis l'application Flask.

## 🔒 Sécurité

### ⚠️ Ne jamais :

- Commiter les clés API dans le code
- Partager les clés API publiquement
- Utiliser les mêmes clés en développement et production

### ✅ Bonnes pratiques :

- Utilisez des clés différentes pour dev/prod
- Régénérez les clés si elles sont compromises
- Limitez les permissions des clés API (si possible)

## 🐛 Dépannage

### L'application ne démarre pas

1. Vérifiez que toutes les variables sont bien configurées
2. Vérifiez les logs Railway (onglet "Deployments" → logs)
3. Testez la route `/health`

### Erreur "MISTRAL_API_KEY doit être fourni"

- Vérifiez que la variable `MISTRAL_API_KEY` est bien configurée sur Railway
- Vérifiez qu'il n'y a pas d'espaces avant/après la valeur

### Erreur "RUNPOD_API_KEY" ou "RUNPOD_ENDPOINT_ID" manquant

- Vérifiez que les deux variables sont configurées
- Vérifiez que l'Endpoint ID est correct (pas l'URL complète, juste l'ID)

### L'endpoint RunPod ne répond pas

1. Vérifiez que l'endpoint est actif sur RunPod
2. Testez l'endpoint directement avec le script de test
3. Vérifiez les logs de l'endpoint RunPod

## 📝 Résumé des variables

| Variable | Où l'obtenir | Format exemple |
|----------|--------------|----------------|
| `SECRET_KEY` | Générée localement | `a1b2c3d4e5f6...` (64 caractères) |
| `ANTHROPIC_API_KEY` | console.anthropic.com | `sk-ant-...` |
| `RUNPOD_API_KEY` | runpod.io/console/user/settings | `...` |
| `RUNPOD_ENDPOINT_ID` | runpod.io/console/serverless | `abc123def456` |
| `MISTRAL_API_KEY` | console.mistral.ai | `...` |
| `FLASK_DEBUG` | Configuration locale | `False` (production) |
| `ALLOWED_ORIGINS` | Configuration locale | `https://app.railway.app,https://www.domaine.com` |

## 🎯 Prochaines étapes

Une fois toutes les variables configurées :

1. ✅ L'application devrait démarrer automatiquement
2. ✅ Testez l'upload d'un fichier audio
3. ✅ Vérifiez que le traitement fonctionne
4. ✅ Consultez les logs pour suivre le traitement

## 📞 Besoin d'aide ?

Si vous rencontrez des problèmes :
1. Consultez `RAILWAY_TROUBLESHOOTING.md` pour le dépannage
2. Vérifiez les logs Railway
3. Vérifiez les logs RunPod (si problème de diarisation)

