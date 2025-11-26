# 🔧 Changements de Configuration - Quick Wins Implémentés

**Date**: 2025-01-27  
**Impact**: Configuration Railway uniquement (aucun changement RunPod)

---

## 📋 Résumé des Changements

Les quick wins implémentés nécessitent **2 nouvelles variables d'environnement optionnelles** sur Railway. Aucun changement n'est nécessaire pour RunPod.

### ✅ Compatibilité
- **Rétrocompatible** : L'application fonctionne sans ces variables (avec avertissements)
- **RunPod** : Aucun changement nécessaire
- **Railway** : Ajout de 2 variables optionnelles recommandées

---

## 🚂 Configuration Railway

### Variables d'environnement à ajouter

#### 1. `FLASK_DEBUG` (Recommandé)

**Description**: Contrôle le mode debug de Flask  
**Valeur par défaut**: `False` (désactivé)  
**Valeurs possibles**: `True` ou `False`

**Comment l'ajouter sur Railway**:
1. Allez dans votre projet Railway
2. Onglet **"Variables"**
3. Cliquez sur **"New Variable"**
4. **Nom**: `FLASK_DEBUG`
5. **Valeur**: `False` (pour la production)
6. Cliquez sur **"Add"**

**⚠️ Important**:
- En **production** : Toujours mettre `False`
- En **développement local** : Peut être `True` pour le débogage
- Si non configuré : Le mode debug est **désactivé par défaut** (sécurisé)

---

#### 2. `ALLOWED_ORIGINS` (Recommandé pour la sécurité)

**Description**: Liste des domaines autorisés pour les requêtes CORS  
**Valeur par défaut**: Vide (tous les domaines autorisés avec avertissement)  
**Format**: Domaines séparés par des virgules

**Comment l'ajouter sur Railway**:
1. Allez dans votre projet Railway
2. Onglet **"Variables"**
3. Cliquez sur **"New Variable"**
4. **Nom**: `ALLOWED_ORIGINS`
5. **Valeur**: Liste des domaines autorisés, par exemple :
   ```
   https://votre-app.railway.app,https://www.votre-domaine.com
   ```
6. Cliquez sur **"Add"**

**Exemples de valeurs**:
```bash
# Un seul domaine
https://aodio.railway.app

# Plusieurs domaines (séparés par virgule)
https://aodio.railway.app,https://www.aodio.fr,https://app.aodio.fr

# Avec RunPod (si nécessaire)
https://aodio.railway.app,https://api.runpod.ai
```

**⚠️ Important**:
- **Si vide ou non configuré** : Tous les domaines sont autorisés (compatible avec RunPod)
- Un **avertissement** sera logué dans les logs Railway
- **Recommandé en production** : Limiter aux domaines nécessaires
- **RunPod** : Si vous avez des problèmes avec RunPod, vous pouvez temporairement laisser vide

---

## 🔍 Vérification de la Configuration

### Checklist Railway

Vérifiez que vous avez ces variables dans Railway :

```
✅ SECRET_KEY
✅ ANTHROPIC_API_KEY
✅ RUNPOD_API_KEY
✅ RUNPOD_ENDPOINT_ID
✅ MISTRAL_API_KEY
✅ FLASK_DEBUG=False          ← NOUVEAU (recommandé)
✅ ALLOWED_ORIGINS=...        ← NOUVEAU (recommandé)
```

### Vérifier les logs Railway

Après le déploiement, vérifiez les logs Railway :

1. Allez dans Railway → Votre projet → Onglet **"Deployments"**
2. Cliquez sur le dernier déploiement
3. Vérifiez les logs pour :
   - ✅ Pas d'erreur au démarrage
   - ⚠️ Si `ALLOWED_ORIGINS` n'est pas configuré, vous verrez :
     ```
     WARNING: ALLOWED_ORIGINS non configuré, CORS ouvert à tous (non recommandé en production)
     ```

---

## 🎯 Impact par Composant

### Railway (Application Flask)

**Changements nécessaires**:
- ✅ Ajouter `FLASK_DEBUG=False` (recommandé)
- ✅ Ajouter `ALLOWED_ORIGINS` avec vos domaines (recommandé)

**Comportement sans ces variables**:
- ✅ L'application fonctionne normalement
- ⚠️ Mode debug désactivé par défaut (sécurisé)
- ⚠️ CORS ouvert à tous (avec avertissement dans les logs)

---

### RunPod (Worker GPU)

**Changements nécessaires**:
- ✅ **AUCUN** - Aucun changement requis

**Pourquoi**:
- Les modifications concernent uniquement l'application Flask
- RunPod continue de fonctionner exactement comme avant
- La communication Flask ↔ RunPod n'est pas affectée

---

## 🔄 Migration depuis l'Ancienne Configuration

### Si vous avez déjà une configuration Railway

1. **Vérifiez vos variables existantes** :
   ```
   SECRET_KEY
   ANTHROPIC_API_KEY
   RUNPOD_API_KEY
   RUNPOD_ENDPOINT_ID
   MISTRAL_API_KEY
   ```

2. **Ajoutez les nouvelles variables** (optionnel mais recommandé) :
   ```
   FLASK_DEBUG=False
   ALLOWED_ORIGINS=https://votre-domaine.railway.app
   ```

3. **Redéployez** (automatique après ajout de variables)

4. **Vérifiez les logs** pour confirmer que tout fonctionne

---

## 📝 Exemple de Configuration Complète Railway

Voici un exemple complet de toutes les variables à configurer sur Railway :

```bash
# Sécurité Flask
SECRET_KEY=votre-secret-key-64-caracteres
FLASK_DEBUG=False

# CORS (sécurité)
ALLOWED_ORIGINS=https://aodio.railway.app,https://www.aodio.fr

# API Anthropic (Claude)
ANTHROPIC_API_KEY=sk-ant-...

# RunPod
RUNPOD_API_KEY=...
RUNPOD_ENDPOINT_ID=abc123def456

# Mistral AI (Voxtral)
MISTRAL_API_KEY=...

# Railway (automatique, mais peut être forcé)
RAILWAY_PUBLIC_DOMAIN=aodio.railway.app
```

---

## 🧪 Test de la Configuration

### Test 1 : Vérifier que l'application démarre

```bash
# Testez la route de santé
curl https://votre-app.railway.app/health

# Réponse attendue :
# {"status":"ok","message":"Application Aodio is running"}
```

### Test 2 : Vérifier les logs

Dans Railway → Deployments → Logs, vous devriez voir :
- ✅ Pas d'erreur
- ⚠️ Si `ALLOWED_ORIGINS` non configuré : Un avertissement (mais l'app fonctionne)

### Test 3 : Vérifier CORS (si configuré)

Si vous avez configuré `ALLOWED_ORIGINS`, testez depuis un navigateur :

```javascript
// Depuis la console du navigateur sur votre domaine autorisé
fetch('https://votre-app.railway.app/health')
  .then(r => r.json())
  .then(console.log)
  // Devrait fonctionner si le domaine est dans ALLOWED_ORIGINS
```

---

## ⚠️ Problèmes Potentiels et Solutions

### Problème 1 : RunPod ne peut plus accéder aux fichiers

**Symptôme**: Erreur 403 ou CORS lors des appels RunPod

**Solution**:
1. Vérifiez que l'URL de votre app Railway est dans `ALLOWED_ORIGINS`
2. Ou temporairement, laissez `ALLOWED_ORIGINS` vide (tous autorisés)
3. RunPod doit pouvoir accéder à `https://votre-app.railway.app/files/...`

**Exemple de configuration**:
```bash
ALLOWED_ORIGINS=https://aodio.railway.app,https://api.runpod.ai
```

---

### Problème 2 : L'application ne démarre pas

**Symptôme**: Erreur au démarrage dans les logs Railway

**Solution**:
1. Vérifiez que toutes les variables obligatoires sont présentes :
   - `SECRET_KEY`
   - `ANTHROPIC_API_KEY`
   - `RUNPOD_API_KEY`
   - `RUNPOD_ENDPOINT_ID`
   - `MISTRAL_API_KEY`
2. Les nouvelles variables (`FLASK_DEBUG`, `ALLOWED_ORIGINS`) sont **optionnelles**

---

### Problème 3 : Avertissement CORS dans les logs

**Symptôme**: 
```
WARNING: ALLOWED_ORIGINS non configuré, CORS ouvert à tous (non recommandé en production)
```

**Solution**:
- C'est juste un avertissement, l'application fonctionne
- Pour le corriger, ajoutez `ALLOWED_ORIGINS` avec vos domaines
- En développement, vous pouvez ignorer cet avertissement

---

## 📊 Récapitulatif des Changements

| Composant | Changement Requis | Urgence | Impact |
|-----------|-------------------|---------|--------|
| **Railway** | Ajouter `FLASK_DEBUG=False` | ⚠️ Recommandé | Sécurité |
| **Railway** | Ajouter `ALLOWED_ORIGINS` | ⚠️ Recommandé | Sécurité |
| **RunPod** | Aucun | ✅ Aucun | Aucun |

---

## ✅ Checklist de Migration

- [ ] Lire ce document
- [ ] Ajouter `FLASK_DEBUG=False` sur Railway
- [ ] Ajouter `ALLOWED_ORIGINS` avec vos domaines sur Railway
- [ ] Vérifier que l'application redéploie automatiquement
- [ ] Tester la route `/health`
- [ ] Vérifier les logs Railway (pas d'erreur)
- [ ] Tester un upload de fichier audio complet
- [ ] Vérifier que RunPod fonctionne toujours

---

## 🎓 Comprendre les Changements

### Pourquoi `FLASK_DEBUG` ?

Le mode debug de Flask expose des informations sensibles (stack traces, code source) en cas d'erreur. En production, cela représente un risque de sécurité.

**Avant** : `debug=True` toujours activé  
**Après** : Contrôlé par variable d'environnement (désactivé par défaut)

---

### Pourquoi `ALLOWED_ORIGINS` ?

CORS (Cross-Origin Resource Sharing) permet à un site web d'accéder à votre API depuis un autre domaine. Par défaut, l'application autorisait tous les domaines (`*`), ce qui peut être un risque de sécurité.

**Avant** : Tous les domaines autorisés (`*`)  
**Après** : Liste de domaines autorisés (configurable)

**Note** : Pour RunPod, si vous avez des problèmes, vous pouvez temporairement laisser vide (tous autorisés) ou ajouter les domaines RunPod.

---

## 📞 Besoin d'Aide ?

Si vous rencontrez des problèmes :

1. **Consultez les logs Railway** : Railway → Deployments → Logs
2. **Vérifiez les variables** : Railway → Variables
3. **Testez la route `/health`** : `curl https://votre-app.railway.app/health`
4. **Consultez** `RAILWAY_TROUBLESHOOTING.md` pour plus d'aide

---

*Dernière mise à jour: 2025-01-27*
