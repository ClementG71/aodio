# 🎯 PROCHAINES ÉTAPES - Priorités Restantes

**Date**: 2025-01-27  
**Statut**: Quick Wins ✅ Terminés

---

## ✅ CE QUI A ÉTÉ FAIT

- ✅ Désactivation du mode debug (FLASK_DEBUG)
- ✅ Restriction CORS (ALLOWED_ORIGINS)
- ✅ Masquage des données sensibles dans les logs
- ✅ Timeouts dynamiques
- ✅ Épinglage des versions

---

## 🔴 PRIORITÉ 1 - CRITIQUE (À faire maintenant)

### 1.1 Corriger la race condition dans LogManager ⚠️
**Fichier**: `services/log_manager.py`  
**Impact**: **CRITIQUE** - Perte de données en cas de requêtes concurrentes  
**Temps**: 30 minutes  
**Urgence**: 🔴 Haute

**Problème**: 
- Plusieurs requêtes simultanées peuvent écrire en même temps dans `history.json`
- Risque de perte de données ou corruption du fichier

**Solution**: Ajouter un verrou de fichier (fcntl)

---

### 1.2 Améliorer la gestion des fichiers temporaires ⚠️
**Fichier**: `services/mistral_voxtral.py`  
**Impact**: **CRITIQUE** - Fichiers temporaires non supprimés = espace disque perdu  
**Temps**: 20 minutes  
**Urgence**: 🔴 Haute

**Problème**: 
- Les segments audio temporaires peuvent ne pas être supprimés en cas d'erreur
- Accumulation de fichiers = problème d'espace disque

**Solution**: Utiliser contextmanager pour garantir la suppression

---

## 🟡 PRIORITÉ 2 - IMPORTANT (À faire cette semaine)

### 2.1 Améliorer la validation des entrées
**Fichier**: `app.py:209-213`  
**Impact**: Sécurité - Validation basique  
**Temps**: 30 minutes  
**Urgence**: 🟡 Moyenne

**Action**: Vérifier la taille réelle du fichier avant sauvegarde complète

---

### 2.2 Ajouter des tests unitaires de base
**Fichier**: Nouveau dossier `tests/`  
**Impact**: Qualité - Aucun test actuellement  
**Temps**: 4-6 heures  
**Urgence**: 🟡 Moyenne

**Action**: Créer structure de tests pour les composants critiques

---

### 2.3 Remplacer threading par Celery
**Fichier**: `app.py:252-255`  
**Impact**: Robustesse - Pas de suivi, pas de limite  
**Temps**: 2-3 heures  
**Urgence**: 🟡 Moyenne

**Action**: Implémenter Celery avec Redis pour le traitement asynchrone

---

### 2.4 Refactoriser mistral_voxtral.py
**Fichier**: `services/mistral_voxtral.py` (1899 lignes)  
**Impact**: Maintenabilité - Code difficile à maintenir  
**Temps**: 4-6 heures  
**Urgence**: 🟡 Moyenne (peut attendre)

**Action**: Diviser en modules plus petits

---

## 📊 PLAN D'ACTION RECOMMANDÉ

### Cette Semaine (Priorité 1)

**Jour 1** (1h):
1. ✅ Corriger la race condition dans LogManager (30 min)
2. ✅ Améliorer la gestion des fichiers temporaires (20 min)
3. ✅ Améliorer la validation des entrées (30 min)

**Résultat**: Tous les problèmes critiques résolus

---

### Semaine Prochaine (Priorité 2)

**Jour 1-2** (4-6h):
- Ajouter des tests unitaires de base

**Jour 3-4** (2-3h):
- Implémenter Celery pour le traitement asynchrone

**Jour 5** (optionnel):
- Commencer le refactoring de mistral_voxtral.py

---

## 🎯 RECOMMANDATION IMMÉDIATE

**Commencer par les 2 priorités critiques restantes** :

1. **Race condition LogManager** (30 min) - Risque de perte de données
2. **Fichiers temporaires** (20 min) - Risque d'espace disque

**Total**: ~1h pour résoudre tous les problèmes critiques

---

## 📈 Impact par Priorité

| Priorité | Impact | Temps | Urgence |
|----------|--------|-------|---------|
| Race condition | 🔴 Critique | 30 min | ⚡ Immédiate |
| Fichiers temporaires | 🔴 Critique | 20 min | ⚡ Immédiate |
| Validation entrées | 🟡 Important | 30 min | 📅 Cette semaine |
| Tests unitaires | 🟡 Important | 4-6h | 📅 Cette semaine |
| Celery | 🟡 Important | 2-3h | 📅 Cette semaine |
| Refactoring | 🟢 Amélioration | 4-6h | 📅 Plus tard |

---

## ✅ Checklist

### Priorité 1 - Critique
- [ ] Corriger race condition LogManager
- [ ] Améliorer gestion fichiers temporaires

### Priorité 2 - Important
- [ ] Améliorer validation des entrées
- [ ] Ajouter tests unitaires
- [ ] Implémenter Celery
- [ ] Refactoriser mistral_voxtral.py

---

*Dernière mise à jour: 2025-01-27*
