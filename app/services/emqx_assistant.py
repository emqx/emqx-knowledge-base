"""Service for EMQX Assistant workflows."""

import logging
import traceback
import time
from typing import List, Union
import os

from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.workflow import (
    Event,
    StartEvent,
    StopEvent,
    Workflow,
    step,
    Context,
    InputRequiredEvent,
    HumanResponseEvent,
)
from llama_index.core.tools import FunctionTool

from app.utils.emqx_api import EmqxToolWrapper
from app.utils.network import check_port_available, get_ping_response_time

# Import the OpenAI embeddings
from llama_index.embeddings.openai import OpenAIEmbedding

from app.models.knowledge import KnowledgeResponse, FileAttachment
from app.services.database import db_service
from app.config import config

logger = logging.getLogger(__name__)


class EmqxQuestionEvent(Event):
    """Event for EMQX question."""

    question: str
    file_attachments: List[FileAttachment] = []


class EmqxContextEvent(Event):
    """Event with EMQX context information."""

    question: str
    context: str
    file_attachments: List[FileAttachment] = []


class EmqxBrokerContextEvent(Event):
    """Event with EMQX broker context information."""

    question: str
    context: str
    broker_context: str = ""
    file_attachments: List[FileAttachment] = []


class EmqxLogAnalysisEvent(Event):
    """Event for EMQX log analysis."""

    log_data: str
    file_attachments: List[FileAttachment] = []


class ContextForLogAnalysisEvent(Event):
    """Event for gathering context for log analysis."""

    question: str
    log_data: str
    file_attachments: List[FileAttachment] = []


class ContextForEmqxQuestionEvent(Event):
    """Event for gathering context for EMQX question."""

    question: str
    file_attachments: List[FileAttachment] = []


class EmqxContextForLogAnalysis(Event):
    """Event with context for log analysis."""

    question: str
    log_data: str
    context: str
    file_attachments: List[FileAttachment] = []


class EmqxContextForQuestion(Event):
    """Event with context for question."""

    question: str
    context: str
    file_attachments: List[FileAttachment] = []


class QueryEmqxContextForLogAnalysis(Event):
    """Event for querying EMQX broker for log analysis context."""

    question: str
    log_data: str
    context: str
    file_attachments: List[FileAttachment] = []


class QueryEmqxContextForQuestion(Event):
    """Event for querying EMQX broker for question context."""

    question: str
    context: str
    file_attachments: List[FileAttachment] = []


class AnalyzeLogWithContext(Event):
    """Event for analyzing logs with context."""

    question: str
    log_data: str
    context: str
    broker_context: str = ""
    file_attachments: List[FileAttachment] = []


class AnswerQuestionWithContext(Event):
    """Event for answering question with context."""

    question: str
    context: str
    broker_context: str = ""
    file_attachments: List[FileAttachment] = []


class SessionManager:
    """Manages conversation sessions for EMQX Assistant workflows.

    This class provides a way to store and retrieve conversation sessions,
    which include workflow, context, and memory objects for EMQX Assistant.
    """

    def __init__(self, session_timeout=3600):  # Default 60 minute timeout
        """Initialize the session manager.

        Args:
            session_timeout: Time in seconds after which a session is considered expired.
        """
        self.sessions = {}
        self.session_timeout = session_timeout
        self.last_accessed = {}

    def create_session(
        self, session_id, llm, file_attachments=None, emqx_credentials=None
    ):
        """Create a new session.

        Args:
            session_id: Unique identifier for the session.
            llm: The LLM to use for this session.
            file_attachments: Optional list of file attachments.
            emqx_credentials: Optional dict with EMQX API credentials (not used currently).

        Returns:
            A tuple of (workflow, context, memory).
        """
        # Create a new memory for this session
        memory = ChatMemoryBuffer(token_limit=8000)

        # Set verbose based on config or log level
        is_debug = logger.getEffectiveLevel() <= logging.DEBUG
        is_verbose = config.llama_index_verbose or is_debug

        # Create a workflow
        workflow = EmqxAssistantWorkflow(
            timeout=120,
            verbose=is_verbose,
            llm=llm,
            memory=memory,
            file_attachments=file_attachments,
            emqx_credentials=emqx_credentials,
        )

        # Create a context
        ctx = Context(workflow)

        # Store the session
        self.sessions[session_id] = (workflow, ctx, memory)
        self.last_accessed[session_id] = time.time()

        return workflow, ctx, memory

    def get_session(self, session_id):
        """Get an existing session.

        Args:
            session_id: Unique identifier for the session.

        Returns:
            A tuple of (workflow, context, memory) or None if the session doesn't exist
            or has expired.
        """
        if session_id not in self.sessions:
            return None

        # Check if the session has expired
        if time.time() - self.last_accessed[session_id] > self.session_timeout:
            self.delete_session(session_id)
            return None

        # Update last accessed time
        self.last_accessed[session_id] = time.time()

        return self.sessions[session_id]

    def refresh_session(self, session_id):
        """Refresh a session by updating its last accessed time.

        Args:
            session_id: Unique identifier for the session.

        Returns:
            True if the session was refreshed, False if it doesn't exist.
        """
        if session_id in self.last_accessed:
            self.last_accessed[session_id] = time.time()
            return True
        return False

    def delete_session(self, session_id):
        """Delete a session.

        Args:
            session_id: Unique identifier for the session.
        """
        if session_id in self.sessions:
            del self.sessions[session_id]

        if session_id in self.last_accessed:
            del self.last_accessed[session_id]

    def cleanup_expired_sessions(self):
        """Clean up expired sessions."""
        current_time = time.time()
        expired_sessions = [
            session_id
            for session_id, last_accessed in self.last_accessed.items()
            if current_time - last_accessed > self.session_timeout
        ]

        for session_id in expired_sessions:
            self.delete_session(session_id)


class EmqxAssistantWorkflow(Workflow):
    """Workflow for answering questions and analyzing logs for EMQX."""

    def __init__(
        self,
        llm,
        memory=None,
        file_attachments=None,
        emqx_credentials=None,
        *args,
        **kwargs,
    ):
        """Initialize the EMQX Assistant workflow.

        Args:
            llm: The language model to use for answering questions
            memory: Optional chat memory buffer for context
            file_attachments: Optional list of file attachments
            emqx_credentials: Optional dict with EMQX API credentials
            *args: Additional arguments
            **kwargs: Additional keyword arguments
        """
        self.memory = memory or ChatMemoryBuffer(token_limit=8000)
        self.file_attachments = file_attachments or []

        # Store EMQX credentials if provided
        self.emqx_credentials = (
            emqx_credentials if isinstance(emqx_credentials, dict) else {}
        )

        # Load prompts
        self.SYSTEM_PROMPT = load_prompt("system_prompt.txt")
        self.LOG_ANALYSIS_PROMPT = load_prompt("log_analysis_prompt.txt")
        self.LOG_DETECTION_PROMPT = load_prompt("log_detection_prompt.txt")
        self.LOG_DETECTION_USER_PROMPT = load_prompt("log_detection_user_prompt.txt")
        self.CREDENTIALS_EXTRACTION_PROMPT = load_prompt(
            "credentials_extraction_prompt.txt"
        )
        self.BROKER_AGENT_PROMPT = load_prompt("broker_agent_prompt.txt")
        self.EMQX_TOOL_PROMPT = load_prompt("emqx_tool_prompt.txt")
        self.BROKER_CONNECTION_ERROR = load_prompt("broker_connection_error.txt")

        # Initialize the LLM
        self.llm = llm
        if self.llm is None:
            try:
                from llama_index.llms.openai import OpenAI

                self.llm = OpenAI(model="gpt-4o")
                logger.info("LLM initialized in workflow")
            except Exception as e:
                logger.error(f"Error initializing LLM in workflow: {e}")
                # Make sure we have at least a placeholder LLM
                from llama_index.llms.base import BaseLLM

                self.llm = BaseLLM()

        # Initialize the embedding model
        try:
            self.embed_model = OpenAIEmbedding()
        except Exception as e:
            logger.error(f"Error initializing embedding model in workflow: {e}")
            self.embed_model = None

        # Set verbose flag based on config or log level
        is_debug = logger.getEffectiveLevel() <= logging.DEBUG
        is_verbose = config.llama_index_verbose or is_debug
        kwargs["verbose"] = kwargs.get("verbose", is_verbose)

        # Set a reasonable timeout if not specified
        kwargs["timeout"] = kwargs.get("timeout", 120)

        # Initialize the parent workflow
        super().__init__(*args, **kwargs)

        logger.info(
            "EMQX Assistant workflow initialized with timeout=%s, verbose=%s",
            kwargs.get("timeout"),
            kwargs.get("verbose"),
        )

    @step
    async def start(
        self, ctx: Context, ev: StartEvent
    ) -> Union[ContextForLogAnalysisEvent, ContextForEmqxQuestionEvent, StopEvent]:
        """Initial step to process the user's question and determine if it's a log analysis request or a question."""
        # Store the user input in memory
        self.memory.put(ChatMessage(role=MessageRole.USER, content=ev.user_input))

        # Check if there's content in any file attachments
        content_in_attachments = False
        for attachment in self.file_attachments:
            if (
                hasattr(attachment, "content_text")
                and attachment.content_text
                and len(attachment.content_text) > 200
            ):
                content_in_attachments = True
                logger.info(
                    f"File attachment with substantial content detected: {attachment.file_name}"
                )
                break

        # If there are file attachments with content, assume it's log data
        if content_in_attachments:
            logger.info("Treating file attachments as log data")
            for attachment in self.file_attachments:
                if hasattr(attachment, "content_text") and attachment.content_text:
                    # Use the file content as log data
                    logger.info(
                        f"Using file content from {attachment.file_name} as log data"
                    )
                    return ContextForLogAnalysisEvent(
                        question=ev.user_input,
                        log_data=attachment.content_text,
                        file_attachments=self.file_attachments,
                    )

        # Verify LLM is initialized
        if not self.llm:
            logger.error("LLM is not initialized in start step")
            return StopEvent(
                message="Error: LLM is not initialized. Please try again later."
            )

        # Extract any EMQX credentials from the user input (saving for later)
        system_prompt = self.CREDENTIALS_EXTRACTION_PROMPT

        chat_history = [
            ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
            ChatMessage(
                role=MessageRole.USER,
                content=f"Extract EMQX credentials if present:\n\n{ev.user_input}",
            ),
        ]

        # Try to extract credentials
        credentials_response = await self.llm.achat(chat_history)
        credentials_text = credentials_response.message.content.strip()

        # Check if credentials were found
        if credentials_text != "NO_CREDENTIALS" and "{" in credentials_text:
            # Try to parse the JSON response
            try:
                # Extract the JSON part
                import json
                import re

                # Find JSON object in the text
                json_match = re.search(r"\{.*\}", credentials_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                    credentials = json.loads(json_str)

                    # Validate the credentials have the required fields
                    if all(
                        k in credentials
                        for k in ["api_endpoint", "username", "password"]
                    ):
                        logger.info("EMQX credentials extracted from user message")
                        # Store the credentials
                        self.emqx_credentials = credentials
                    else:
                        logger.info("Incomplete credentials extracted, ignoring")
                else:
                    logger.info("No valid JSON found in credentials response")
            except Exception as e:
                logger.error(f"Error parsing credentials JSON: {e}")
        else:
            logger.info("No credentials found in user message")

        # Use the LLM to detect if this is log data
        ctx.write_event_to_stream(
            Event(metadata={"type": "status", "data": "Analyzing input..."})
        )

        # Create a system prompt for log detection
        system_prompt = self.LOG_DETECTION_PROMPT

        # Load and format the user prompt template
        user_prompt = self.LOG_DETECTION_USER_PROMPT.replace("{input}", ev.user_input)

        # Check if any file attachments contain log data
        if self.file_attachments:
            user_prompt += "\nAlso, check these file attachments for log data:\n"
            for attachment in self.file_attachments:
                if hasattr(attachment, "content_text") and attachment.content_text:
                    file_preview = (
                        attachment.content_text[:500] + "..."
                        if len(attachment.content_text) > 500
                        else attachment.content_text
                    )
                    user_prompt += (
                        f"\nFile: {attachment.file_name}\nPreview: {file_preview}\n"
                    )

        # Create chat history
        chat_history = [
            ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
            ChatMessage(role=MessageRole.USER, content=user_prompt),
        ]

        # Get response from LLM
        response = await self.llm.achat(chat_history)
        detection_result = response.message.content.strip().upper()

        logger.info(f"Log detection result: {detection_result}")

        # Determine if this is log data
        is_log_data = "YES" in detection_result

        if is_log_data:
            return ContextForLogAnalysisEvent(
                question=ev.user_input,
                log_data=ev.user_input,
                file_attachments=self.file_attachments,
            )
        else:
            return ContextForEmqxQuestionEvent(
                question=ev.user_input,
                file_attachments=self.file_attachments,
            )

    @step
    async def gather_context(
        self,
        ctx: Context,
        ev: Union[ContextForLogAnalysisEvent, ContextForEmqxQuestionEvent],
    ) -> Union[EmqxContextForLogAnalysis, EmqxContextForQuestion]:
        """Gather context for answering the question or analyzing logs."""
        # Get the question from the event
        question = ev.question

        # Let the user know we're gathering context
        ctx.write_event_to_stream(
            Event(
                metadata={
                    "type": "status",
                    "data": "Searching knowledge base for relevant information...",
                }
            )
        )

        # Create embedding for the question
        question_embedding = self.create_embedding(question)

        # Search for similar entries in the knowledge base with a lower threshold for broader coverage
        similar_entries = db_service.find_similar_entries(
            question_embedding, threshold=0.5, limit=10
        )

        # Find similar file attachments if we don't have any attached to this question
        file_attachments = ev.file_attachments or []

        # Always search for similar file attachments to supplement the context
        similar_files = db_service.find_similar_file_attachments(
            question_embedding, threshold=0.5, limit=5
        )

        # Add unique files that aren't already in file_attachments
        for file, similarity in similar_files:
            if not any(
                existing_file.id == file.id
                for existing_file in file_attachments
                if hasattr(existing_file, "id") and existing_file.id is not None
            ):
                logger.info(
                    f"Adding similar file attachment: {file.file_name} (similarity: {similarity:.2f})"
                )
                file_attachments.append(file)

        # Gather context from the knowledge base
        context = ""
        if similar_entries:
            context += "## Relevant Knowledge Base Entries\n\n"
            for entry, similarity in similar_entries:
                # Include more context from each entry for better understanding
                snippet = (
                    entry.content[:500] + "..."
                    if len(entry.content) > 500
                    else entry.content
                )
                context += f"**Entry {entry.id}** (Similarity: {similarity:.2f}):\n{snippet}\n\n"

        # Add file attachments
        if file_attachments:
            context += "## Relevant Files\n\n"
            for file in file_attachments:
                context += f"**File: {file.file_name}**\n"
                if hasattr(file, "content_summary") and file.content_summary:
                    context += f"Summary: {file.content_summary}\n"
                if (
                    hasattr(file, "content_text")
                    and file.content_text
                    and len(file.content_text) > 0
                ):
                    content_preview = (
                        file.content_text[:300] + "..."
                        if len(file.content_text) > 300
                        else file.content_text
                    )
                    context += f"Content: {content_preview}\n"
                context += "\n"

        # If we couldn't gather any context, inform the user
        if not context:
            context = "No relevant information found in the knowledge base."

        # Return appropriate event based on the source event type
        if isinstance(ev, ContextForLogAnalysisEvent):
            return EmqxContextForLogAnalysis(
                question=question,
                log_data=ev.log_data,
                context=context,
                file_attachments=file_attachments,
            )
        else:
            return EmqxContextForQuestion(
                question=question, context=context, file_attachments=file_attachments
            )

    @step
    async def extract_emqx_credentials(
        self, ctx: Context, ev: Union[EmqxContextForLogAnalysis, EmqxContextForQuestion]
    ) -> Union[
        QueryEmqxContextForLogAnalysis,
        QueryEmqxContextForQuestion,
        AnalyzeLogWithContext,
        AnswerQuestionWithContext,
    ]:
        """Extract EMQX credentials from the input if available."""
        # Check if we already have credentials (extracted in the start step)
        if self.emqx_credentials and all(
            k in self.emqx_credentials for k in ["api_endpoint", "username", "password"]
        ):
            # If we have credentials, proceed to query EMQX broker
            if isinstance(ev, EmqxContextForLogAnalysis):
                return QueryEmqxContextForLogAnalysis(
                    question=ev.question,
                    log_data=ev.log_data,
                    context=ev.context,
                    file_attachments=ev.file_attachments,
                )
            else:
                return QueryEmqxContextForQuestion(
                    question=ev.question,
                    context=ev.context,
                    file_attachments=ev.file_attachments,
                )
        else:
            # If no credentials, skip to final analysis/answer step
            if isinstance(ev, EmqxContextForLogAnalysis):
                return AnalyzeLogWithContext(
                    question=ev.question,
                    log_data=ev.log_data,
                    context=ev.context,
                    broker_context="",
                    file_attachments=ev.file_attachments,
                )
            else:
                return AnswerQuestionWithContext(
                    question=ev.question,
                    context=ev.context,
                    broker_context="",
                    file_attachments=ev.file_attachments,
                )

    @step
    async def query_emqx_broker(
        self,
        ctx: Context,
        ev: Union[QueryEmqxContextForLogAnalysis, QueryEmqxContextForQuestion],
    ) -> Union[AnalyzeLogWithContext, AnswerQuestionWithContext]:
        """Query the EMQX broker for context information."""
        # Initialize broker_context
        broker_context = ""

        try:
            # Let the user know we're querying the broker
            ctx.write_event_to_stream(
                Event(metadata={"type": "status", "data": "Checking EMQX broker..."})
            )

            # Import required modules
            from llama_index.core.agent.workflow import AgentWorkflow

            # Extract credentials once before creating tools
            tool_wrapper = EmqxToolWrapper(
                endpoint=self.emqx_credentials.get("api_endpoint", ""),
                username=self.emqx_credentials.get("username", ""),
                password=self.emqx_credentials.get("password", ""),
            )

            # Create a system prompt
            system_prompt = self.EMQX_TOOL_PROMPT

            # Set verbose flag based on config or log level
            is_debug = logger.getEffectiveLevel() <= logging.DEBUG
            is_verbose = config.llama_index_verbose or is_debug

            # Create the AgentWorkflow
            broker_agent = AgentWorkflow.from_tools_or_functions(
                [
                    FunctionTool.from_defaults(fn=tool_wrapper.get_connector_info),
                    FunctionTool.from_defaults(fn=tool_wrapper.get_cluster_info),
                    FunctionTool.from_defaults(fn=tool_wrapper.get_authentication_info),
                    FunctionTool.from_defaults(fn=check_port_available),
                    FunctionTool.from_defaults(fn=get_ping_response_time),
                ],
                llm=self.llm,
                system_prompt=system_prompt,
                verbose=is_verbose,
            )

            # Parse host for display
            user_prompt = f"""
            Get the emqx 1) cluster information 2) connector or
            authentication information.  The 'connector ID' or
            "authentication ID " field can be extracted from JSON
            block of {ev.question}
            """

            # Run the agent to collect broker information
            broker_response = await broker_agent.run(user_msg=user_prompt)

            # Create a user prompt for network tools
            network_prompt = f"""
            If there are some possible network issues for server
            resources, please use the supplied network tools to get
            more detailed information to diagonse. Such as ping and
            telnet tools. The related host and port information can be
            extracted from JSON block of {ev.question}. If host and port
            cannot be extracted, then skip this step directly.
            """

            # Run the agent again for network analysis
            network_response = await broker_agent.run(user_msg=network_prompt)

            # Combine the responses
            combined_response = (
                f"{broker_response}\n\nNetwork Analysis:\n{network_response}"
            )
            broker_context = combined_response

        except Exception as e:
            logger.error(f"Error getting broker context: {e}")
            logger.error(traceback.format_exc())

            # Create a more user-friendly error message for connection failures
            broker_context = self.BROKER_CONNECTION_ERROR

        # Always send the broker context to the stream, regardless of success or failure
        ctx.write_event_to_stream(
            Event(metadata={"type": "broker_info", "data": broker_context})
        )
        logger.info("Broker context event sent to stream")

        # Return the appropriate event type with the broker context
        if isinstance(ev, QueryEmqxContextForLogAnalysis):
            return AnalyzeLogWithContext(
                question=ev.question,
                log_data=ev.log_data,
                context=ev.context,
                broker_context=broker_context,
                file_attachments=ev.file_attachments,
            )
        else:
            return AnswerQuestionWithContext(
                question=ev.question,
                context=ev.context,
                broker_context=broker_context,
                file_attachments=ev.file_attachments,
            )

    @step
    async def analyze_log_with_context(
        self, ctx: Context, ev: AnalyzeLogWithContext
    ) -> StopEvent:
        """Analyze logs with context information."""
        # Let the user know we're analyzing logs
        ctx.write_event_to_stream(
            Event(metadata={"type": "status", "data": "Analyzing logs..."})
        )

        # Log that we're analyzing logs
        logger.info(
            f"Analyzing logs: content length={len(ev.log_data)}, question={ev.question}"
        )
        ctx.write_event_to_stream(
            Event(metadata={"type": "clear", "data": "log_analysis"})
        )

        # Prepare the context information
        context_info = ev.context

        # Add broker context if available
        if ev.broker_context:
            context_info += "\n\n## Real-time EMQX Broker Information\n\n"
            context_info += ev.broker_context

        # Use the specialized log analysis prompt
        system_prompt = self.LOG_ANALYSIS_PROMPT
        user_prompt = f"""
        EMQX Logs to analyze:
        ```
        {ev.log_data}
        ```

        Additional Context Information (if helpful for your analysis):
        {context_info}

        Please provide a detailed analysis of these logs according to the guidelines.
        """

        # Add the messages to memory
        self.memory.put(ChatMessage(role=MessageRole.SYSTEM, content=system_prompt))
        self.memory.put(ChatMessage(role=MessageRole.USER, content=user_prompt))

        # Get chat history
        chat_history = self.memory.get()

        # Stream the response token by token
        response = ""

        # Use astream_chat to get streaming tokens
        handle = await self.llm.astream_chat(chat_history)

        # Stream each token to the client and collect the response
        async for token in handle:
            logger.debug(f"Token: {token.delta}")
            response += token.delta

            # Stream each token to the event stream
            ctx.write_event_to_stream(Event(token=token.delta))

        # Store the complete response in memory
        self.memory.put(ChatMessage(role=MessageRole.ASSISTANT, content=response))

        # Return the StopEvent with the complete message and broker_context
        return StopEvent(message=response, broker_context=ev.broker_context)

    @step
    async def answer_question_with_context(
        self, ctx: Context, ev: AnswerQuestionWithContext
    ) -> StopEvent:
        """Answer EMQX question with context information."""
        # Let the user know we're answering the question
        ctx.write_event_to_stream(
            Event(metadata={"type": "status", "data": "Answering your question..."})
        )

        # Prepare the context information
        context_info = ev.context

        # Add broker context if available
        if ev.broker_context:
            context_info += "\n\n## Real-time EMQX Broker Information\n\n"
            context_info += ev.broker_context

        # Use the standard system prompt
        system_prompt = self.SYSTEM_PROMPT
        user_prompt = f"""
        User input:
        ```
        {ev.question}
        ```

        Context Information:
        {context_info}

        Please provide a comprehensive answer to the user's question based on the context information.
        """

        # Add the messages to memory
        self.memory.put(ChatMessage(role=MessageRole.SYSTEM, content=system_prompt))
        self.memory.put(ChatMessage(role=MessageRole.USER, content=user_prompt))

        # Get chat history
        chat_history = self.memory.get()

        # Stream the response token by token
        response = ""

        # Use astream_chat to get streaming tokens
        handle = await self.llm.astream_chat(chat_history)

        # Stream each token to the client and collect the response
        async for token in handle:
            logger.debug(f"Token: {token.delta}")
            response += token.delta

            # Stream each token to the event stream
            ctx.write_event_to_stream(Event(token=token.delta))

        # Store the complete response in memory
        self.memory.put(ChatMessage(role=MessageRole.ASSISTANT, content=response))

        # Return the StopEvent with the complete message and broker_context
        return StopEvent(message=response, broker_context=ev.broker_context)

    def create_embedding(self, text):
        """Create an embedding for the given text.

        Args:
            text: The text to create an embedding for.

        Returns:
            The embedding vector.
        """
        try:
            # Initialize the embedding model if needed
            if not hasattr(self, "embed_model") or self.embed_model is None:
                self.embed_model = OpenAIEmbedding()

            # Generate embedding
            embedding = self.embed_model.get_text_embedding(text)

            return embedding
        except Exception as e:
            logger.error(f"Error creating embedding in workflow: {e}")
            # Return a zero vector of appropriate length as fallback
            return [0.0] * 1536  # Default OpenAI embedding size

    def get_embeddings(self, text: str) -> List[float]:
        """Get embeddings for a text using the OpenAI model.

        Args:
            text: The text to get embeddings for

        Returns:
            The embeddings
        """
        try:
            # Check if there's an embedding model
            if self.embed_model:
                embeddings = self.embed_model.get_text_embedding(text)
                return embeddings

            # Otherwise return zeros
            return [0.0] * 1536  # Default OpenAI embedding size
        except Exception as e:
            logger.error(f"Error getting embeddings: {e}")
            return [0.0] * 1536  # Default OpenAI embedding size

    async def run(self, user_input: str, ctx: Context):
        """Run the workflow with the user's input.

        Args:
            user_input: The user's question or input
            ctx: The workflow context
        """
        # Create a start event with the user input
        start_event = StartEvent(user_input=user_input)

        # Start the workflow with default flow
        ev = await self.start(ctx, start_event)

        # Determine flow based on event type
        if isinstance(ev, ContextForLogAnalysisEvent) or isinstance(
            ev, ContextForEmqxQuestionEvent
        ):
            # Gather context
            context_ev = await self.gather_context(ctx, ev)

            # Extract credentials and determine next step
            cred_ev = await self.extract_emqx_credentials(ctx, context_ev)

            if isinstance(cred_ev, QueryEmqxContextForLogAnalysis) or isinstance(
                cred_ev, QueryEmqxContextForQuestion
            ):
                # Query EMQX broker
                final_ev = await self.query_emqx_broker(ctx, cred_ev)
            else:
                # Skip broker query
                final_ev = cred_ev

            # Final processing
            if isinstance(final_ev, AnalyzeLogWithContext):
                return await self.analyze_log_with_context(ctx, final_ev)
            elif isinstance(final_ev, AnswerQuestionWithContext):
                return await self.answer_question_with_context(ctx, final_ev)

        # If we reach here, it's likely a StopEvent due to an error
        return ev


class EmqxAssistantService:
    """Service for EMQX Assistant workflows."""

    def __init__(self):
        """Initialize the EMQX Assistant service."""
        self.session_manager = SessionManager(session_timeout=3600)
        self.llm = None

        # Load prompts
        self.SYSTEM_PROMPT = load_prompt("system_prompt.txt")
        self.LOG_ANALYSIS_PROMPT = load_prompt("log_analysis_prompt.txt")
        self.LOG_DETECTION_PROMPT = load_prompt("log_detection_prompt.txt")
        self.LOG_DETECTION_USER_PROMPT = load_prompt("log_detection_user_prompt.txt")
        self.CREDENTIALS_EXTRACTION_PROMPT = load_prompt(
            "credentials_extraction_prompt.txt"
        )
        self.BROKER_AGENT_PROMPT = load_prompt("broker_agent_prompt.txt")
        self.EMQX_TOOL_PROMPT = load_prompt("emqx_tool_prompt.txt")
        self.BROKER_CONNECTION_ERROR = load_prompt("broker_connection_error.txt")

        # Initialize the LLM immediately
        self._initialize_llm()

        # Initialize the OpenAI embedding model
        try:
            self.embed_model = OpenAIEmbedding()
        except Exception as e:
            logger.error(f"Error initializing embedding model: {e}")
            self.embed_model = None

    def _initialize_llm(self):
        """Initialize the LLM if not already initialized."""
        if not self.llm:
            try:
                from llama_index.llms.openai import OpenAI

                # Initialize the LLM
                self.llm = OpenAI(model="gpt-4o")
                logger.info("LLM initialized successfully")
            except Exception as e:
                logger.error(f"Error initializing LLM: {e}")

    async def process_input(
        self, question: str, session_id: str = None, file_attachments=None
    ) -> KnowledgeResponse:
        """Answer a question about EMQX or analyze logs using the EmqxAssistantWorkflow.

        Args:
            question: The question to answer or logs to analyze
            session_id: Optional session ID for continuing conversations
            file_attachments: Optional file attachments to include

        Returns:
            The knowledge response
        """
        try:
            # Make sure the LLM is initialized
            self._initialize_llm()

            if not self.llm:
                logger.warning("LLM not initialized. Generating a fallback response.")
                return KnowledgeResponse(
                    question=question,
                    answer="I'm unable to generate a response at the moment due to a configuration issue. Please try again later.",
                    sources=[],
                    file_sources=[],
                )

            # Create embedding for the question to find possible sources
            question_embedding = self.create_embedding(question)

            # Find similar entries in the knowledge base
            similar_entries = db_service.find_similar_entries(
                question_embedding, threshold=0.5, limit=8
            )

            # Find similar file attachments if none were provided
            provided_file_attachments = file_attachments or []

            # Get similar files from the database
            similar_files = db_service.find_similar_file_attachments(
                question_embedding, threshold=0.5, limit=5
            )

            # Combine provided files with similar files, avoiding duplicates
            all_file_attachments = list(provided_file_attachments)
            for file, similarity in similar_files:
                if not any(
                    existing_file.id == file.id
                    for existing_file in provided_file_attachments
                    if hasattr(existing_file, "id") and existing_file.id is not None
                ):
                    logger.info(
                        f"Adding similar file attachment: {file.file_name} (similarity: {similarity:.2f})"
                    )
                    all_file_attachments.append(file)

            # Check if we have an existing session
            session = None
            if session_id:
                session = self.session_manager.get_session(session_id)

            # If no session exists, create a new one
            if not session:
                if not session_id:
                    session_id = f"qa_{int(time.time())}"

                workflow, ctx, memory = self.session_manager.create_session(
                    session_id=session_id,
                    llm=self.llm,
                    file_attachments=all_file_attachments,
                )
            else:
                workflow, ctx, memory = session
                # Add file attachments to the existing workflow
                workflow.file_attachments = all_file_attachments

            # Run the workflow with the question
            handler = await workflow.run(user_input=question, ctx=ctx)

            # Process the events
            result = ""
            sources = []
            file_sources = []

            # If handler is a StopEvent, extract the message directly
            if isinstance(handler, StopEvent):
                result = getattr(handler, "message", "")
            else:
                # Otherwise, it's a workflow handler with stream_events
                async for event in handler.stream_events():
                    if isinstance(event, StopEvent):
                        result = getattr(event, "message", "")
                    elif isinstance(event, InputRequiredEvent):
                        # In this API implementation, we can't interact with the user directly
                        # So we'll auto-respond with a default value
                        handler.ctx.send_event(HumanResponseEvent(response=""))
                    elif (
                        isinstance(event, Event)
                        and hasattr(event, "token")
                        and event.token
                    ):
                        # If we have token streaming (for UI), we could handle that here
                        pass

                # Wait for the handler to complete
                await handler

            # Extract source information from similar entries
            for entry, similarity in similar_entries:
                if similarity > 0.6:  # Only include sources with good similarity
                    sources.append(entry)

            # Extract file sources from the attachments used
            for file in all_file_attachments:
                file_sources.append(file)

            # Create a response with the result and sources
            return KnowledgeResponse(
                question=question,
                answer=result or "I couldn't generate an answer to your question.",
                sources=sources,
                file_sources=file_sources,
            )

        except Exception as e:
            logger.error(f"Error in process_input: {e}")
            logger.error(traceback.format_exc())
            return KnowledgeResponse(
                question=question,
                answer=f"I encountered an error while processing your question: {str(e)}",
                sources=[],
                file_sources=[],
            )

    def create_embedding(self, text):
        """Create an embedding for the given text.

        Args:
            text: The text to create an embedding for.

        Returns:
            The embedding vector.
        """
        try:
            # Initialize the embedding model if needed
            if not hasattr(self, "embed_model") or self.embed_model is None:
                self.embed_model = OpenAIEmbedding()

            # Generate embedding
            embedding = self.embed_model.get_text_embedding(text)

            return embedding
        except Exception as e:
            logger.error(f"Error creating embedding in service: {e}")
            # Return a zero vector of appropriate length as fallback
            return [0.0] * 1536  # Default OpenAI embedding size


def load_prompt(filename):
    """Load a prompt from a file.

    Args:
        filename: The name of the prompt file

    Returns:
        The prompt text
    """
    prompt_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "prompts", filename
    )
    try:
        with open(prompt_path, "r") as f:
            return f.read().strip()
    except Exception as e:
        logger.error(f"Error loading prompt from {prompt_path}: {e}")
        return "Error loading prompt."


# Create a global instance of the service
emqx_assistant_service = EmqxAssistantService()
