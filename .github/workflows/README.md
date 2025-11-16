# GitHub Actions Workflows

Ce dossier contient les workflows GitHub Actions pour automatiser les déploiements.

## Workflows disponibles

### `runpod-rebuild.yml`

Déclenche automatiquement un rebuild de l'endpoint RunPod lorsque :
- Des modifications sont poussées sur la branche `main` dans le dossier `runpod_worker/`
- Une release GitHub est publiée ou modifiée
- Le workflow est déclenché manuellement depuis l'interface GitHub

## Configuration requise

Pour que ce workflow fonctionne, vous devez configurer les secrets suivants dans GitHub :

1. Allez dans **Settings** → **Secrets and variables** → **Actions**
2. Ajoutez les secrets suivants :
   - `RUNPOD_API_KEY` : Votre clé API RunPod
   - `RUNPOD_ENDPOINT_ID` : L'ID de votre endpoint RunPod

## Comment obtenir les valeurs

### RUNPOD_API_KEY
1. Allez sur [https://www.runpod.io/console/user/settings](https://www.runpod.io/console/user/settings)
2. Section "API Keys"
3. Créez ou copiez votre clé API

### RUNPOD_ENDPOINT_ID
1. Allez sur [https://www.runpod.io/console/serverless](https://www.runpod.io/console/serverless)
2. Cliquez sur votre endpoint
3. Copiez l'Endpoint ID (visible dans l'URL ou les détails)

## Déclenchement manuel

Vous pouvez déclencher le workflow manuellement :
1. Allez dans l'onglet **Actions** de votre repository GitHub
2. Sélectionnez le workflow "Rebuild RunPod Endpoint"
3. Cliquez sur **Run workflow**
4. Choisissez la branche et cliquez sur **Run workflow**

## Notes

- Le workflow utilise l'API RunPod pour déclencher un "rolling release" qui reconstruit l'endpoint
- Le rebuild peut prendre plusieurs minutes selon la taille de l'image Docker
- Vous pouvez suivre le progrès du build sur la console RunPod

