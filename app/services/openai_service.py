"""Service for interacting with OpenAI API."""
import logging
import re
from typing import List
import traceback

from openai import OpenAI

from app.config import config
from app.models.knowledge import KnowledgeEntry, KnowledgeResponse, FileAttachment

logger = logging.getLogger(__name__)


class OpenAIService:
    """Service for interacting with OpenAI API."""

    def __init__(self):
        """Initialize the OpenAI service."""
        try:
            if not config.openai_api_key:
                logger.warning("OpenAI API key is not set. Using mock responses.")
                self.client = None
            else:
                self.client = OpenAI(api_key=config.openai_api_key)
                logger.debug("OpenAI client initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing OpenAI client: {e}")
            logger.error(traceback.format_exc())
            self.client = None

    def create_embedding(self, text: str) -> List[float]:
        """Create an embedding for the given text.

        Args:
            text: The text to create an embedding for.

        Returns:
            The embedding vector.
        """
        try:
            if self.client is None:
                logger.warning("OpenAI client not initialized. Returning mock embedding.")
                return [0.1] * config.embedding_dimension

            logger.debug(f"Creating embedding for text: {text[:50]}...")

            # Wrap the actual API call in its own try-except block
            try:
                response = self.client.embeddings.create(
                    model=config.embedding_model,
                    input=text,
                )
                logger.debug("Embedding API call completed successfully")
                return response.data[0].embedding
            except Exception as api_error:
                logger.error(f"OpenAI API call failed: {api_error}")
                logger.error(traceback.format_exc())
                # Return a mock embedding as fallback
                return [0.1] * config.embedding_dimension

        except Exception as e:
            logger.error(f"Error creating embedding: {e}")
            logger.error(traceback.format_exc())
            # Return a mock embedding as fallback
            return [0.1] * config.embedding_dimension

    def generate_response(
        self, question: str, context_entries: List[KnowledgeEntry], file_attachments: List[FileAttachment] = None
    ) -> KnowledgeResponse:
        """Generate a response to a question using OpenAI's Response API.

        Args:
            question: The question to answer.
            context_entries: Knowledge entries to use as context.
            file_attachments: File attachments to use as additional context.

        Returns:
            The generated response.
        """
        # Initialize file_attachments if None
        if file_attachments is None:
            file_attachments = []

        # Check if OpenAI client is initialized
        if self.client is None:
            logger.warning("OpenAI client not initialized. Returning mock response.")
            return KnowledgeResponse(
                question=question,
                answer=f"This is a mock response to your question: '{question}'. OpenAI API key is not configured.",
                sources=context_entries,
                file_sources=file_attachments,
                confidence=0.5,
            )

        # Prepare context from knowledge entries
        context = "\n\n".join(
            [f"Source {i+1}:\n{entry.content}" for i, entry in enumerate(context_entries)]
        )

        # Prepare context from file attachments
        file_context = ""
        if file_attachments:
            file_summaries = []
            for i, attachment in enumerate(file_attachments):
                summary = f"File {i+1}: {attachment.file_name} - {attachment.content_summary}"
                if attachment.content_text and len(attachment.content_text) > 0:
                    # Add a snippet of the content if available
                    content_snippet = attachment.content_text[:300] + "..." if len(attachment.content_text) > 300 else attachment.content_text
                    summary += f"\nContent snippet: {content_snippet}"
                file_summaries.append(summary)

            file_context = "File Attachments:\n" + "\n\n".join(file_summaries)

        # Check if the question is about a specific EMQX version
        # Match patterns like "EMQX 4.3", "v4.3.10", "version 5.0", etc.
        version_patterns = [
            r"emqx\s+v?(\d+\.\d+(?:\.\d+)?)",  # EMQX 4.3 or EMQX v4.3
            r"v(\d+\.\d+(?:\.\d+)?)",  # v4.3 or v4.3.10
            r"version\s+(\d+\.\d+(?:\.\d+)?)",  # version 4.3
        ]

        version_specific_docs = ""
        version = None

        for pattern in version_patterns:
            match = re.search(pattern, question.lower())
            if match:
                version = match.group(1)
                break

        if version:
            # Determine if it's likely enterprise or open source based on the question
            if "enterprise" in question.lower() or "ee" in question.lower():
                version_specific_docs = f"{config.emqx_docs_enterprise_base}v{version}/"
                logger.info(f"Detected Enterprise version {version}, using docs: {version_specific_docs}")
            else:
                version_specific_docs = f"{config.emqx_docs_opensource_base}v{version}/"
                logger.info(f"Detected Open Source version {version}, using docs: {version_specific_docs}")

        # Check if the question is about Kubernetes, K8s, or EMQX Operator
        is_k8s_related = any(term in question.lower() for term in ["kubernetes", "k8s", "operator", "helm", "chart", "cluster"])

        # Prepare the system message with documentation references
        system_message = (
            "You are a helpful assistant that answers questions about EMQX, an open-source, highly scalable, "
            "and distributed MQTT broker for IoT, M2M, and mobile applications. "
            "Use the information in the sources provided to answer the question. "
            "If the information needed is not in the sources, you can refer to the official EMQX documentation. "
            f"The latest EMQX documentation is available at: {config.emqx_docs_latest}\n"
        )

        # Add version-specific documentation if available
        if version_specific_docs:
            system_message += f"For version {version} specific information, refer to: {version_specific_docs}\n"

        # Add EMQX Operator documentation if the question is related to Kubernetes
        if is_k8s_related:
            system_message += f"For EMQX Kubernetes Operator documentation, refer to: {config.emqx_operator_docs}\n"

        # Add release notes reference
        system_message += (
            f"Release notes for EMQX are available at: {config.emqx_release_notes}\n\n"
            "If you reference the documentation, include the relevant documentation links in your answer. "
            "If you cannot find the information in the sources or documentation, say 'I don't have enough information to answer this question.'"
        )

        try:
            # Use the Response API to generate an answer
            response = self.client.responses.create(
                model=config.response_model,
                tools=[{"type": "web_search_preview"}],
                input=[
                    {"role": "system", "content": system_message},
                    {"role": "developer", "content": f"Context: {context}"},
                    {"role": "developer", "content": f"File Context: {file_context}" if file_context else "No file attachments provided."},
                    {"role": "user", "content": f"Question: {question}"}
                ]
            )

            # Calculate a simple confidence score based on the model's response
            confidence = 0.8  # Default confidence
            if "I don't have enough information" in response.output_text:
                confidence = 0.2

            return KnowledgeResponse(
                question=question,
                answer=response.output_text,
                sources=context_entries,
                file_sources=file_attachments,
                confidence=confidence,
            )
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            # Return a fallback response
            return KnowledgeResponse(
                question=question,
                answer="I'm sorry, I encountered an error while trying to answer your question.",
                sources=[],
                file_sources=[],
                confidence=0.0,
            )


# Create a global OpenAI service instance
openai_service = OpenAIService()
