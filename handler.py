"""
Handler RunPod - Point d'entrée à la racine pour la validation RunPod
Ce fichier est utilisé uniquement pour la validation RunPod avant le build.
Le vrai handler est dans runpod_worker/handler.py et sera copié dans l'image Docker.
"""
# Ce fichier existe uniquement pour que RunPod puisse valider le handler path
# Le vrai handler est dans runpod_worker/handler.py et sera copié vers /app/handler.py par le Dockerfile
pass

