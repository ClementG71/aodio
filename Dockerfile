# Dockerfile pour RunPod Worker - doit être à la racine du repo
# Ce Dockerfile est utilisé par RunPod pour builder l'image du worker
# Utilisation d'une image PyTorch officielle avec CUDA 12.1 (dernière version stable disponible)
# Note: PyTorch 2.8 n'est pas encore disponible, on utilise la dernière version stable
FROM pytorch/pytorch:2.5.1-cuda12.1-cudnn9-devel

# Installer les dépendances système (cette couche sera mise en cache)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Créer le répertoire de travail
WORKDIR /app

# Copier uniquement requirements.txt d'abord (pour maximiser le cache)
# Si requirements.txt ne change pas, cette couche sera réutilisée
COPY runpod_worker/requirements.txt ./requirements.txt

# Installer les dépendances Python
# Note: torch et torchaudio sont déjà dans l'image de base (PyTorch 2.8.0 avec CUDA 12.6.0)
# On les spécifie dans requirements.txt pour éviter que pyannote.audio ne les remplace
# On utilise --no-cache-dir pour réduire la taille, mais le cache Docker accélérera les builds suivants
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copier le handler en dernier (change le plus souvent)
# On copie depuis runpod_worker/ (source de vérité) vers /app/handler.py
COPY runpod_worker/handler.py ./handler.py

# Commande de démarrage
CMD ["python", "handler.py"]

