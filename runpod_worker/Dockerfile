FROM runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel

# Installer les dépendances système
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Copier les fichiers
WORKDIR /app
COPY requirements.txt .
COPY handler.py .

# Installer les dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# Commande de démarrage
CMD ["python", "handler.py"]

