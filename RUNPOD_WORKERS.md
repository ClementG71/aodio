# Configuration des Workers RunPod - Guide rapide

## 🎯 Problème : "No workers available"

C'est **normal** ! Sur RunPod Serverless, les workers sont créés à la demande par défaut.

## ✅ Solution : Configurer des Warm Workers

### Option 1 : Via l'interface web (recommandé)

1. **Allez sur votre endpoint** :
   - [https://www.runpod.io/console/serverless](https://www.runpod.io/console/serverless)
   - Cliquez sur votre endpoint `aodio`

2. **Onglet "Settings"** :
   - Cliquez sur **"Settings"** ou **"Manage"** → **"Settings"**

3. **Section "Worker Configuration"** :
   - Cherchez **"Idle Workers"** ou **"Warm Workers"** ou **"Minimum Workers"**
   - Mettez la valeur à **1**
   - Cela gardera 1 worker toujours actif

4. **Sauvegardez** :
   - Cliquez sur **"Save"** ou **"Update"**

5. **Vérifiez** :
   - Retournez dans l'onglet **"Workers"**
   - Vous devriez voir un worker démarrer dans 1-2 minutes

### Option 2 : Via l'API RunPod

Si l'interface ne propose pas cette option, vous pouvez utiliser l'API :

```python
import requests

RUNPOD_API_KEY = "votre-api-key"
ENDPOINT_ID = "votre-endpoint-id"

url = f"https://api.runpod.io/v2/{ENDPOINT_ID}/update"
headers = {
    "Authorization": f"Bearer {RUNPOD_API_KEY}",
    "Content-Type": "application/json"
}

# Configurer 1 warm worker
payload = {
    "templateId": "votre-template-id",  # Trouvable dans les détails de l'endpoint
    "gpuIds": "AMPERE_16",  # Type de GPU
    "networkVolumeId": "votre-volume-id",  # Optionnel
    "containerDiskSizeGb": 20,
    "env": [
        {"key": "HF_TOKEN", "value": "votre-token"}
    ],
    "scalingConfig": {
        "minWorkers": 1,  # ← C'est ici qu'on configure les warm workers
        "maxWorkers": 3
    }
}

response = requests.put(url, headers=headers, json=payload)
print(response.json())
```

## 📊 Comportement des Workers

### Sans Warm Workers (par défaut)
- ❌ **Cold Start** : 2-3 minutes au premier appel (chargement du modèle)
- ✅ **Coût** : Pay-per-use uniquement
- ⚠️ **Délai** : Chaque requête attend le démarrage du worker

### Avec Warm Workers (recommandé)
- ✅ **Pas de Cold Start** : Worker toujours prêt
- ✅ **Réponse rapide** : < 30 secondes pour la diarisation
- ⚠️ **Coût** : ~$7/jour pour 1 worker RTX 3090 toujours actif

## 💰 Optimisation des coûts

### Stratégie recommandée

1. **En développement/test** :
   - 0 warm workers (pay-per-use uniquement)
   - Acceptez le cold start pour économiser

2. **En production** :
   - 1 warm worker minimum
   - Max 2-3 workers pour gérer les pics
   - Idle timeout : 5-10 minutes

### Calcul des coûts

**Avec 1 warm worker RTX 3090** :
- Coût/heure : ~$0.29
- Coût/jour (24h) : ~$7
- Coût/mois : ~$210

**Sans warm worker (pay-per-use)** :
- Coût par réunion (1h audio, ~5 min traitement) : ~$0.02-0.05
- Si 10 réunions/mois : ~$0.20-0.50
- **Beaucoup moins cher** mais avec cold start

## 🔍 Vérifier l'état des workers

### Dans l'interface RunPod

1. Onglet **"Workers"** :
   - Vous devriez voir la liste des workers
   - Statut : **"Ready"** (vert) = prêt à traiter
   - Statut : **"Starting"** (orange) = en cours de démarrage
   - Statut : **"Idle"** (gris) = inactif mais disponible

### Via l'API

```python
import requests

RUNPOD_API_KEY = "votre-api-key"
ENDPOINT_ID = "votre-endpoint-id"

url = f"https://api.runpod.io/v2/{ENDPOINT_ID}/health"
headers = {"Authorization": f"Bearer {RUNPOD_API_KEY}"}

response = requests.get(url, headers=headers)
print(response.json())
# Devrait retourner le nombre de workers disponibles
```

## 🐛 Dépannage

### Les workers ne démarrent pas

1. **Vérifiez les logs** :
   - Onglet "Logs" de votre endpoint
   - Cherchez les erreurs de build ou de démarrage

2. **Vérifiez la configuration** :
   - Variables d'environnement (HF_TOKEN)
   - GPU Type disponible
   - Crédits RunPod suffisants

3. **Vérifiez le build** :
   - Onglet "Builds" → Vérifiez que le dernier build a réussi

### Les workers démarrent mais crash

1. **Vérifiez les logs du worker** :
   - Cliquez sur un worker dans l'onglet "Workers"
   - Consultez les logs pour voir l'erreur

2. **Erreur commune** : "HF_TOKEN not found"
   - Vérifiez que la variable d'environnement est bien configurée

### Cold start trop long

- C'est normal : le modèle Pyannote prend 1-2 minutes à charger
- Solution : Configurez 1 warm worker pour éviter ce délai

## 📝 Résumé

1. ✅ Endpoint créé et build réussi
2. ⚙️ Configurer 1 warm worker dans Settings
3. ⏱️ Attendre 2-3 minutes que le worker démarre
4. ✅ Vérifier dans l'onglet "Workers" que le statut est "Ready"
5. 🚀 Tester avec une requête de diarisation

Une fois qu'un worker est "Ready", votre endpoint est opérationnel !

