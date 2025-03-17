"""Service for interacting with LlamaIndex."""
import logging
import os
import urllib.request
import json
import base64
from typing import List, Optional, Dict, Any

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

from app.config import config
from app.models.knowledge import KnowledgeEntry, KnowledgeResponse, FileAttachment

logger = logging.getLogger(__name__)

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
        A string that represents the status of the cluster.
    """
    try:
        token = get_emqx_token()
        if not token:
            return {"error": "Failed to obtain authentication token"}

        url = f'{config.emqx_base_url}/nodes'
        req = urllib.request.Request(url)
        req.add_header('Content-Type', 'application/json')
        req.add_header('Authorization', f'Bearer {token}')

        logger.debug(f"Querying EMQX cluster info: {url}")

        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())

        logger.debug(f"EMQX cluster info: {data}")
        return data
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

class LlamaIndexService:
    """Service for interacting with LlamaIndex."""

    def __init__(self):
        """Initialize the LlamaIndex service."""
        try:
            if not config.openai_api_key:
                logger.warning("OpenAI API key is not set. LlamaIndex service will not work properly.")
                self.llm = None
            else:
                self.llm = OpenAI(api_key=config.openai_api_key, model=config.openai_model)
                logger.debug("LlamaIndex service initialized successfully")

            self.memory = ChatMemoryBuffer(token_limit=8000)
        except Exception as e:
            logger.error(f"Error initializing LlamaIndex service: {e}")
            self.llm = None
            self.memory = None

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
                    answer="I'm sorry, but the LlamaIndex service is not properly initialized.",
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
            self.llm = llm or None
            self.memory = memory or ChatMemoryBuffer(token_limit=8000)
            super().__init__(*args, **kwargs)

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

            # Create individual messages instead of using memory
            messages = [
                ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
                ChatMessage(role=MessageRole.USER, content=f'{ev.user_input}\nPlease extract EMQX log entries to a JSON block and give some suggestions for it.')
            ]

            # Use chat instead of complete
            response = await self.llm.achat(messages)

            return LogEntryEvent(entry=response.message.content)

        @step
        async def query_emqx_context(self, ctx: Context, ev: LogEntryEvent) -> LogEntryWithContextEvent:
            """Query EMQX context information."""
            logger.debug("Querying EMQX context")
            system_prompt = """
            You are a helpful assistant that can extract information from EMQX logs and retrieve relevant information from the EMQX API.
            Your task is to identify resource IDs in the log entry and use the appropriate tools to gather more context.
            """

            # Create an agent workflow with the EMQX API functions as tools
            query_info = AgentWorkflow.from_tools_or_functions(
                [query_emqx_cluster_info, query_emqx_connector_info, query_emqx_authentication_info],
                llm=self.llm,
                system_prompt=system_prompt
            )

            # Run the agent workflow with the log entry
            user_msg = f"""
            Extract any resource IDs from this log entry and retrieve relevant information:

            {ev.entry}

            If you find a connector ID (format: connector:type:name), use query_emqx_connector_info to get more information.
            If you find an authentication ID (format: emqx_authn_type:number or password_based:type), use query_emqx_authentication_info to get more information.
            Always use query_emqx_cluster_info to get general cluster information.
            """

            response = await query_info.run(user_msg=user_msg)

            return LogEntryWithContextEvent(entry=ev.entry, log_context=str(response))

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

            ### Actionable Recommendations
            1. For each identified issue, provide a concise summary of the potential problem.
            2. Outline possible root causes based on the log details.
            3. Offer step-by-step troubleshooting or mitigation strategies.
            4. Suggest verifying network configurations, resource usage, or recent configuration changes where applicable.

            ### Audience Considerations
            1. Provide clear explanations that are accessible to both technical and non-technical users.
            3. Use technical language where needed for precision, but also include definitions or context for specialized terms.

            ### Clarifications and Follow-Up
            1. If the log details are ambiguous or incomplete, ask clarifying questions to gather more context.
            2. Recommend additional logging or monitoring if more details would aid in diagnosis.
            """

            # Create individual messages instead of using memory
            messages = [
                ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
                ChatMessage(role=MessageRole.USER, content=f'Log information is {ev.entry}. Additional context information: {ev.log_context}. Please deliver a detailed analysis along with step-by-step troubleshooting recommendations.')
            ]

            # Use chat instead of complete
            response = await self.llm.achat(messages)

            return StopEvent(message=response.message.content)

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
                return "I'm sorry, but the LlamaIndex service is not properly initialized."

            workflow = self.LogAnalysis(timeout=None, verbose=True, llm=self.llm)
            ctx = Context(workflow)

            handler = workflow.run(user_input=log_text, ctx=ctx)

            result = ""
            async for event in handler.stream_events():
                if isinstance(event, StopEvent):
                    # Access the message attribute instead of data
                    result = event.message
                elif isinstance(event, InputRequiredEvent):
                    # In a real application, we would handle user input here
                    # For now, we'll just continue with a default response
                    handler.ctx.send_event(HumanResponseEvent(response="yes"))

            await handler
            return result
        except Exception as e:
            logger.error(f"Error analyzing log with LlamaIndex: {e}")
            return f"I encountered an error while analyzing the log: {str(e)}"

# Create a global instance of the service
llama_index_service = LlamaIndexService()
