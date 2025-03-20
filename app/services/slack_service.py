"""Service for interacting with Slack API."""

import logging
import re
import asyncio
import threading
import traceback

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from app.config import config
from app.models.knowledge import KnowledgeEntry
from app.services.database import db_service
from app.services.file_service import file_service
from app.services.emqx_assistant import emqx_assistant_service

logger = logging.getLogger(__name__)


class SlackService:
    """Service for interacting with Slack API."""

    def __init__(self):
        """Initialize the Slack service."""
        self.app = App(
            token=config.slack_bot_token,
            signing_secret=config.slack_signing_secret,
        )
        self.client = self.app.client
        self._register_handlers()

    def _register_handlers(self):
        """Register event handlers for Slack events."""
        # Handle app mentions (direct messages to the bot)
        self.app.event("app_mention")(self._handle_app_mention)

        # Handle reaction added events (for saving threads)
        self.app.event("reaction_added")(self._handle_reaction_added)

        # Handle file shared events
        self.app.event("file_shared")(self._handle_file_shared)

    def _handle_app_mention(self, body, say, context):
        """Handle app mention events.

        Args:
            body: The event body.
            say: Function to send a message to the channel.
            context: The event context.
        """
        event = body["event"]
        text = event["text"]
        channel_id = event["channel"]
        thread_ts = event.get("thread_ts", event["ts"])
        user_id = event["user"]

        # Extract the actual message (remove the bot mention)
        message = re.sub(r"<@[A-Z0-9]+>\s*", "", text).strip().lower()

        # Check if this is a request to save the thread
        # Now matches just "save" or variations like "save this", "save thread",
        # etc.
        if message == "save" or message.startswith("save "):
            self._save_thread(channel_id, thread_ts, user_id, say)
            return

        # Check if this is a request to analyze the current thread
        # This check needs to come before the general help request check
        if self._is_analyze_thread_request(message):
            # Use a synchronous wrapper to run the async function
            self._run_async_analyze_thread(channel_id, thread_ts, user_id, say)
            return

        # Check if this is a general help request
        if self._is_help_request(message):
            self._send_help_message(thread_ts, say)
            return

        # Otherwise, treat it as a question
        # Use a synchronous wrapper to run the async function
        self._run_async_process_input(text, channel_id, thread_ts, say)

    def _run_async_analyze_thread(self, channel_id, thread_ts, user_id, say):
        """Synchronous wrapper to run the async analyze_thread function."""
        try:
            # Helper function to run in a new event loop
            def run_in_new_loop():
                # Create and set a new event loop
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                try:
                    # Run the async function to completion with proper awaiting
                    coroutine = self._analyze_thread(
                        channel_id, thread_ts, user_id, say
                    )
                    loop.run_until_complete(coroutine)
                except Exception as e:
                    logger.error(f"Error in analyze_thread: {e}")
                    logger.error(traceback.format_exc())
                finally:
                    # Close the loop
                    loop.close()

            # Run in a separate thread to avoid blocking
            thread = threading.Thread(target=run_in_new_loop)
            thread.daemon = True
            thread.start()

        except Exception as e:
            logger.error(f"Error running async analyze_thread: {e}")
            say(
                text="I encountered an error while trying to analyze this thread.",
                thread_ts=thread_ts,
            )

    def _run_async_process_input(self, text, channel_id, thread_ts, say):
        """Synchronous wrapper to run the async process_input function."""
        try:
            # Helper function to run in a new event loop
            def run_in_new_loop():
                # Create and set a new event loop
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                try:
                    # Run the async function to completion with proper awaiting
                    coroutine = self._process_input(text, channel_id, thread_ts, say)
                    loop.run_until_complete(coroutine)
                except Exception as e:
                    logger.error(f"Error in process_input: {e}")
                    logger.error(traceback.format_exc())
                finally:
                    # Close the loop
                    loop.close()

            # Run in a separate thread to avoid blocking
            thread = threading.Thread(target=run_in_new_loop)
            thread.daemon = True
            thread.start()

        except Exception as e:
            logger.error(f"Error running async process_input: {e}")
            say(
                text="I encountered an error while trying to answer your question.",
                thread_ts=thread_ts,
            )

    def _is_help_request(self, message: str) -> bool:
        """Check if the message is a general help request.

        Args:
            message: The message to check.

        Returns:
            True if the message is a general help request, False otherwise.
        """
        # These patterns are for general help about the bot itself, not for
        # analyzing a thread
        help_patterns = [
            r"^help$",  # Just the word "help" by itself
            r"^what can you do$",
            r"^what do you do$",
            r"^how do you work$",
            r"^how to use$",
            r"capabilities",
            r"features",
            r"commands",
            r"usage",
            r"instructions",
            r"tell me about yourself",
            r"what are you",
        ]

        for pattern in help_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                return True

        return False

    def _send_help_message(self, thread_ts: str, say):
        """Send a help message explaining what the bot can do.

        Args:
            thread_ts: The thread timestamp.
            say: Function to send a message to the channel.
        """
        help_text = (
            "*EMQX Knowledge Bot*\n\n"
            "I help your team capture and retrieve valuable knowledge from Slack conversations.\n\n"
            "*What I can do:*\n"
            "- Save important Slack threads to a searchable knowledge base\n"
            "- Analyze ongoing threads to provide assistance without saving them\n"
            "- Answer questions based on previously saved knowledge\n"
            "- Provide source links to original conversations\n"
            "- Reference official EMQX documentation when appropriate\n"
            "- Recognize version-specific questions (e.g., 'How to configure auth in EMQX 5.0?')\n"
            "- Provide information about EMQX Kubernetes deployments using the Operator\n"
            "- Use AI to generate relevant responses based on your team's specific knowledge\n\n"
            "*How to use me:*\n"
            "- To save a thread: Add a 📚 reaction to any message or mention me with `@KnowledgeBot save`\n"
            "- To analyze a thread: Mention me with `@KnowledgeBot help with this` or similar phrases\n"
            "- To ask a question: Mention me with your question like `@KnowledgeBot What's the solution for...?`\n"
            "- For version-specific help: Include the version number in your question (e.g., `@KnowledgeBot How to use rule engine in EMQX 4.3?`)\n"
            "- For Kubernetes help: Include terms like 'Kubernetes', 'K8s', or 'Operator' in your question\n\n"
            "*What I cannot do:*\n"
            "- Automatically save all conversations (I only save threads when explicitly requested)\n"
            "- Answer questions outside the scope of saved knowledge and official documentation\n"
            "- Access private channels or conversations I'm not invited to"
        )

        say(
            text=help_text,
            thread_ts=thread_ts,
        )

    def _handle_reaction_added(self, body, say, context):
        """Handle reaction added events.

        Args:
            body: The event body.
            say: Function to send a message to the channel.
            context: The event context.
        """
        event = body["event"]
        reaction = event["reaction"]
        item = event["item"]
        user_id = event["user"]

        logger.info(f"Reaction added: {reaction}")
        # Check if this is the save emoji
        if reaction == config.save_emoji and item["type"] == "message":
            channel_id = item["channel"]
            thread_ts = item.get("thread_ts", item["ts"])
            self._save_thread(channel_id, thread_ts, user_id, say)

    def _handle_file_shared(self, body, say, context):
        """Handle file shared events.

        Args:
            body: The event body.
            say: Function to send a message to the channel.
            context: The event context.
        """
        event = body["event"]
        file_id = event.get("file_id")

        if not file_id:
            return

        try:
            # Get file info
            file_info = self.client.files_info(file=file_id)

            if not file_info["ok"]:
                logger.error(f"Failed to get file info: {file_info}")
                return

            file = file_info["file"]
            channel_id = file.get("channels")[0] if file.get("channels") else None
            thread_ts = file.get("thread_ts")
            user_id = file.get("user")

            # Only process files that are in threads
            if not thread_ts or not channel_id:
                return

            # Process the file
            file_url = file.get("url_private")
            file_name = file.get("name")

            logger.info(f"Processing file: {file_name} in thread {thread_ts}")

            # Process and save the file attachment
            attachment = file_service.process_file(
                file_url=file_url,
                file_name=file_name,
                channel_id=channel_id,
                thread_ts=thread_ts,
                user_id=user_id,
            )

            if attachment:
                logger.info(f"File attachment saved: {attachment.id}")

        except Exception as e:
            logger.error(f"Error processing file: {e}")

    def _save_thread(self, channel_id: str, thread_ts: str, user_id: str, say):
        """Save a thread to the knowledge base.

        Args:
            channel_id: The channel ID.
            thread_ts: The thread timestamp.
            user_id: The user ID who initiated the save.
            say: Function to send a message to the channel.
        """
        try:
            # Get all messages in the thread
            response = self.client.conversations_replies(
                channel=channel_id,
                ts=thread_ts,
            )

            if not response["ok"] or not response["messages"]:
                say(
                    text="I couldn't find any messages in this thread.",
                    thread_ts=thread_ts,
                )
                return

            # Combine all messages into a single text
            messages = response["messages"]
            thread_content = "\n\n".join(
                [
                    f"<@{msg.get('user', 'UNKNOWN')}>: {msg.get('text', '')}"
                    for msg in messages
                ]
            )

            # Create embedding for the thread content
            embedding = emqx_assistant_service.create_embedding(thread_content)

            # Create and save the knowledge entry
            entry = KnowledgeEntry(
                channel_id=channel_id,
                thread_ts=thread_ts,
                user_id=user_id,
                content=thread_content,
                embedding=embedding,
            )

            entry_id = db_service.save_knowledge(entry)

            # Process any files in the thread
            file_count = 0
            for message in messages:
                if "files" in message:
                    for file in message["files"]:
                        file_url = file.get("url_private")
                        file_name = file.get("name")

                        # Process and save the file attachment
                        attachment = file_service.process_file(
                            file_url=file_url,
                            file_name=file_name,
                            channel_id=channel_id,
                            thread_ts=thread_ts,
                            user_id=message.get("user", user_id),
                        )

                        if attachment:
                            file_count += 1

            if file_count > 0:
                say(
                    text=f"I've saved this thread to the knowledge base (ID: {entry_id}) along with {file_count} file attachments.",
                    thread_ts=thread_ts,
                )
            else:
                say(
                    text=f"I've saved this thread to the knowledge base (ID: {entry_id}).",
                    thread_ts=thread_ts,
                )

        except Exception as e:
            logger.error(f"Error saving thread: {e}")
            say(
                text="I encountered an error while trying to save this thread.",
                thread_ts=thread_ts,
            )

    async def _process_input(self, text: str, channel_id: str, thread_ts: str, say):
        """Answer a question using the knowledge base.

        Args:
            text: The question text.
            channel_id: The channel ID.
            thread_ts: The thread timestamp.
            say: Function to send a message to the channel.
        """
        try:
            # Extract the actual question (remove the bot mention)
            question = re.sub(r"<@[A-Z0-9]+>\s*", "", text).strip()

            # If the question is too short or doesn't seem like a question, ask for clarification
            if len(question) < 5 or not any(
                q in question.lower()
                for q in ["?", "what", "how", "why", "when", "where", "who"]
            ):
                say(
                    text="I'm not sure what you're asking. Could you please rephrase your question?",
                    thread_ts=thread_ts,
                )
                return

            # Check if there are files in the current thread that need to be processed
            thread_file_attachments = []
            try:
                # Get all messages in the thread
                response = self.client.conversations_replies(
                    channel=channel_id,
                    ts=thread_ts,
                )

                if response["ok"] and response["messages"]:
                    messages = response["messages"]

                    # Process any files in the thread
                    for message in messages:
                        if "files" in message:
                            for file in message["files"]:
                                file_url = file.get("url_private")
                                file_name = file.get("name")

                                logger.info(
                                    f"Processing file for question: {file_name}"
                                )

                                # First check if the file is already in the database
                                existing_attachments = (
                                    db_service.get_file_attachments_by_thread(
                                        channel_id, thread_ts
                                    )
                                )
                                existing_file = next(
                                    (
                                        a
                                        for a in existing_attachments
                                        if a.file_name == file_name
                                    ),
                                    None,
                                )

                                if existing_file:
                                    logger.info(
                                        f"File already exists in database: {existing_file.id}"
                                    )
                                    thread_file_attachments.append(existing_file)
                                else:
                                    # Process and save the file attachment
                                    attachment = file_service.process_file(
                                        file_url=file_url,
                                        file_name=file_name,
                                        channel_id=channel_id,
                                        thread_ts=thread_ts,
                                        user_id=message.get("user"),
                                    )

                                    if attachment:
                                        logger.info(
                                            f"File attachment processed for question: {attachment.id}"
                                        )
                                        thread_file_attachments.append(attachment)
            except Exception as e:
                logger.error(f"Error processing files in thread for question: {e}")
                # Continue with the question answering even if file processing fails

            # Create embedding for the question to find similar entries
            embedding = emqx_assistant_service.create_embedding(question)

            # Find similar file attachments
            similar_files = db_service.find_similar_file_attachments(embedding)

            # Combine thread files with similar files, prioritizing thread files
            all_file_attachments = thread_file_attachments.copy()
            for file, _ in similar_files:
                if not any(
                    tf.id == file.id
                    for tf in thread_file_attachments
                    if tf.id is not None
                ):
                    all_file_attachments.append(file)

            # Always use the EMQX Q&A service to answer questions
            logger.info("Using EMQX Q&A service to answer question")
            response = await emqx_assistant_service.process_input(
                question=question, file_attachments=all_file_attachments
            )

            # Format the response
            answer_text = response.answer

            # Add source references
            if response.sources:
                source_links = []
                for i, source in enumerate(response.sources, 1):
                    source_link = f"<slack://channel?team={config.slack_team_id}&id={source.channel_id}&message={source.thread_ts}|Source {i}>"
                    source_links.append(source_link)

                answer_text += "\n\n*Sources:* " + ", ".join(source_links)

            # Add file references
            if response.file_sources:
                file_links = []
                for i, file in enumerate(response.file_sources, 1):
                    file_link = f"<slack://channel?team={config.slack_team_id}&id={file.channel_id}&message={file.thread_ts}|{file.file_name}>"
                    file_links.append(file_link)

                answer_text += "\n\n*File References:* " + ", ".join(file_links)

            # Add note about thread files if they were processed
            if thread_file_attachments:
                thread_file_names = [
                    f"`{file.file_name}`" for file in thread_file_attachments
                ]
                answer_text += (
                    f"\n\n*Files in this thread:* {', '.join(thread_file_names)}"
                )

            say(
                text=answer_text,
                thread_ts=thread_ts,
            )

        except Exception as e:
            logger.error(f"Error answering question: {e}")
            say(
                text="I encountered an error while trying to answer your question.",
                thread_ts=thread_ts,
            )

    def _is_analyze_thread_request(self, message: str) -> bool:
        """Check if the message is a request to analyze the current thread.

        Args:
            message: The message to check.

        Returns:
            True if the message is a request to analyze the thread, False otherwise.
        """
        analyze_patterns = [
            r"help here",
            r"analyze( this)? thread",
            r"summarize( this)? thread",
            r"assist( with)? this( thread)?",
            r"help( with)? this( thread)?",
            r"what('s| is) (happening|going on)( here)?",
            r"can you (help|assist)( me)?( with this)?",
            r"check this( thread)?( out)?",
        ]

        for pattern in analyze_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                return True

        return False

    async def _analyze_thread(self, channel_id: str, thread_ts: str, user_id: str, say):
        """Analyze the current thread and provide assistance.

        Args:
            channel_id: The channel ID.
            thread_ts: The thread timestamp.
            user_id: The user ID who requested the analysis.
            say: Function to send a message to the channel.
        """
        try:
            # Get all messages in the thread
            response = self.client.conversations_replies(
                channel=channel_id,
                ts=thread_ts,
            )

            if not response["ok"] or not response["messages"]:
                say(
                    text="I couldn't find any messages in this thread to analyze.",
                    thread_ts=thread_ts,
                )
                return

            # Combine all messages into a single text
            messages = response["messages"]
            thread_content = "\n\n".join(
                [
                    f"<@{msg.get('user', 'UNKNOWN')}>: {msg.get('text', '')}"
                    for msg in messages
                ]
            )

            # Process any files in the thread
            file_attachments = []
            for message in messages:
                if "files" in message:
                    for file in message["files"]:
                        file_url = file.get("url_private")
                        file_name = file.get("name")

                        logger.info(f"Processing file in thread analysis: {file_name}")

                        # First check if the file is already in the database
                        existing_attachments = (
                            db_service.get_file_attachments_by_thread(
                                channel_id, thread_ts
                            )
                        )
                        existing_file = next(
                            (
                                a
                                for a in existing_attachments
                                if a.file_name == file_name
                            ),
                            None,
                        )

                        if existing_file:
                            logger.info(
                                f"File already exists in database: {existing_file.id}"
                            )
                            file_attachments.append(existing_file)
                        else:
                            # Process and save the file attachment
                            attachment = file_service.process_file(
                                file_url=file_url,
                                file_name=file_name,
                                channel_id=channel_id,
                                thread_ts=thread_ts,
                                user_id=message.get("user", user_id),
                            )

                            if attachment:
                                logger.info(
                                    f"File attachment processed for analysis: {attachment.id}"
                                )
                                file_attachments.append(attachment)

            # Create a question that asks for analysis of the thread and includes the thread content
            analysis_question = f"""Please analyze this conversation thread and provide assistance:

Thread Content:
{thread_content}

Provide a thorough analysis of the above conversation. Identify any problems, questions, or issues being discussed and provide helpful information, solutions, or recommendations. Focus on EMQX-related issues if present."""

            # Create embedding for the thread content
            embedding = emqx_assistant_service.create_embedding(thread_content)

            # Create a thread context entry to provide to the Q&A service
            current_thread_entry = KnowledgeEntry(
                channel_id=channel_id,
                thread_ts=thread_ts,
                user_id=user_id,
                content=thread_content,
                embedding=embedding,
            )

            # Save the thread entry temporarily to make it available as a source
            temp_entry_id = db_service.save_knowledge(current_thread_entry)
            logger.info(f"Temporary thread entry saved with ID: {temp_entry_id}")

            # Use the EMQX Q&A service for thread analysis
            logger.info("Using EMQX Q&A service for thread analysis")

            # Use a custom session ID for this thread analysis
            session_id = f"slack_thread_{channel_id}_{thread_ts}"

            response = await emqx_assistant_service.process_input(
                question=analysis_question,
                session_id=session_id,
                file_attachments=file_attachments,
            )

            # Remove the temporary entry to keep the database clean
            db_service.delete_knowledge(temp_entry_id)

            # Format the response
            answer_text = f"*Thread Analysis:*\n\n{response.answer}"

            # Add file references if any were processed
            if file_attachments:
                file_names = [f"`{file.file_name}`" for file in file_attachments]
                answer_text += f"\n\n*Files Analyzed:* {', '.join(file_names)}"

            say(
                text=answer_text,
                thread_ts=thread_ts,
            )

        except Exception as e:
            logger.error(f"Error analyzing thread: {e}")
            say(
                text="I encountered an error while trying to analyze this thread.",
                thread_ts=thread_ts,
            )

    def start(self):
        """Start the Slack bot."""
        handler = SocketModeHandler(self.app, config.slack_app_token)
        handler.start()


# Create a global Slack service instance
slack_service = SlackService()
