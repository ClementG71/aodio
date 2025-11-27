"""
Circuit Breaker pour les appels API externes

Évite d'appeler répétitivement une API qui est indisponible.

États:
- CLOSED: Fonctionnement normal, les appels passent
- OPEN: API détectée comme down, les appels échouent immédiatement
- HALF_OPEN: Période de test, on laisse passer un appel pour vérifier

Usage:
    breaker = CircuitBreaker("mistral_api", failure_threshold=3, recovery_timeout=60)
    
    try:
        with breaker:
            result = call_api()
    except CircuitBreakerOpen:
        # L'API est down, gérer l'erreur sans appeler l'API
        pass
"""
import time
import logging
import threading
from enum import Enum
from functools import wraps
from typing import Optional, Dict, Any, Callable

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing fast
    HALF_OPEN = "half_open" # Testing recovery


class CircuitBreakerOpen(Exception):
    """Exception levée quand le circuit est ouvert"""
    def __init__(self, name: str, time_until_retry: float):
        self.name = name
        self.time_until_retry = time_until_retry
        super().__init__(
            f"Circuit breaker '{name}' is OPEN. "
            f"API unavailable. Retry in {time_until_retry:.0f}s"
        )


class CircuitBreaker:
    """
    Circuit Breaker pour protéger les appels API
    
    Args:
        name: Nom du circuit (pour le logging)
        failure_threshold: Nombre d'échecs avant ouverture du circuit
        recovery_timeout: Temps en secondes avant de retester l'API
        success_threshold: Nombre de succès en HALF_OPEN pour fermer le circuit
    """
    
    # Registre global de tous les circuit breakers
    _instances: Dict[str, 'CircuitBreaker'] = {}
    _lock = threading.Lock()
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
        success_threshold: int = 1
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._lock = threading.Lock()
        
        # Enregistrer l'instance
        with CircuitBreaker._lock:
            CircuitBreaker._instances[name] = self
    
    @classmethod
    def get(cls, name: str) -> Optional['CircuitBreaker']:
        """Récupère un circuit breaker par son nom"""
        return cls._instances.get(name)
    
    @classmethod
    def get_all_status(cls) -> Dict[str, Dict[str, Any]]:
        """Retourne le statut de tous les circuit breakers"""
        return {
            name: breaker.get_status()
            for name, breaker in cls._instances.items()
        }
    
    @property
    def state(self) -> CircuitState:
        """État actuel du circuit"""
        return self._state
    
    @property
    def is_closed(self) -> bool:
        return self._state == CircuitState.CLOSED
    
    @property
    def is_open(self) -> bool:
        return self._state == CircuitState.OPEN
    
    def get_status(self) -> Dict[str, Any]:
        """Retourne le statut détaillé du circuit"""
        with self._lock:
            status = {
                "name": self.name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "failure_threshold": self.failure_threshold,
            }
            
            if self._state == CircuitState.OPEN and self._last_failure_time:
                time_since_failure = time.time() - self._last_failure_time
                time_until_retry = max(0, self.recovery_timeout - time_since_failure)
                status["time_until_retry"] = round(time_until_retry, 1)
            
            return status
    
    def _should_attempt(self) -> bool:
        """Vérifie si on doit tenter un appel"""
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True
            
            if self._state == CircuitState.OPEN:
                # Vérifier si le timeout de recovery est passé
                if self._last_failure_time:
                    time_since_failure = time.time() - self._last_failure_time
                    if time_since_failure >= self.recovery_timeout:
                        # Passer en HALF_OPEN pour tester
                        self._state = CircuitState.HALF_OPEN
                        self._success_count = 0
                        logger.info(f"Circuit breaker '{self.name}': OPEN -> HALF_OPEN (testing recovery)")
                        return True
                
                return False
            
            # HALF_OPEN: on laisse passer pour tester
            return True
    
    def _on_success(self):
        """Appelé après un appel réussi"""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    logger.info(f"Circuit breaker '{self.name}': HALF_OPEN -> CLOSED (recovered)")
            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success
                self._failure_count = 0
    
    def _on_failure(self, error: Exception):
        """Appelé après un échec"""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            
            if self._state == CircuitState.HALF_OPEN:
                # Échec pendant le test, retour en OPEN
                self._state = CircuitState.OPEN
                logger.warning(
                    f"Circuit breaker '{self.name}': HALF_OPEN -> OPEN "
                    f"(recovery failed: {type(error).__name__})"
                )
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    self._state = CircuitState.OPEN
                    logger.warning(
                        f"Circuit breaker '{self.name}': CLOSED -> OPEN "
                        f"(threshold reached: {self._failure_count} failures)"
                    )
    
    def reset(self):
        """Réinitialise le circuit breaker"""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = None
            logger.info(f"Circuit breaker '{self.name}': manually reset to CLOSED")
    
    def __enter__(self):
        """Context manager entry"""
        if not self._should_attempt():
            time_since_failure = time.time() - (self._last_failure_time or time.time())
            time_until_retry = max(0, self.recovery_timeout - time_since_failure)
            raise CircuitBreakerOpen(self.name, time_until_retry)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        if exc_type is None:
            self._on_success()
        else:
            # Ne pas traiter CircuitBreakerOpen comme un échec
            if not isinstance(exc_val, CircuitBreakerOpen):
                self._on_failure(exc_val)
        return False  # Don't suppress exceptions
    
    def call(self, func: Callable, *args, **kwargs):
        """
        Exécute une fonction avec protection du circuit breaker
        
        Args:
            func: Fonction à exécuter
            *args, **kwargs: Arguments de la fonction
            
        Returns:
            Résultat de la fonction
            
        Raises:
            CircuitBreakerOpen: Si le circuit est ouvert
        """
        with self:
            return func(*args, **kwargs)


def circuit_breaker(
    name: str,
    failure_threshold: int = 3,
    recovery_timeout: float = 60.0
):
    """
    Décorateur pour protéger une fonction avec un circuit breaker
    
    Usage:
        @circuit_breaker("mistral_api")
        def call_mistral():
            ...
    """
    def decorator(func: Callable):
        breaker = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout
        )
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            return breaker.call(func, *args, **kwargs)
        
        # Attacher le breaker pour un accès direct
        wrapper.circuit_breaker = breaker
        return wrapper
    
    return decorator


# Circuit breakers pré-configurés pour les APIs du projet
mistral_breaker = CircuitBreaker(
    name="mistral_api",
    failure_threshold=3,
    recovery_timeout=60.0
)

anthropic_breaker = CircuitBreaker(
    name="anthropic_api", 
    failure_threshold=3,
    recovery_timeout=60.0
)

runpod_breaker = CircuitBreaker(
    name="runpod_api",
    failure_threshold=3,
    recovery_timeout=120.0  # RunPod peut être plus lent à récupérer
)
