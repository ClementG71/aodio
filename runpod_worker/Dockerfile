FROM runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel

# Installer les dépendances système (cette couche sera mise en cache)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Créer le répertoire de travail
WORKDIR /app

# Copier uniquement requirements.txt d'abord (pour maximiser le cache)
# Si requirements.txt ne change pas, cette couche sera réutilisée
# Note: Quand le Dockerfile est dans runpod_worker/, RunPod configure le contexte de build
# comme étant runpod_worker/, donc les chemins sont relatifs à ce dossier
COPY requirements.txt ./requirements.txt

# Installer les dépendances Python
# Note: torch et torchaudio sont déjà dans l'image de base (PyTorch 2.1.0 avec CUDA 11.8.0)
# On les spécifie dans requirements.txt pour éviter que pyannote.audio ne les remplace
# On utilise --no-cache-dir pour réduire la taille, mais le cache Docker accélérera les builds suivants
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copier le handler en dernier (change le plus souvent)
COPY handler.py ./handler.py

# Commande de démarrage
CMD ["python", "handler.py"]

