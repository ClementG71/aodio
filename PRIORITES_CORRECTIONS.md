# 🎯 LISTE DES PRIORITÉS DE CORRECTION

**Date**: 2025-01-27  
**Basé sur**: Code Review complet

---

## 🔴 PRIORITÉ 1 - CRITIQUE (À faire immédiatement)

### 1.1 Désactiver le mode debug en production
**Fichier**: `app.py:475`  
**Impact**: Sécurité - Exposition d'informations sensibles  
**Temps estimé**: 5 minutes  
**Code actuel**:
```python
app.run(debug=True, host='0.0.0.0', port=5000)
```
**Correction**:
```python
if __name__ == '__main__':
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode, host='0.0.0.0', port=5000)
```

---

### 1.2 Restreindre CORS aux domaines autorisés
**Fichier**: `app.py:132, 176`  
**Impact**: Sécurité - Risque de CSRF  
**Temps estimé**: 15 minutes  
**Code actuel**:
```python
response.headers['Access-Control-Allow-Origin'] = '*'
```
**Correction**:
```python
allowed_origins = os.getenv('ALLOWED_ORIGINS', '').split(',')
origin = request.headers.get('Origin')
if origin and origin in allowed_origins:
    response.headers['Access-Control-Allow-Origin'] = origin
else:
    response.headers['Access-Control-Allow-Origin'] = 'null'
```

---

### 1.3 Corriger la race condition dans LogManager
**Fichier**: `services/log_manager.py:40-73`  
**Impact**: Stabilité - Perte de données en cas de requêtes concurrentes  
**Temps estimé**: 30 minutes  
**Problème**: Lecture/écriture non atomique du fichier JSON  
**Correction**: Ajouter un verrou de fichier
```python
import fcntl

def log_status(self, session_id: str, stage: str, message: str, data: Any = None):
    try:
        with open(self.history_file, 'r+', encoding='utf-8') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)  # Verrou exclusif
            history = json.load(f)
            # ... reste du code ...
            f.seek(0)
            f.truncate()
            json.dump(history, f, ensure_ascii=False, indent=2)
```

---

### 1.4 Améliorer la gestion des fichiers temporaires
**Fichier**: `services/mistral_voxtral.py:844-852, 1060-1068`  
**Impact**: Stabilité - Fichiers temporaires non supprimés en cas d'erreur  
**Temps estimé**: 20 minutes  
**Correction**: Utiliser contextmanager
```python
from contextlib import contextmanager

@contextmanager
def temporary_audio_segments(segments):
    try:
        yield segments
    finally:
        for seg in segments:
            try:
                if os.path.exists(seg['path']):
                    os.remove(seg['path'])
            except Exception as e:
                logger.warning(f"Impossible de supprimer {seg['path']}: {e}")
```

---

## 🟡 PRIORITÉ 2 - IMPORTANT (À faire bientôt)

### 2.1 Refactoriser mistral_voxtral.py
**Fichier**: `services/mistral_voxtral.py` (1899 lignes)  
**Impact**: Maintenabilité - Code difficile à maintenir et tester  
**Temps estimé**: 4-6 heures  
**Action**: Diviser en modules :
- `services/mistral_client.py` - Client API de base
- `services/transcription_mapper.py` - Logique de mapping
- `services/audio_segmenter.py` - Découpage audio
- `services/transcription_aligner.py` - Alignement des transcriptions

---

### 2.2 Remplacer threading par Celery
**Fichier**: `app.py:252-255`  
**Impact**: Robustesse - Pas de suivi, pas de limite, perte en cas de redémarrage  
**Temps estimé**: 2-3 heures  
**Action**: Implémenter Celery avec Redis
```python
from celery import Celery

celery_app = Celery('aodio', broker=os.getenv('REDIS_URL'))

@celery_app.task(bind=True, max_retries=3)
def process_audio_pipeline_task(self, session_id, metadata):
    try:
        # ... traitement ...
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)
```

---

### 2.3 Ajouter des tests unitaires de base
**Fichier**: Nouveau dossier `tests/`  
**Impact**: Qualité - Aucun test actuellement  
**Temps estimé**: 4-6 heures  
**Action**: Créer structure de tests :
```
tests/
├── __init__.py
├── test_audio_processor.py
├── test_llm_processor.py
├── test_mistral_voxtral.py
├── test_document_generator.py
└── test_app.py
```

---

### 2.4 Améliorer la validation des entrées
**Fichier**: `app.py:209-213`  
**Impact**: Sécurité - Validation basique  
**Temps estimé**: 30 minutes  
**Correction**: Vérifier la taille avant sauvegarde
```python
# Vérifier la taille avant sauvegarde
audio_file.seek(0, os.SEEK_END)
size = audio_file.tell()
audio_file.seek(0)
if size > MAX_FILE_SIZE:
    return jsonify({'error': 'Fichier trop volumineux'}), 413
```

---

## 🟢 PRIORITÉ 3 - AMÉLIORATION (À planifier)

### 3.1 Timeouts dynamiques
**Fichier**: `services/audio_processor.py:99, 166`  
**Temps estimé**: 15 minutes  
**Action**: Baser le timeout sur la durée du fichier
```python
duration = self._get_audio_duration(input_path)
timeout = max(3600, int(duration * 2))  # Au moins 2x la durée
```

---

### 3.2 Circuit breaker pour les appels API
**Fichier**: `services/llm_processor.py:406-450`  
**Temps estimé**: 1 heure  
**Action**: Ajouter circuit breaker
```python
from circuitbreaker import circuit

@circuit(failure_threshold=5, recovery_timeout=60)
@retry(...)
def _call_claude_safe(self, prompt: str) -> str:
    # ...
```

---

### 3.3 Masquer les données sensibles dans les logs
**Fichier**: `services/runpod_worker.py:107`  
**Temps estimé**: 20 minutes  
**Action**: Filtrer les clés API
```python
def _sanitize_payload(payload):
    sensitive_keys = ['key', 'token', 'api_key', 'secret']
    return {k: '***' if any(sk in k.lower() for sk in sensitive_keys) else v 
            for k, v in payload.items()}
```

---

### 3.4 Créer config.py centralisé
**Fichier**: Nouveau `config.py`  
**Temps estimé**: 1 heure  
**Action**: Centraliser toutes les configurations

---

### 3.5 Validation MIME type
**Fichier**: `app.py:38`  
**Temps estimé**: 30 minutes  
**Action**: Vérifier le type réel du fichier
```python
import magic
mime = magic.Magic(mime=True)
file_type = mime.from_file(audio_path)
```

---

### 3.6 Épingler les versions dans requirements.txt
**Fichier**: `requirements.txt`  
**Temps estimé**: 15 minutes  
**Action**: Utiliser des versions exactes pour la production

---

## 📊 PRIORITÉ 4 - MONITORING & OPTIMISATION

### 4.1 Ajouter métriques Prometheus
**Temps estimé**: 2 heures  
**Action**: Monitoring des performances

---

### 4.2 Implémenter cache Redis
**Temps estimé**: 2-3 heures  
**Action**: Éviter les appels API redondants

---

## 📚 PRIORITÉ 5 - DOCUMENTATION

### 5.1 Ajouter Swagger/OpenAPI
**Temps estimé**: 1-2 heures  
**Action**: Documentation interactive des API

---

### 5.2 Compléter les docstrings
**Temps estimé**: 1 heure  
**Action**: Ajouter docstrings manquantes

---

## 📅 PLAN D'ACTION RECOMMANDÉ

### Semaine 1 (Critique)
- ✅ Jour 1-2: Priorité 1 (4 tâches critiques)
- ✅ Jour 3-4: Priorité 2.4 (Validation entrées)

### Semaine 2 (Important)
- ✅ Jour 1-3: Priorité 2.3 (Tests unitaires)
- ✅ Jour 4-5: Priorité 2.2 (Celery)

### Semaine 3 (Refactoring)
- ✅ Jour 1-3: Priorité 2.1 (Refactoring mistral_voxtral.py)

### Semaine 4 (Améliorations)
- ✅ Priorité 3 (Améliorations diverses)
- ✅ Priorité 4 (Monitoring)

---

## ⚡ QUICK WINS (Corrections rapides < 30 min)

1. ✅ Désactiver debug (5 min)
2. ✅ Restreindre CORS (15 min)
3. ✅ Épingler versions requirements.txt (15 min)
4. ✅ Masquer données sensibles dans logs (20 min)
5. ✅ Timeouts dynamiques (15 min)

**Total Quick Wins**: ~1h15 pour améliorer significativement la sécurité et la robustesse

---

*Dernière mise à jour: 2025-01-27*
