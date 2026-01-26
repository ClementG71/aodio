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

# Exposer le port
EXPOSE 5000

# Commande par défaut
# Dokploy gère le port via reverse proxy, on utilise 5000 en interne
# Le nombre de workers peut être ajusté selon les ressources disponibles
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "--timeout", "1800", "--graceful-timeout", "120", "wsgi:app"]