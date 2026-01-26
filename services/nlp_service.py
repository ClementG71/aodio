"""
Service singleton pour partager l'instance Spacy entre tous les services
Économise la mémoire en évitant de charger le modèle plusieurs fois
"""
import logging
import threading
import spacy
from typing import Optional

logger = logging.getLogger(__name__)

# Instance globale partagée
_nlp_instance: Optional[spacy.Language] = None
_nlp_lock = threading.Lock()
_model_loaded = False


def get_nlp() -> Optional[spacy.Language]:
    """
    Retourne l'instance Spacy partagée (singleton).
    Charge le modèle au premier appel si nécessaire.
    
    Returns:
        spacy.Language: Instance du modèle Spacy ou None si erreur
    """
    global _nlp_instance, _model_loaded
    
    # Double-checked locking pattern pour thread-safety
    if _model_loaded:
        return _nlp_instance
    
    with _nlp_lock:
        # Vérifier à nouveau après avoir acquis le verrou
        if _model_loaded:
            return _nlp_instance
        
        if _nlp_instance is None:
            try:
                logger.info("Chargement du modèle Spacy 'fr_core_news_md' (singleton)...")
                _nlp_instance = spacy.load("fr_core_news_md")
                _model_loaded = True
                logger.info("Modèle Spacy chargé avec succès (singleton)")
            except OSError:
                logger.warning("Modèle Spacy 'fr_core_news_md' non trouvé. Tentative de téléchargement...")
                try:
                    from spacy.cli import download
                    download("fr_core_news_md")
                    _nlp_instance = spacy.load("fr_core_news_md")
                    _model_loaded = True
                    logger.info("Modèle Spacy téléchargé et chargé avec succès (singleton)")
                except Exception as e:
                    logger.error(f"Impossible de charger Spacy: {e}")
                    _nlp_instance = None
                    _model_loaded = True
        else:
            _model_loaded = True
    
    return _nlp_instance


def reset_nlp():
    """
    Réinitialise l'instance Spacy (utile pour les tests ou rechargement).
    """
    global _nlp_instance, _model_loaded
    
    with _nlp_lock:
        _nlp_instance = None
        _model_loaded = False
        logger.info("Instance Spacy réinitialisée")
