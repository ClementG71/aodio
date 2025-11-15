# Dépannage Railway - Build Failed

## Comment voir les logs détaillés

Si vous voyez "No logs yet..." dans l'interface Railway :

1. **Cliquez sur l'icône de téléchargement** (📥) à côté de "Build Logs" pour télécharger les logs
2. **Ou utilisez la CLI Railway** :
   ```bash
   railway logs
   ```
3. **Ou dans l'interface web** :
   - Allez dans "Deployments" → Cliquez sur le déploiement qui a échoué
   - Les logs détaillés devraient apparaître

## Problèmes courants et solutions

### 1. Erreur : "Module not found" ou "Import error"

**Cause** : Dépendances manquantes ou problème d'import

**Solution** :
- Vérifiez que `requirements.txt` contient toutes les dépendances
- Vérifiez que tous les fichiers dans `services/` existent
- Vérifiez que `templates/` contient tous les fichiers HTML

### 2. Erreur : "Port already in use" ou "Address already in use"

**Cause** : Le port $PORT n'est pas correctement configuré

**Solution** :
- Vérifiez que le `Procfile` utilise `$PORT` (Railway l'injecte automatiquement)
- Vérifiez que `railway.json` utilise `$PORT` dans startCommand

### 3. Erreur : "Permission denied" pour les dossiers

**Cause** : Railway ne peut pas créer les dossiers `uploads/`, `processed/`, `logs/`

**Solution** :
- Le code crée automatiquement ces dossiers avec `Path().mkdir(exist_ok=True)`
- Si le problème persiste, vérifiez les permissions dans Railway

### 4. Erreur : "Environment variable not set"

**Cause** : Variables d'environnement manquantes

**Solution** :
- Vérifiez que toutes les variables sont configurées dans Railway :
  - `SECRET_KEY`
  - `ANTHROPIC_API_KEY`
  - `RUNPOD_API_KEY`
  - `RUNPOD_ENDPOINT_ID`
  - `MISTRAL_API_KEY`

**Note** : L'application peut démarrer sans ces variables, mais elles sont nécessaires pour utiliser les fonctionnalités.

### 5. Erreur : "Build timeout"

**Cause** : Le build prend trop de temps

**Solution** :
- Vérifiez que `requirements.txt` n'inclut pas PyTorch/Pyannote (utilisez `requirements-worker.txt` pour RunPod)
- Le build devrait prendre 2-3 minutes maximum

### 6. Erreur : "Application failed to start"

**Cause** : L'application crash au démarrage

**Solution** :
- Vérifiez les logs pour voir l'erreur exacte
- Testez localement : `python app.py`
- Vérifiez que tous les imports fonctionnent

## Vérification rapide

### 1. Tester l'import de l'application

```bash
python -c "from app import app; print('OK')"
```

### 2. Tester le démarrage

```bash
python app.py
```

L'application devrait démarrer sur `http://localhost:5000`

### 3. Tester la route de santé

Une fois déployé, testez :
```
https://votre-app.railway.app/health
```

Vous devriez voir :
```json
{
  "status": "ok",
  "message": "Application Aodio is running"
}
```

## Checklist de déploiement

- [ ] Tous les fichiers sont commités et poussés sur GitHub
- [ ] Le repository est connecté à Railway
- [ ] Les variables d'environnement sont configurées dans Railway
- [ ] Le `Procfile` existe et est correct
- [ ] Le `railway.json` existe (optionnel mais recommandé)
- [ ] Le build passe sans erreur
- [ ] L'application démarre (vérifier avec `/health`)
- [ ] Les routes principales fonctionnent

## Obtenir de l'aide

Si le problème persiste :

1. **Téléchargez les logs complets** depuis Railway
2. **Vérifiez les logs de build** (section "Build Logs")
3. **Vérifiez les logs de runtime** (section "Deploy Logs")
4. **Partagez les logs** pour diagnostic

## Commandes utiles Railway CLI

```bash
# Installer Railway CLI
npm i -g @railway/cli

# Se connecter
railway login

# Voir les logs
railway logs

# Voir les variables d'environnement
railway variables

# Redémarrer le service
railway restart
```

