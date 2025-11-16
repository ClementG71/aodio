# Dépannage RunPod - Erreur 404

## 🔴 Erreur : "404 Client Error: Not Found for url: https://api.runpod.io/v2/..."

Cette erreur indique que l'endpoint RunPod n'est pas trouvé. Voici comment la résoudre :

## ✅ Vérifications à faire

### 1. Vérifier l'Endpoint ID

L'erreur montre l'Endpoint ID utilisé : `u6bvt0n0dh9bda`

**Vérifiez que cet ID est correct** :

1. Allez sur [https://www.runpod.io/console/serverless](https://www.runpod.io/console/serverless)
2. Cliquez sur votre endpoint
3. Vérifiez l'Endpoint ID dans :
   - L'URL : `https://www.runpod.io/console/serverless/YOUR_ENDPOINT_ID`
   - Ou dans "Endpoint Details" → "Endpoint ID"

4. **Comparez avec la variable `RUNPOD_ENDPOINT_ID` sur Railway** :
   - Allez dans Railway → Votre projet → Variables
   - Vérifiez que `RUNPOD_ENDPOINT_ID` correspond exactement à l'ID de votre endpoint
   - ⚠️ **Pas d'espaces avant/après** la valeur

### 2. Vérifier que l'endpoint est actif

1. Sur RunPod, vérifiez que votre endpoint est **"Active"** (statut vert)
2. Vérifiez qu'il y a au moins **1 worker disponible** (voir `RUNPOD_WORKERS.md`)

### 3. Vérifier l'API Key

1. Vérifiez que `RUNPOD_API_KEY` est bien configurée sur Railway
2. Testez l'API Key avec cette commande :

```bash
curl -X GET "https://api.runpod.io/v2/YOUR_ENDPOINT_ID/health" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

Si vous obtenez une réponse (même une erreur 404), l'API Key est valide.
Si vous obtenez `401 Unauthorized`, l'API Key est incorrecte.

### 4. Vérifier l'URL de l'API

L'URL correcte pour lancer un job est :
```
https://api.runpod.io/v2/{ENDPOINT_ID}/run
```

Vérifiez dans les logs que l'URL utilisée est bien celle-ci.

## 🔧 Solutions

### Solution 1 : Endpoint ID incorrect

Si l'Endpoint ID est incorrect :

1. Copiez le bon Endpoint ID depuis RunPod
2. Sur Railway → Variables → Modifiez `RUNPOD_ENDPOINT_ID`
3. Railway redéploiera automatiquement

### Solution 2 : Endpoint non déployé

Si l'endpoint n'existe pas ou a été supprimé :

1. Vérifiez sur RunPod que l'endpoint existe
2. Si nécessaire, recréez l'endpoint (voir `RUNPOD_SETUP.md`)
3. Mettez à jour `RUNPOD_ENDPOINT_ID` sur Railway

### Solution 3 : API Key incorrecte

Si l'API Key est incorrecte :

1. Générez une nouvelle API Key sur RunPod
2. Mettez à jour `RUNPOD_API_KEY` sur Railway

### Solution 4 : Endpoint dans un autre compte

Si l'endpoint est dans un compte d'équipe différent :

1. Vérifiez que vous êtes connecté au bon compte RunPod
2. Vérifiez que l'API Key correspond au bon compte

## 🧪 Test de l'endpoint

Pour tester si l'endpoint fonctionne, utilisez cette commande :

```bash
curl -X POST "https://api.runpod.io/v2/YOUR_ENDPOINT_ID/run" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "task": "diarization",
      "audio_url": "https://example.com/test.wav",
      "model": "pyannote/speaker-diarization-3.1"
    }
  }'
```

**Réponse attendue** :
- `200 OK` avec un `id` de job → Endpoint fonctionne ✅
- `404 Not Found` → Endpoint ID incorrect ou endpoint n'existe pas ❌
- `401 Unauthorized` → API Key incorrecte ❌

## 📝 Checklist de vérification

- [ ] Endpoint ID correct sur Railway
- [ ] Endpoint actif sur RunPod
- [ ] Au moins 1 worker disponible
- [ ] API Key correcte sur Railway
- [ ] Test API réussi (commande curl ci-dessus)

## 🆘 Si le problème persiste

1. Vérifiez les logs Railway pour plus de détails
2. Vérifiez les logs RunPod (onglet "Logs" de l'endpoint)
3. Contactez le support RunPod si nécessaire

