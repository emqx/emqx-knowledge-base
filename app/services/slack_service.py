"""Service for interacting with Slack API."""
import logging
import re
from typing import List, Optional, Tuple

from slack_bolt import App, BoltContext
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.web import WebClient

from app.config import config
from app.models.knowledge import KnowledgeEntry, KnowledgeResponse
from app.services.database import db_service
from app.services.openai_service import openai_service

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
            self._analyze_thread(channel_id, thread_ts, user_id, say)
            return

        # Check if this is a general help request
        if self._is_help_request(message):
            self._send_help_message(thread_ts, say)
            return

        # Otherwise, treat it as a question
        self._answer_question(text, channel_id, thread_ts, say)

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
            "• Save important Slack threads to a searchable knowledge base\n"
            "• Analyze ongoing threads to provide assistance without saving them\n"
            "• Answer questions based on previously saved knowledge\n"
            "• Provide source links to original conversations\n"
            "• Reference official EMQX documentation when appropriate\n"
            "• Recognize version-specific questions (e.g., 'How to configure auth in EMQX 5.0?')\n"
            "• Provide information about EMQX Kubernetes deployments using the Operator\n"
            "• Use AI to generate relevant responses based on your team's specific knowledge\n\n"
            "*How to use me:*\n"
            "• To save a thread: Add a 📚 reaction to any message or mention me with `@KnowledgeBot save`\n"
            "• To analyze a thread: Mention me with `@KnowledgeBot help with this` or similar phrases\n"
            "• To ask a question: Mention me with your question like `@KnowledgeBot What's the solution for...?`\n"
            "• For version-specific help: Include the version number in your question (e.g., `@KnowledgeBot How to use rule engine in EMQX 4.3?`)\n"
            "• For Kubernetes help: Include terms like 'Kubernetes', 'K8s', or 'Operator' in your question\n\n"
            "*What I cannot do:*\n"
            "• Automatically save all conversations (I only save threads when explicitly requested)\n"
            "• Answer questions outside the scope of saved knowledge and official documentation\n"
            "• Access private channels or conversations I'm not invited to"
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
                [f"<@{msg.get('user', 'UNKNOWN')}>: {msg.get('text', '')}" for msg in messages]
            )

            # Create embedding for the thread content
            embedding = openai_service.create_embedding(thread_content)

            # Create and save the knowledge entry
            entry = KnowledgeEntry(
                channel_id=channel_id,
                thread_ts=thread_ts,
                user_id=user_id,
                content=thread_content,
                embedding=embedding,
            )

            entry_id = db_service.save_knowledge(entry)

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

    def _answer_question(self, text: str, channel_id: str, thread_ts: str, say):
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
            if len(question) < 5 or not any(q in question.lower() for q in ["?", "what", "how", "why", "when", "where", "who"]):
                say(
                    text="I'm not sure what you're asking. Could you please rephrase your question?",
                    thread_ts=thread_ts,
                )
                return

            # Create embedding for the question
            embedding = openai_service.create_embedding(question)

            # Find similar entries in the knowledge base
            similar_entries = db_service.find_similar_entries(embedding)

            if not similar_entries:
                say(
                    text="I don't have any relevant information in my knowledge base to answer your question.",
                    thread_ts=thread_ts,
                )
                return

            # Generate a response using OpenAI
            entries = [entry for entry, _ in similar_entries]
            response = openai_service.generate_response(question, entries)

            # Format the response
            answer_text = response.answer
            
            # Add source references if we have high confidence
            if response.confidence > 0.5 and response.sources:
                source_links = []
                for i, source in enumerate(response.sources):
                    # Create a link to the source thread
                    link = f"<https://slack.com/archives/{source.channel_id}/p{source.thread_ts.replace('.', '')}|Source {i+1}>"
                    source_links.append(link)
                
                if source_links:
                    answer_text += f"\n\n*Sources:* {', '.join(source_links)}"

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
        
    def _analyze_thread(self, channel_id: str, thread_ts: str, user_id: str, say):
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
                [f"<@{msg.get('user', 'UNKNOWN')}>: {msg.get('text', '')}" for msg in messages]
            )
            
            # Create a question that asks for analysis of the thread
            analysis_question = "Please analyze this thread and provide assistance based on the conversation. " + \
                               "Identify any problems, questions, or issues being discussed and provide helpful information or solutions."

            # Create embedding for the thread content
            embedding = openai_service.create_embedding(thread_content)
            
            # Find similar entries in the knowledge base that might be relevant
            similar_entries = db_service.find_similar_entries(embedding, threshold=0.5)
            
            # Generate a response using OpenAI
            entries = [entry for entry, _ in similar_entries]
            
            # Add the current thread as a source
            current_thread_entry = KnowledgeEntry(
                channel_id=channel_id,
                thread_ts=thread_ts,
                user_id=user_id,
                content=thread_content,
                embedding=embedding,
            )
            
            # Put the current thread as the first entry for context
            all_entries = [current_thread_entry] + entries
            
            response = openai_service.generate_response(analysis_question, all_entries)

            say(
                text=f"*Thread Analysis:*\n\n{response.answer}",
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
