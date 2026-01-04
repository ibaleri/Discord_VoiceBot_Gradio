"""
llm_client
==========

Ein universelles Interface für LLM-Zugriffe (OpenAI, Groq, Ollama).

Dieses Package bietet die Klasse `LLMClient`, die automatisch erkennt,
welche API verfügbar ist (basierend auf `secrets.env`) und entsprechend
die Methode `chat_completion()` aufruft.
"""

from .llm_client import LLMClient

__all__ = ["LLMClient"]

# Optionaler Import des Adapters
try:
    from .adapter import LLMClientAdapter  # noqa: F401

    __all__.append("LLMClientAdapter")
except ImportError:
    # llama_index nicht installiert - Adapter nicht verfügbar
    pass


__version__ = "0.1.0"
__author__ = "Daniel Gaida"
__license__ = "MIT"
