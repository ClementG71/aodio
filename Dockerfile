# Dockerfile pour Aodio - Application Flask

# Utiliser une image Python officielle
FROM python:3.9-slim

# Définir le répertoire de travail
WORKDIR /app

# Installer les dépendances système nécessaires
RUN apt-get update && apt-get install -y \
    build-essential \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Copier les fichiers de configuration et requirements
COPY requirements.txt ./
COPY env.example .env.example

# Installer les dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# Copier le reste de l'application
COPY . .

# Créer les répertoires nécessaires
RUN mkdir -p uploads processed logs

# Exposer le port (121 par défaut, peut être changé via variable PORT)
EXPOSE 121

# Commande par défaut
# Dokploy gère le port via reverse proxy
# Utilise PORT de l'environnement si défini, sinon 121 par défaut
# Le nombre de workers peut être ajusté selon les ressources disponibles
CMD ["sh", "-c", "gunicorn -w 4 -b 0.0.0.0:${PORT:-121} --timeout 1800 --graceful-timeout 120 wsgi:app"]