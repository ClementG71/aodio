"""
Tests pour le Circuit Breaker
"""
import pytest
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.circuit_breaker import (
    CircuitBreaker, 
    CircuitState, 
    CircuitBreakerOpen,
    circuit_breaker
)


class TestCircuitBreaker:
    """Tests pour CircuitBreaker"""
    
    def test_initial_state_is_closed(self):
        """Vérifie que le circuit est fermé à l'initialisation"""
        breaker = CircuitBreaker("test_init", failure_threshold=3)
        assert breaker.state == CircuitState.CLOSED
        assert breaker.is_closed is True
        assert breaker.is_open is False
    
    def test_stays_closed_on_success(self):
        """Vérifie que le circuit reste fermé après un succès"""
        breaker = CircuitBreaker("test_success", failure_threshold=3)
        
        with breaker:
            pass  # Succès
        
        assert breaker.state == CircuitState.CLOSED
    
    def test_opens_after_threshold_failures(self):
        """Vérifie que le circuit s'ouvre après le seuil d'échecs"""
        breaker = CircuitBreaker("test_threshold", failure_threshold=3, recovery_timeout=60)
        
        # 3 échecs consécutifs
        for i in range(3):
            try:
                with breaker:
                    raise Exception(f"Error {i}")
            except Exception:
                pass
        
        assert breaker.state == CircuitState.OPEN
        assert breaker.is_open is True
    
    def test_open_circuit_raises_exception(self):
        """Vérifie que le circuit ouvert lève une exception"""
        breaker = CircuitBreaker("test_open", failure_threshold=1, recovery_timeout=60)
        
        # Ouvrir le circuit
        try:
            with breaker:
                raise Exception("Error")
        except Exception:
            pass
        
        # Tenter un nouvel appel
        with pytest.raises(CircuitBreakerOpen) as exc_info:
            with breaker:
                pass
        
        assert "test_open" in str(exc_info.value)
        assert exc_info.value.time_until_retry > 0
    
    def test_half_open_after_recovery_timeout(self):
        """Vérifie le passage en HALF_OPEN après le timeout"""
        breaker = CircuitBreaker(
            "test_half_open", 
            failure_threshold=1, 
            recovery_timeout=0.1  # 100ms pour le test
        )
        
        # Ouvrir le circuit
        try:
            with breaker:
                raise Exception("Error")
        except Exception:
            pass
        
        assert breaker.state == CircuitState.OPEN
        
        # Attendre le recovery timeout
        time.sleep(0.15)
        
        # Le prochain appel devrait passer en HALF_OPEN
        with breaker:
            pass  # Succès
        
        # Après succès en HALF_OPEN, devrait passer en CLOSED
        assert breaker.state == CircuitState.CLOSED
    
    def test_half_open_failure_returns_to_open(self):
        """Vérifie le retour en OPEN après un échec en HALF_OPEN"""
        breaker = CircuitBreaker(
            "test_half_open_fail",
            failure_threshold=1,
            recovery_timeout=0.1
        )
        
        # Ouvrir le circuit
        try:
            with breaker:
                raise Exception("Error 1")
        except Exception:
            pass
        
        # Attendre le recovery timeout
        time.sleep(0.15)
        
        # Échec en HALF_OPEN
        try:
            with breaker:
                raise Exception("Error 2")
        except Exception:
            pass
        
        # Devrait retourner en OPEN
        assert breaker.state == CircuitState.OPEN
    
    def test_reset_clears_state(self):
        """Vérifie que reset() réinitialise le circuit"""
        breaker = CircuitBreaker("test_reset", failure_threshold=1)
        
        # Ouvrir le circuit
        try:
            with breaker:
                raise Exception("Error")
        except Exception:
            pass
        
        assert breaker.state == CircuitState.OPEN
        
        # Reset
        breaker.reset()
        
        assert breaker.state == CircuitState.CLOSED
        assert breaker.is_closed is True
    
    def test_get_status(self):
        """Vérifie que get_status() retourne les bonnes infos"""
        breaker = CircuitBreaker("test_status", failure_threshold=3)
        
        status = breaker.get_status()
        
        assert status["name"] == "test_status"
        assert status["state"] == "closed"
        assert status["failure_count"] == 0
        assert status["failure_threshold"] == 3
    
    def test_call_method(self):
        """Vérifie que call() exécute la fonction"""
        breaker = CircuitBreaker("test_call", failure_threshold=3)
        
        def add(a, b):
            return a + b
        
        result = breaker.call(add, 2, 3)
        assert result == 5
    
    def test_call_method_raises_on_open(self):
        """Vérifie que call() lève une exception si le circuit est ouvert"""
        breaker = CircuitBreaker("test_call_open", failure_threshold=1, recovery_timeout=60)
        
        # Ouvrir le circuit
        def failing_func():
            raise Exception("Error")
        
        try:
            breaker.call(failing_func)
        except Exception:
            pass
        
        # Le circuit est ouvert, call() doit lever CircuitBreakerOpen
        with pytest.raises(CircuitBreakerOpen):
            breaker.call(lambda: "should not run")
    
    def test_success_resets_failure_count(self):
        """Vérifie que le compteur d'échecs est réinitialisé après un succès"""
        breaker = CircuitBreaker("test_reset_count", failure_threshold=3)
        
        # 2 échecs (pas assez pour ouvrir)
        for i in range(2):
            try:
                with breaker:
                    raise Exception(f"Error {i}")
            except Exception:
                pass
        
        # 1 succès
        with breaker:
            pass
        
        # Le compteur devrait être à 0
        assert breaker.get_status()["failure_count"] == 0
        assert breaker.state == CircuitState.CLOSED


class TestCircuitBreakerDecorator:
    """Tests pour le décorateur @circuit_breaker"""
    
    def test_decorator_wraps_function(self):
        """Vérifie que le décorateur protège la fonction"""
        @circuit_breaker("test_decorator", failure_threshold=3)
        def my_func(x):
            return x * 2
        
        result = my_func(5)
        assert result == 10
    
    def test_decorator_opens_circuit(self):
        """Vérifie que le décorateur ouvre le circuit après échecs"""
        @circuit_breaker("test_decorator_fail", failure_threshold=2, recovery_timeout=60)
        def failing_func():
            raise ValueError("Always fails")
        
        # 2 échecs
        for _ in range(2):
            try:
                failing_func()
            except ValueError:
                pass
        
        # Le circuit devrait être ouvert
        with pytest.raises(CircuitBreakerOpen):
            failing_func()


class TestCircuitBreakerRegistry:
    """Tests pour le registre global des circuit breakers"""
    
    def test_get_returns_instance(self):
        """Vérifie que get() retourne l'instance enregistrée"""
        breaker = CircuitBreaker("test_registry", failure_threshold=3)
        
        retrieved = CircuitBreaker.get("test_registry")
        assert retrieved is breaker
    
    def test_get_returns_none_for_unknown(self):
        """Vérifie que get() retourne None pour un nom inconnu"""
        retrieved = CircuitBreaker.get("unknown_breaker_xyz")
        assert retrieved is None
    
    def test_get_all_status(self):
        """Vérifie que get_all_status() retourne tous les statuts"""
        # Créer quelques breakers
        CircuitBreaker("test_all_1", failure_threshold=3)
        CircuitBreaker("test_all_2", failure_threshold=5)
        
        all_status = CircuitBreaker.get_all_status()
        
        assert "test_all_1" in all_status
        assert "test_all_2" in all_status
        assert all_status["test_all_1"]["failure_threshold"] == 3
        assert all_status["test_all_2"]["failure_threshold"] == 5
