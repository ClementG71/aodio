# Guide de configuration rapide

## 1. Configuration locale (développement)

### Créer le fichier `.env.local`

```bash
cp env.example .env.local
```

Puis éditer `.env.local` et remplir les valeurs :

```env
SECRET_KEY=dev-secret-key-change-in-production
ANTHROPIC_API_KEY=sk-ant-api03-...
RUNPOD_API_KEY=...
RUNPOD_ENDPOINT_ID=...
VOXTRAL_API_KEY=...
VOXTRAL_ENDPOINT=https://api.voxtral.com/v1
```

**Note** : Le fichier `.env.local` est dans `.gitignore` et ne sera pas commité.

### Variables nécessaires pour tester localement

- **ANTHROPIC_API_KEY** : OBLIGATOIRE pour le mapping des locuteurs et la génération du pré-CR
- **RUNPOD_API_KEY** et **RUNPOD_ENDPOINT_ID** : OBLIGATOIRES pour la diarisation et transcription
- **SECRET_KEY** : Peut rester en "dev" pour le développement local

### Lancer l'application en local

```bash
# Installer les dépendances
pip install -r requirements.txt

# Lancer l'application
python app.py
```

L'application sera accessible sur `http://localhost:5000`

## 2. Configuration Railway (production)

### Variables d'environnement sur Railway

1. Connecter votre repository GitHub à Railway
2. Dans les paramètres du projet Railway, ajouter les variables d'environnement :

```
SECRET_KEY=<générer-une-clé-sécurisée>
ANTHROPIC_API_KEY=<votre-clé-anthropic>
RUNPOD_API_KEY=<votre-clé-runpod>
RUNPOD_ENDPOINT_ID=<votre-endpoint-id>
VOXTRAL_API_KEY=<votre-clé-voxtral>
VOXTRAL_ENDPOINT=https://api.voxtral.com/v1
```

**Important** : 
- Générer une `SECRET_KEY` sécurisée pour la production (utiliser `secrets.token_hex(32)` en Python)
- Ne jamais commit les clés API dans le code

### Déploiement

Railway détectera automatiquement :
- Le `Procfile` pour le démarrage
- Le `requirements.txt` pour l'installation des dépendances
- Le `railway.json` pour la configuration

## 3. Push vers Git

### Si vous avez un repository distant

```bash
# Ajouter le remote (remplacer par votre URL)
git remote add origin https://github.com/votre-username/aodio.git

# Push vers GitHub
git branch -M main
git push -u origin main
```

### Si vous créez un nouveau repository GitHub

1. Créer un nouveau repository sur GitHub
2. Suivre les instructions GitHub pour connecter un repo existant
3. Push le code :

```bash
git remote add origin https://github.com/votre-username/aodio.git
git branch -M main
git push -u origin main
```

## 4. Workflow recommandé

1. ✅ **Commit et push sur Git** (fait)
2. ✅ **Configurer les variables d'environnement en local** (`.env.local`)
3. ✅ **Tester localement** (`python app.py`)
4. ✅ **Connecter Railway au repository GitHub**
5. ✅ **Configurer les variables d'environnement sur Railway**
6. ✅ **Déployer sur Railway**

## 5. Génération d'une SECRET_KEY sécurisée

Pour générer une clé secrète sécurisée :

```python
import secrets
print(secrets.token_hex(32))
```

Ou en ligne de commande :

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Notes importantes

- ⚠️ **Ne jamais commit `.env` ou `.env.local`** (déjà dans `.gitignore`)
- ⚠️ **Les clés API sont sensibles** - ne les partagez jamais publiquement
- ✅ **Railway peut se connecter directement à GitHub** pour un déploiement automatique
- ✅ **Les variables d'environnement sur Railway** sont sécurisées et chiffrées

