"""LLMClientAdapter für llama-index Integration.

Dieser Adapter ermöglicht die Nutzung von LLMClient als llama-index LLM.
"""

from typing import Any

from pydantic import Field

from .llm_client import LLMClient

try:
    from llama_index.core.llms import (
        LLM,
        ChatMessage,
        ChatResponse,
        CompletionResponse,
        LLMMetadata,
    )

    LLAMA_INDEX_AVAILABLE = True
except ImportError:
    LLAMA_INDEX_AVAILABLE = False
    # Dummy-Klassen für den Fall, dass llama_index nicht installiert ist
    LLM = object  # type: ignore
    ChatMessage = dict  # type: ignore
    ChatResponse = dict  # type: ignore
    CompletionResponse = dict  # type: ignore
    LLMMetadata = dict  # type: ignore


class LLMClientAdapter(LLM):
    """Adapter für llama-index zur Nutzung des LLMClient.

    Dieser Adapter ermöglicht es, LLMClient als normales llama-index LLM
    zu verwenden, z.B. für RAG-Anwendungen.

    Attributes:
        client: Die LLMClient-Instanz die verwendet werden soll.

    Examples:
        >>> from llm_client import LLMClient, LLMClientAdapter
        >>> client = LLMClient()
        >>> adapter = LLMClientAdapter(client=client)
        >>> # Nutze in llama-index
        >>> from llama_index.core import VectorStoreIndex
        >>> index = VectorStoreIndex.from_documents(docs, llm=adapter)

    Note:
        Benötigt llama-index-core Installation:
        pip install llama-index-core
    """

    client: LLMClient | None = Field(default=None, exclude=True)

    def __init__(self, **data: Any) -> None:
        """Initialisiert den LLMClientAdapter.

        Args:
            **data: Keyword-Argumente inklusive 'client' (LLMClient Instanz).

        Raises:
            ImportError: Wenn llama-index-core nicht installiert ist.

        Examples:
            >>> client = LLMClient(api_choice="openai")
            >>> adapter = LLMClientAdapter(client=client)
        """
        if not LLAMA_INDEX_AVAILABLE:
            raise ImportError(
                "llama-index-core is required to use LLMClientAdapter. "
                "Install it with: pip install llama-index-core"
            )
        super().__init__(**data)

    def chat(self, messages: list[ChatMessage], **kwargs: Any) -> ChatResponse:
        """Führt einen Chat-Completion Request aus.

        Args:
            messages: Liste von ChatMessage-Objekten von llama-index.
            **kwargs: Zusätzliche Keyword-Argumente (werden ignoriert).

        Returns:
            ChatResponse-Objekt mit der generierten Antwort.

        Raises:
            ValueError: Wenn kein Client gesetzt ist.

        Examples:
            >>> from llama_index.core.llms import ChatMessage
            >>> messages = [ChatMessage(role="user", content="Hello!")]
            >>> response = adapter.chat(messages)
        """
        if self.client is None:
            raise ValueError("LLMClient instance must be provided")

        # Konvertiere llama_index Nachrichten in dict
        hf_messages = [{"role": m.role, "content": m.content} for m in messages]

        # Nutze LLMClient
        response = self.client.chat_completion(hf_messages)

        return ChatResponse(message=ChatMessage(role="assistant", content=response))

    def complete(self, prompt: str, **kwargs: Any) -> CompletionResponse:
        """Führt einen Completion Request aus.

        Args:
            prompt: Der Input-Prompt.
            **kwargs: Zusätzliche Keyword-Argumente.

        Raises:
            NotImplementedError: Diese Methode ist nicht implementiert.

        Note:
            Verwenden Sie stattdessen die chat()-Methode.
        """
        raise NotImplementedError("complete not implemented")

    def stream_chat(self, *args: Any, **kwargs: Any) -> Any:
        """Streaming Chat ist nicht implementiert.

        Args:
            *args: Positionsargumente.
            **kwargs: Keyword-Argumente.

        Raises:
            NotImplementedError: Diese Methode ist nicht implementiert.
        """
        raise NotImplementedError("stream_chat not implemented")

    def stream_complete(self, *args: Any, **kwargs: Any) -> Any:
        """Streaming Completion ist nicht implementiert.

        Args:
            *args: Positionsargumente.
            **kwargs: Keyword-Argumente.

        Raises:
            NotImplementedError: Diese Methode ist nicht implementiert.
        """
        raise NotImplementedError("stream_complete not implemented")

    async def astream_chat(self, *args: Any, **kwargs: Any) -> Any:
        """Async Streaming Chat ist nicht implementiert.

        Args:
            *args: Positionsargumente.
            **kwargs: Keyword-Argumente.

        Raises:
            NotImplementedError: Diese Methode ist nicht implementiert.
        """
        raise NotImplementedError("astream_chat not implemented")

    async def astream_complete(self, *args: Any, **kwargs: Any) -> Any:
        """Async Streaming Completion ist nicht implementiert.

        Args:
            *args: Positionsargumente.
            **kwargs: Keyword-Argumente.

        Raises:
            NotImplementedError: Diese Methode ist nicht implementiert.
        """
        raise NotImplementedError("astream_complete not implemented")

    async def achat(self, *args: Any, **kwargs: Any) -> Any:
        """Async Chat ist nicht implementiert.

        Args:
            *args: Positionsargumente.
            **kwargs: Keyword-Argumente.

        Raises:
            NotImplementedError: Diese Methode ist nicht implementiert.
        """
        raise NotImplementedError("achat not implemented")

    async def acomplete(self, *args: Any, **kwargs: Any) -> Any:
        """Async Completion ist nicht implementiert.

        Args:
            *args: Positionsargumente.
            **kwargs: Keyword-Argumente.

        Raises:
            NotImplementedError: Diese Methode ist nicht implementiert.
        """
        raise NotImplementedError("acomplete not implemented")

    @property
    def model(self) -> str:
        """Gibt den Modellnamen zurück.

        Returns:
            Name des verwendeten Modells.

        Raises:
            ValueError: Wenn kein Client gesetzt ist.
        """
        if self.client is None:
            raise ValueError("LLMClient instance must be provided")
        return self.client.llm

    @property
    def metadata(self) -> LLMMetadata:
        """Gibt Metadaten über das LLM zurück.

        Returns:
            LLMMetadata-Objekt mit Modell-Informationen.

        Raises:
            ValueError: Wenn kein Client gesetzt ist.
        """
        if self.client is None:
            raise ValueError("LLMClient instance must be provided")

        return LLMMetadata(
            context_window=2048,
            num_output=512,
            is_chat_model=True,
            model_name=self.model,
        )

    def __repr__(self) -> str:
        """String-Repräsentation des Adapters.

        Returns:
            String mit Client-Informationen.
        """
        if self.client:
            return f"LLMClientAdapter(client={self.client})"
        return "LLMClientAdapter(client=None)"
