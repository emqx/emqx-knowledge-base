"""Service for interacting with LlamaIndex."""
import logging
import os
import urllib.request
import json
import base64
from typing import List, Optional, Dict, Any
import asyncio
import contextlib
from functools import wraps
import time

from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.llms.openai import OpenAI
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.agent.workflow import AgentWorkflow
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
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, Document
from llama_index.core.schema import TextNode

# Import additional LLM providers
try:
    from llama_index.llms.anthropic import Anthropic
except ImportError:
    Anthropic = None

try:
    from llama_index.llms.cohere import Cohere
except ImportError:
    Cohere = None

try:
    from llama_index.llms.gemini import Gemini
except ImportError:
    Gemini = None

try:
    from llama_index.llms.huggingface import HuggingFaceInferenceAPI
except ImportError:
    HuggingFaceInferenceAPI = None

from app.config import config
from app.models.knowledge import KnowledgeEntry, KnowledgeResponse, FileAttachment

logger = logging.getLogger(__name__)

@contextlib.asynccontextmanager
async def timeout_context(timeout_seconds, error_message="Operation timed out"):
    """Context manager for handling timeouts in async operations.

    Args:
        timeout_seconds: Number of seconds to wait before timing out.
        error_message: Message to include in the TimeoutError.

    Yields:
        None

    Raises:
        asyncio.TimeoutError: If the operation times out.
    """
    try:
        yield await asyncio.wait_for(asyncio.shield(asyncio.sleep(timeout_seconds)), timeout=timeout_seconds)
        # If we get here, the operation completed before the timeout
    except asyncio.TimeoutError:
        logger.warning(f"Timeout after {timeout_seconds} seconds: {error_message}")
        raise asyncio.TimeoutError(error_message)

def with_timeout(timeout_seconds, error_message="Operation timed out"):
    """Decorator for adding timeout to async functions.

    Args:
        timeout_seconds: Number of seconds to wait before timing out.
        error_message: Message to include in the TimeoutError.

    Returns:
        Decorated function.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_seconds)
            except asyncio.TimeoutError:
                logger.warning(f"Timeout after {timeout_seconds} seconds: {error_message}")
                raise asyncio.TimeoutError(error_message)
        return wrapper
    return decorator

# Create auth token for EMQX API
def get_emqx_token():
    """Get a Bearer token for EMQX API authentication."""
    try:
        url = f'{config.emqx_base_url}/login'
        data = json.dumps({
            "username": config.emqx_username,
            "password": config.emqx_password
        }).encode()

        req = urllib.request.Request(url, data=data)
        req.add_header('Content-Type', 'application/json')

        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode())
            return result.get("token")
    except Exception as e:
        logger.error(f"Error getting EMQX token: {e}")
        return None

class LogEntryEvent(Event):
    """Event for log entry."""
    entry: str

class LogEntryWithContextEvent(LogEntryEvent):
    """Event for log entry with context."""
    log_context: str

# EMQX API functions
def query_emqx_cluster_info() -> str:
    """
    Return the EMQX cluster information for the server.

    The returned value includes EMQX version number, edition (such as open source or enterprise),
    cluster status (running or stopped), etc. It helps you to know the overall status of the EMQX cluster.

    Returns:
        A dictionary that represents the status of the cluster.
    """
    try:
        token = get_emqx_token()
        if not token:
            return {"error": "Failed to obtain authentication token"}

        # First, get basic node info
        nodes_url = f'{config.emqx_base_url}/nodes'
        nodes_req = urllib.request.Request(nodes_url)
        nodes_req.add_header('Content-Type', 'application/json')
        nodes_req.add_header('Authorization', f'Bearer {token}')

        logger.debug(f"Querying EMQX cluster info: {nodes_url}")

        nodes_data = {}
        with urllib.request.urlopen(nodes_req) as response:
            nodes_data = json.loads(response.read().decode())

        # Then, get stats
        stats_url = f'{config.emqx_base_url}/stats'
        stats_req = urllib.request.Request(stats_url)
        stats_req.add_header('Content-Type', 'application/json')
        stats_req.add_header('Authorization', f'Bearer {token}')

        logger.debug(f"Querying EMQX stats: {stats_url}")

        stats_data = {}
        with urllib.request.urlopen(stats_req) as response:
            stats_data = json.loads(response.read().decode())

        # And metrics
        metrics_url = f'{config.emqx_base_url}/metrics'
        metrics_req = urllib.request.Request(metrics_url)
        metrics_req.add_header('Content-Type', 'application/json')
        metrics_req.add_header('Authorization', f'Bearer {token}')

        logger.debug(f"Querying EMQX metrics: {metrics_url}")

        metrics_data = {}
        with urllib.request.urlopen(metrics_req) as response:
            metrics_data = json.loads(response.read().decode())

        # Combine the data
        return {
            "nodes": nodes_data,
            "stats": stats_data,
            "metrics": metrics_data
        }
    except Exception as e:
        logger.error(f"Error querying EMQX cluster info: {e}")
        return {"error": str(e)}

def query_emqx_connector_info(id: str) -> str:
    """
    Get information for EMQX connectors.

    The tag value for connectors starts with "CONNECTOR", such as "CONNECTOR/MYSQL".
    The EMQX connector is a key concept in data integration, serving as the underlying
    connection channel for Sink/Source, used to connect to external data systems.

    Args:
        id: The connector ID to query.

    Returns:
        A string that represents the status of the connector.
    """
    try:
        token = get_emqx_token()
        if not token:
            return {"error": "Failed to obtain authentication token"}

        url = f'{config.emqx_base_url}/connectors/{id}'
        logger.debug(f"Querying connector info: {url}")
        req = urllib.request.Request(url)
        req.add_header('Content-Type', 'application/json')
        req.add_header('Authorization', f'Bearer {token}')

        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())

        return data
    except Exception as e:
        logger.error(f"Error querying EMQX connector info: {e}")
        return {"error": str(e)}

def query_emqx_authentication_info(id: str) -> str:
    """
    Get information for EMQX authentications.

    The tag value for authentications starts with "AUTHN", such as "AUTHN/WEBHOOK".
    Authentication is the process of verifying the identity of a client.

    Args:
        id: The authentication ID to query.

    Returns:
        A string that represents the status of the authentication.
    """
    try:
        token = get_emqx_token()
        if not token:
            return {"error": "Failed to obtain authentication token"}

        url = f'{config.emqx_base_url}/authentication/{id}/status'
        logger.debug(f"Querying authentication info: {url}")
        req = urllib.request.Request(url)
        req.add_header('Content-Type', 'application/json')
        req.add_header('Authorization', f'Bearer {token}')

        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())

        return data
    except Exception as e:
        logger.error(f"Error querying EMQX authentication info: {e}")
        return {"error": str(e)}

class SessionManager:
    """Manages conversation sessions for LlamaIndex workflows.

    This class provides a way to store and retrieve conversation sessions,
    which include workflow, context, and memory objects.
    """

    def __init__(self, session_timeout=3600, log_analysis_class=None):  # Default 60 minute timeout
        """Initialize the session manager.

        Args:
            session_timeout: Time in seconds after which a session is considered expired.
            log_analysis_class: The LogAnalysis class to use for creating workflows.
        """
        self.sessions = {}
        self.session_timeout = session_timeout
        self.last_accessed = {}
        self.log_analysis_class = log_analysis_class

    def create_session(self, session_id, llm):
        """Create a new session.

        Args:
            session_id: Unique identifier for the session.
            llm: The LLM to use for this session.

        Returns:
            A tuple of (workflow, context, memory).
        """
        if self.log_analysis_class is None:
            raise ValueError("LogAnalysis class not set")

        # Create a new memory for this session
        memory = ChatMemoryBuffer(token_limit=8000)

        # Create a workflow
        workflow = self.log_analysis_class(timeout=60, verbose=True, llm=llm, memory=memory)

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
            session_id for session_id, last_accessed in self.last_accessed.items()
            if current_time - last_accessed > self.session_timeout
        ]

        for session_id in expired_sessions:
            self.delete_session(session_id)

class LlamaIndexService:
    """Service for interacting with LlamaIndex."""

    def __init__(self):
        """Initialize the LlamaIndex service."""
        self.llm = None
        self.memory = None
        self.session_manager = None

        # Initialize the LLM based on the provider
        if config.llm_api_key:
            self.llm = self._initialize_llm()
            if self.llm:
                self.memory = ChatMemoryBuffer(token_limit=8000)
                # Initialize the session manager after LogAnalysis is defined
                self.session_manager = SessionManager(log_analysis_class=self.LogAnalysis)
            else:
                logger.error(f"Failed to initialize LLM with provider: {config.llm_provider}")

    def _initialize_llm(self):
        """Initialize the LLM based on the provider configuration.

        Returns:
            An initialized LLM instance or None if initialization fails.
        """
        try:
            provider = config.llm_provider.lower()

            if provider == "openai":
                return OpenAI(
                    api_key=config.llm_api_key,
                    model=config.llm_model,
                    temperature=config.llm_temperature,
                )
            elif provider == "anthropic" and Anthropic:
                return Anthropic(
                    api_key=config.llm_api_key,
                    model=config.llm_model,
                    temperature=config.llm_temperature,
                )
            elif provider == "cohere" and Cohere:
                return Cohere(
                    api_key=config.llm_api_key,
                    model=config.llm_model,
                    temperature=config.llm_temperature,
                )
            elif provider == "gemini" and Gemini:
                return Gemini(
                    api_key=config.llm_api_key,
                    model=config.llm_model,
                    temperature=config.llm_temperature,
                )
            elif provider == "huggingface" and HuggingFaceInferenceAPI:
                return HuggingFaceInferenceAPI(
                    api_key=config.llm_api_key,
                    model_name=config.llm_model,
                    temperature=config.llm_temperature,
                )
            else:
                logger.warning(f"Unsupported LLM provider: {provider}. Falling back to OpenAI.")
                return OpenAI(
                    api_key=config.llm_api_key,
                    model=config.llm_model,
                    temperature=config.llm_temperature,
                )
        except Exception as e:
            logger.error(f"Error initializing LLM: {e}")
            return None

    def create_knowledge_index(self, knowledge_entries: List[KnowledgeEntry]) -> VectorStoreIndex:
        """Create a vector store index from knowledge entries.

        Args:
            knowledge_entries: List of knowledge entries to index.

        Returns:
            The vector store index.
        """
        documents = []
        for entry in knowledge_entries:
            doc = Document(
                text=entry.content,
                metadata={
                    "id": entry.id,
                    "title": entry.title,
                    "url": entry.url,
                    "source": entry.source,
                    "created_at": str(entry.created_at),
                    "updated_at": str(entry.updated_at),
                }
            )
            documents.append(doc)

        return VectorStoreIndex.from_documents(documents)

    def create_file_index(self, file_attachments: List[FileAttachment]) -> VectorStoreIndex:
        """Create a vector store index from file attachments.

        Args:
            file_attachments: List of file attachments to index.

        Returns:
            The vector store index.
        """
        documents = []
        for file in file_attachments:
            doc = Document(
                text=file.content,
                metadata={
                    "id": file.id,
                    "file_name": file.file_name,
                    "file_type": file.file_type,
                    "file_size": file.file_size,
                    "created_at": str(file.created_at),
                }
            )
            documents.append(doc)

        return VectorStoreIndex.from_documents(documents)

    async def generate_response(
        self,
        question: str,
        context_entries: List[KnowledgeEntry],
        file_attachments: Optional[List[FileAttachment]] = None
    ) -> KnowledgeResponse:
        """Generate a response to a question using LlamaIndex.

        Args:
            question: The question to answer.
            context_entries: The context entries to use.
            file_attachments: Optional file attachments to include.

        Returns:
            The knowledge response.
        """
        try:
            if self.llm is None:
                logger.warning("LlamaIndex service not initialized. Returning mock response.")
                return KnowledgeResponse(
                    answer=f"I'm sorry, but the LLM service is not properly initialized. Please check your {config.llm_provider} API key and configuration.",
                    sources=[],
                    file_sources=[]
                )

            # Create indices
            knowledge_index = self.create_knowledge_index(context_entries)

            # Create query engine
            query_engine = knowledge_index.as_query_engine()

            # If we have file attachments, create a separate index and query engine
            file_sources = []
            if file_attachments and len(file_attachments) > 0:
                file_index = self.create_file_index(file_attachments)
                file_query_engine = file_index.as_query_engine()
                file_response = file_query_engine.query(question)

                # Extract file sources
                for node in file_response.source_nodes:
                    file_id = node.metadata.get("id")
                    file_name = node.metadata.get("file_name")
                    file_type = node.metadata.get("file_type")

                    for file in file_attachments:
                        if file.id == file_id:
                            file_sources.append(file)
                            break

            # Query the knowledge base
            response = query_engine.query(question)

            # Extract sources
            sources = []
            for node in response.source_nodes:
                entry_id = node.metadata.get("id")
                for entry in context_entries:
                    if entry.id == entry_id:
                        sources.append(entry)
                        break

            return KnowledgeResponse(
                answer=str(response),
                sources=sources,
                file_sources=file_sources
            )
        except Exception as e:
            logger.error(f"Error generating response with LlamaIndex: {e}")
            return KnowledgeResponse(
                answer=f"I encountered an error while processing your question: {str(e)}",
                sources=[],
                file_sources=[]
            )

    class LogAnalysis(Workflow):
        """Workflow for log analysis."""

        def __init__(
                self,
                llm: OpenAI,
                memory: ChatMemoryBuffer = None,
                *args,
                **kwargs):
            """Initialize the LogAnalysis workflow.

            Args:
                llm: The language model to use for analysis
                memory: Optional chat memory buffer for context
                *args: Additional arguments
                **kwargs: Additional keyword arguments
            """
            self.llm = llm or None
            self.memory = memory or ChatMemoryBuffer(token_limit=8000)

            # Ensure the verbose flag is set to True for better debugging
            kwargs['verbose'] = kwargs.get('verbose', True)

            # Set a reasonable timeout if not specified
            kwargs['timeout'] = kwargs.get('timeout', 120)

            # Initialize the parent workflow
            super().__init__(*args, **kwargs)

            logger.info("LogAnalysis workflow initialized with timeout=%s, verbose=%s",
                        kwargs.get('timeout'), kwargs.get('verbose'))

        @step
        async def llm_extract_log(self, ctx: Context, ev: StartEvent) -> LogEntryEvent:
            """Extract log information from the input."""
            system_prompt = """
            You are an EMQX v5 Log Analyzer. Your task is to extract EMQX log entries, please follow these guidelines:

            ## General Log Analysis

            ### Input Structure
            EMQX v5 logs are typically structured with name: value pairs. When nested, they follow Erlang's map() format.

            ### Common Fields
            1. The msg field is in snake_case_format and is designed to be both human-friendly and indexer friendly.
            2. Additional fields such as hint, explain, and reason may be present to offer more context.
            3. For crash logs or caught exceptions, a stacktrace field may be included.

            ### Arbitrary Formats
            1. EMQX's software dependencies might not follow this logging convention, so be prepared to analyze logs in arbitrary formats.
            2. Component-Specific Considerations

            ### MQTT and Gateway Clients
            1. Logs emitted from MQTT clients or gateway clients will include metadata such as clientid, username, and peername.
            2. Data Integration Components:
            3. Logs from components like action, bridge, connector, and source may contain resource IDs (e.g., connector or action IDs).
              3.1. When such IDs are present, highlight the resource ID and advise the user to retrieve the corresponding configuration details (such as rule, action, or connector config) for further diagnosis.
            """

            # Store messages in memory for conversation history
            self.memory.put(ChatMessage(role=MessageRole.SYSTEM, content=system_prompt))
            self.memory.put(ChatMessage(role=MessageRole.USER, content=f'{ev.user_input}\nPlease extract EMQX log entries to a JSON block and give some suggestions for it.'))

            # Get chat history from memory
            chat_history = self.memory.get()

            # Stream the response
            response = ""
            handle = await self.llm.astream_chat(chat_history)
            async for token in handle:
                # In a real application, you would stream this to the client
                logger.debug(f"Token: {token.delta}")
                response += token.delta

                # Write the token to the stream for real-time updates
                ctx.write_event_to_stream(Event(token=token.delta))

            # Store the assistant's response in memory
            self.memory.put(ChatMessage(role=MessageRole.ASSISTANT, content=response))

            # Return the log entry event directly without asking for confirmation
            # This simplifies the flow and prevents hanging
            return LogEntryEvent(entry=response)

        @step
        async def query_emqx_context(self, ctx: Context, ev: LogEntryEvent) -> LogEntryWithContextEvent:
            """Query EMQX context information."""
            logger.debug("Querying EMQX context")
            system_prompt = """
            You are a helpful assistant that analyzes EMQX logs and retrieves relevant information from the EMQX API.
            Your task is to identify resource IDs in the log entry and use the provided tools to gather additional context.

            ## Guidelines:
            1. Use the query_emqx_cluster_info tool if the logs suggest general cluster issues or you need overall system status
            2. If connector IDs are found (format: connector:type:name), use query_emqx_connector_info for details
            3. If authentication IDs are found (format: emqx_authn_type:number or password_based:type), use query_emqx_authentication_info
            4. Format your response in a structured way, using markdown headings for each type of information
            5. Only call the tools that are relevant to the log entries being analyzed
            """

            # Create an agent workflow with the EMQX API functions as tools
            query_info = AgentWorkflow.from_tools_or_functions(
                [query_emqx_cluster_info, query_emqx_connector_info, query_emqx_authentication_info],
                llm=self.llm,
                system_prompt=system_prompt
            )

            # Run the agent workflow with the log entry
            user_msg = f"""
            Analyze these log entries and retrieve relevant contextual information:

            ```
            {ev.entry}
            ```

            Instructions:
            1. Only call tools that are relevant to the issues shown in the logs
            2. If you see connector issues, call query_emqx_connector_info with the connector ID
            3. If you see authentication issues, call query_emqx_authentication_info with the auth ID
            4. If you see general cluster issues or need system status, call query_emqx_cluster_info
            5. Format the response with clear markdown sections for each type of information

            Don't call tools unnecessarily if the information won't help diagnose the issues in the logs.
            """

            # Store this interaction in memory
            self.memory.put(ChatMessage(role=MessageRole.USER, content=user_msg))

            # Let the user know we're gathering context
            ctx.write_event_to_stream(Event(token="Analyzing logs and gathering relevant EMQX context... "))

            try:
                # Stream the response
                response_text = ""
                response = await query_info.run(user_msg=user_msg)
                response_text = str(response)

                # Store the response in memory
                self.memory.put(ChatMessage(role=MessageRole.ASSISTANT, content=response_text))

                # Check for specific tool information in the response to track what was used
                tool_usage = {
                    "cluster_info": "query_emqx_cluster_info" in response_text or "Cluster Information" in response_text,
                    "connector_info": "query_emqx_connector_info" in response_text or "Connector Information" in response_text,
                    "auth_info": "query_emqx_authentication_info" in response_text or "Authentication Information" in response_text
                }

                # Add a summary of what tools were used
                tools_summary = "\n\n## Tools Used for Context Gathering\n\n"
                if any(tool_usage.values()):
                    tools_summary += "The following tools were used to gather additional context:\n\n"
                    if tool_usage["cluster_info"]:
                        tools_summary += "- EMQX Cluster Information\n"
                    if tool_usage["connector_info"]:
                        tools_summary += "- EMQX Connector Information\n"
                    if tool_usage["auth_info"]:
                        tools_summary += "- EMQX Authentication Information\n"
                else:
                    tools_summary += "No additional context tools were used for this analysis."

                # Append the summary to the response
                response_text += tools_summary

                ctx.write_event_to_stream(Event(token="Context gathering complete."))

                return LogEntryWithContextEvent(entry=ev.entry, log_context=response_text)
            except Exception as e:
                logger.error(f"Error querying EMQX context: {e}")
                error_message = f"""## Error Querying EMQX Context

                An error occurred while gathering EMQX context information: {str(e)}
                """

                ctx.write_event_to_stream(Event(token=f"Error gathering context: {str(e)}"))

                return LogEntryWithContextEvent(entry=ev.entry, log_context=error_message)

        @step
        async def llm_analysis_log(self, ctx: Context, ev: LogEntryWithContextEvent) -> StopEvent:
            """Analyze the log entry and provide recommendations."""
            system_prompt = """
            You are an EMQX v5 Log Analyzer. Your task is to provide actionable troubleshooting advice, please follow these guidelines:

            ## Troubleshooting Steps

            ### Log Analysis
            1. Examine timestamps, error codes, and severity levels.
            2. Identify patterns or anomalies that indicate issues such as repeated errors, warnings, or unexpected behavior.

            ### Categorization
            1. Categorize log entries by type (e.g., connection issues, authentication failures, resource constraints, configuration errors, etc.).
            2. Summarize the key problem(s) detected for each category.

            ### EMQX Context Information
            1. Include ALL context information that was gathered from EMQX tools in a dedicated section.
            2. If cluster information was gathered, include it under "## EMQX Cluster Information"
            3. If connector information was gathered, include it under "## EMQX Connector Information"
            4. If authentication information was gathered, include it under "## EMQX Authentication Information"
            5. If no additional context was gathered, you can skip this section.

            ### Actionable Recommendations
            1. For each identified issue, provide a concise summary of the potential problem.
            2. Outline possible root causes based on the log details and any available context.
            3. Offer step-by-step troubleshooting or mitigation strategies.
            4. Suggest verifying network configurations, resource usage, or recent configuration changes where applicable.

            ### Audience Considerations
            1. Provide clear explanations that are accessible to both technical and non-technical users.
            2. Use technical language where needed for precision, but also include definitions or context for specialized terms.

            ### Formatting
            1. Start your analysis with the title "# EMQX Log Analysis - Final Report" to clearly indicate this is the comprehensive final analysis.
            2. Use Markdown formatting for headings, lists, and code blocks to improve readability.
            3. Include these sections in your report:
               - "## Detailed Analysis of Extracted EMQX Log Entries" (always include this)
               - Context sections for any tools that were used (if applicable)
               - "## Recommendations" (always include this)
            """

            # Detect which context tools were used
            tools_used = []
            if "EMQX Cluster Information" in ev.log_context:
                tools_used.append("cluster_info")
            if "EMQX Connector Information" in ev.log_context:
                tools_used.append("connector_info")
            if "EMQX Authentication Information" in ev.log_context:
                tools_used.append("auth_info")

            # Add to memory
            user_prompt = f"""
            Log information:
            ```
            {ev.entry}
            ```

            """

            # Only include the context information if tools were actually used
            if tools_used:
                user_prompt += f"""
            Additional context information from EMQX:
            ```
            {ev.log_context}
            ```

            Note: The above context information was gathered using EMQX API tools. Please incorporate ALL relevant details from it in your analysis.
            """
            else:
                user_prompt += "No additional context information was gathered from EMQX for this analysis.\n"

            user_prompt += """
            Please deliver a detailed analysis along with step-by-step troubleshooting recommendations.
            If context information from EMQX tools was provided, make sure to include it in dedicated sections in your report.
            """

            self.memory.put(ChatMessage(role=MessageRole.SYSTEM, content=system_prompt))
            self.memory.put(ChatMessage(role=MessageRole.USER, content=user_prompt))

            # Get chat history
            chat_history = self.memory.get()

            # Stream the response token by token
            response = ""

            # Use astream_chat to get streaming tokens
            handle = await self.llm.astream_chat(chat_history)

            # Stream each token to the client
            async for token in handle:
                logger.debug(f"Token: {token.delta}")
                response += token.delta

                # This is the key line - write each token to the event stream
                # with the token attribute so it will be properly streamed
                ctx.write_event_to_stream(Event(token=token.delta))

            # Store the complete response in memory
            self.memory.put(ChatMessage(role=MessageRole.ASSISTANT, content=response))

            # Log the final response for debugging
            logger.info(f"Final analysis response generated (length: {len(response)})")
            if "EMQX Log Analysis - Final Report" in response:
                logger.info("Final report title found in response")
            else:
                logger.warning("Final report title NOT found in response")

            # Return the StopEvent with the complete message
            # This ensures the response is captured for WebSocket delivery
            return StopEvent(message=response)

    @with_timeout(60, "Log analysis timed out")
    async def analyze_log(self, log_text: str) -> str:
        """Analyze a log entry using the LogAnalysis workflow.

        Args:
            log_text: The log text to analyze.

        Returns:
            The analysis result.
        """
        try:
            if self.llm is None:
                logger.warning("LlamaIndex service not initialized. Returning mock response.")
                return f"I'm sorry, but the LLM service is not properly initialized. Please check your {config.llm_provider} API key and configuration."

            # Create a new memory for this session to avoid conflicts
            session_memory = ChatMemoryBuffer(token_limit=8000)

            workflow = self.LogAnalysis(timeout=60, verbose=True, llm=self.llm, memory=session_memory)
            ctx = Context(workflow)

            # Start the workflow
            handler = workflow.run(user_input=log_text, ctx=ctx)

            # Process events
            result = ""
            async for event in handler.stream_events():
                if isinstance(event, StopEvent):
                    # Access the message attribute
                    result = event.message
                elif isinstance(event, InputRequiredEvent):
                    # Auto-respond with "done" to avoid hanging
                    handler.ctx.send_event(HumanResponseEvent(response="done"))

            # Wait for the handler to complete
            await handler

            return result or "Analysis completed, but no result was returned."
        except asyncio.TimeoutError:
            logger.warning("Log analysis timed out")
            return "The log analysis timed out. Please try again with a simpler log entry."
        except Exception as e:
            logger.error(f"Error analyzing log: {e}")
            return f"An error occurred during log analysis: {str(e)}"

    def create_embedding(self, text: str) -> List[float]:
        """Create an embedding for the given text.

        Args:
            text: The text to create an embedding for.

        Returns:
            The embedding vector.
        """
        try:
            if self.llm is None:
                logger.warning("LlamaIndex service not initialized. Returning mock embedding.")
                return [0.1] * config.embedding_dimension

            logger.debug(f"Creating embedding for text: {text[:50]}...")

            # Use the client from the LLM if it's OpenAI
            if config.llm_provider.lower() == "openai" and hasattr(self.llm, "client"):
                try:
                    response = self.llm.client.embeddings.create(
                        model=config.embedding_model,
                        input=text,
                    )
                    logger.debug("Embedding API call completed successfully")
                    return response.data[0].embedding
                except Exception as api_error:
                    logger.error(f"API call failed: {api_error}")
                    # Return a mock embedding as fallback
                    return [0.1] * config.embedding_dimension
            else:
                # For other providers, we would need to implement their embedding API calls
                logger.warning(f"Embeddings not implemented for provider: {config.llm_provider}")
                return [0.1] * config.embedding_dimension

        except Exception as e:
            logger.error(f"Error creating embedding: {e}")
            # Return a mock embedding as fallback
            return [0.1] * config.embedding_dimension

# Create a global instance of the service
llama_index_service = LlamaIndexService()
