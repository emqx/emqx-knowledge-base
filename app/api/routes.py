"""API routes for the application."""

import logging
import traceback
import asyncio
import functools
import time

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.models.knowledge import FileType, FileAttachment
from app.services.emqx_assistant import emqx_assistant_service
from app.config import config
from llama_index.core.workflow import StopEvent

logger = logging.getLogger(__name__)

# Create separate routers for API and WebSocket endpoints
router = APIRouter()
ws_router = APIRouter()


def api_error_handler(func):
    """Decorator to standardize error handling for API routes.

    This decorator catches exceptions, logs them, and returns appropriate HTTP responses.
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except HTTPException:
            # Re-raise HTTP exceptions as they're already properly formatted
            raise
        except asyncio.TimeoutError:
            logger.error(f"Timeout in {func.__name__}")
            raise HTTPException(status_code=504, detail="Request timed out")
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {e}")
            logger.error(traceback.format_exc())
            raise HTTPException(
                status_code=500, detail=f"Internal server error: {str(e)}"
            )

    return wrapper


@router.get("/health")
async def health_check():
    """Health check endpoint.

    Returns:
        A simple health check response.
    """
    return {"status": "ok"}


async def validate_jwt_token(token: str) -> bool:
    """Validate a JWT token for WebSocket connections.

    Args:
        token: The JWT token to validate

    Returns:
        True if token is valid, False otherwise
    """
    try:
        # Handle development token
        if token == "LOCAL_DEV_TOKEN" and config.environment != "production":
            logger.info("Using development token bypass")
            return True

        # Import JWT library
        import jwt
        from jwt.exceptions import InvalidTokenError

        # Check if jwt_secret is available
        if not config.jwt_secret:
            logger.error("JWT validation failed: No JWT_SECRET configured")
            return False

        try:
            # Verify the JWT token
            decoded = jwt.decode(
                token,
                config.jwt_secret,
                algorithms=["HS256"],
                options={"verify_signature": True},
            )

            logger.info(
                f"JWT validation successful for subject: {decoded.get('sub', 'unknown')}"
            )
            # If we get here, token is valid
            return True
        except InvalidTokenError as e:
            logger.error(f"JWT validation error: {e}")
            return False
    except Exception as e:
        logger.error(f"Error validating token: {str(e)}")
        return False


@ws_router.websocket("/ws/chat")
async def chat_websocket(websocket: WebSocket):
    """WebSocket endpoint for EMQX Assistant chat.

    This endpoint provides a chat interface that can answer questions about EMQX,
    supporting follow-up questions and maintaining conversational context.
    """
    # Extract token from query parameters
    query_params = dict(websocket.query_params)
    token = query_params.get("token")

    # Log token information for debugging
    logger.info(
        f"WebSocket chat connection attempt. Token present: {token is not None}"
    )

    # Validate token in all environments
    if not token:
        logger.warning("WebSocket chat connection rejected: Missing token")
        await websocket.close(code=1008, reason="Unauthorized: Missing token")
        return

    token_valid = await validate_jwt_token(token)
    if not token_valid:
        logger.warning("WebSocket chat connection rejected: Invalid token")
        await websocket.close(code=1008, reason="Unauthorized: Invalid token")
        return

    # Accept the connection if token is valid
    await websocket.accept()
    logger.info("WebSocket chat connection accepted with valid token")

    # Generate a unique session ID for this connection
    session_id = f"chat_ws_{id(websocket)}_{int(time.time())}"

    try:
        while True:  # Keep the connection open for multiple interactions
            # Receive the next message from the client
            data = await websocket.receive_json()

            # Handle ping messages to keep the connection alive
            if data.get("ping") is True:
                # Refresh the session if it exists
                emqx_assistant_service.session_manager.refresh_session(session_id)
                await websocket.send_json({"type": "pong", "data": "pong"})
                continue

            # Get the message content
            user_input = data.get("message", "")
            content = data.get("content", "")
            files = data.get("files", [])
            reset_session = data.get("reset_session", False)

            # Check if we have file content (log data)
            has_file_content = bool(content and len(content) > 0)

            # Log request details
            logger.info(
                f"Processing websocket request: has_file_content={has_file_content}, content_length={len(content) if content else 0}, user_input_length={len(user_input)}"
            )

            # All credential handling code has been removed in the simplified flow

            # If reset_session is true, clear the existing session
            if (
                reset_session
                and session_id in emqx_assistant_service.session_manager.sessions
            ):
                logger.info(f"Resetting chat session {session_id}")
                emqx_assistant_service.session_manager.delete_session(session_id)

            # The client must provide a question
            if not user_input.strip():
                await websocket.send_json(
                    {"type": "error", "data": "Message is required"}
                )
                continue

            # Process any file attachments
            file_attachments = []
            for file_data in files or []:
                filename = file_data.get("filename", "unnamed_file")
                content = file_data.get("content", "")
                filetype = file_data.get("filetype", "txt")

                # Create a file attachment
                file_attachment = FileAttachment(
                    file_name=filename,
                    file_type=FileType.from_extension(filetype),
                    content_text=content,
                    content_summary=f"File uploaded via chat: {filename}",
                    channel_id="websocket",
                    thread_ts=session_id,
                    user_id="websocket_user",
                    file_url="",
                )

                file_attachments.append(file_attachment)
                logger.info(f"Processed file attachment: {filename}")

            # If we have content but no files, create a file attachment for it
            if has_file_content and not file_attachments:
                logger.info("Creating file attachment from content field")
                # Create a default file name based on content
                default_filename = "uploaded_content.log"

                file_attachment = FileAttachment(
                    file_name=default_filename,
                    file_type=FileType.LOG,
                    content_text=content,
                    content_summary="File content uploaded via chat",
                    channel_id="websocket",
                    thread_ts=session_id,
                    user_id="websocket_user",
                    file_url="",
                )
                file_attachments.append(file_attachment)
                logger.info(f"Created file attachment from content: {default_filename}")

            # Check if we have an existing session
            session = emqx_assistant_service.session_manager.get_session(session_id)

            # Send appropriate initial message
            if session is None:
                await websocket.send_json(
                    {"type": "status", "data": "Starting new chat session..."}
                )
            else:
                await websocket.send_json(
                    {"type": "status", "data": "Processing your message..."}
                )

            try:
                # If no session exists, create a new one
                if session is None:
                    # Create a new session with the EMQX Assistant workflow
                    workflow, ctx, memory = (
                        emqx_assistant_service.session_manager.create_session(
                            session_id=session_id,
                            llm=emqx_assistant_service.llm,
                            file_attachments=file_attachments,
                        )
                    )
                else:
                    # Use the existing session
                    workflow, ctx, memory = session

                    # Add or update file attachments if any
                    if file_attachments:
                        workflow.file_attachments = file_attachments

                # Add debug logging for context
                logger.info(f"Context object attributes: {dir(ctx)}")

                # Approach 3: Use a callback to handle events from write_event_to_stream
                async def handle_event(event):
                    try:
                        # Handle events with metadata
                        if hasattr(event, "metadata") and event.metadata:
                            # Ensure broker_info events are processed with high priority
                            if event.metadata.get("type") == "broker_info":
                                logger.info(
                                    "Broker info event received, forwarding to client"
                                )
                                await websocket.send_json(event.metadata)
                            else:
                                await websocket.send_json(event.metadata)
                        # Handle token streaming
                        elif hasattr(event, "token") and event.token:
                            # Token streaming event for real-time updates
                            await websocket.send_json(
                                {"type": "token", "data": event.token}
                            )
                        else:
                            # Log unknown event types for debugging
                            logger.debug(f"Unknown event type: {type(event)} - {event}")
                    except Exception as e:
                        logger.error(f"Error handling event: {e}")
                        logger.error(traceback.format_exc())

                # Use the streaming_queue attribute of the context
                async def listen_for_events():
                    try:
                        while True:
                            # Use the streaming_queue to get events
                            # This is based on seeing 'streaming_queue' in the context attributes
                            if hasattr(ctx, "streaming_queue"):
                                try:
                                    event = await asyncio.wait_for(
                                        ctx.streaming_queue.get(), timeout=0.1
                                    )
                                    await handle_event(event)
                                except asyncio.TimeoutError:
                                    # No events in the queue, check if workflow is done
                                    if getattr(
                                        workflow_future, "done", lambda: False
                                    )():
                                        break
                                    await asyncio.sleep(0.1)
                            else:
                                logger.error("Context has no streaming_queue attribute")
                                break
                    except Exception as e:
                        logger.error(f"Error in listen_for_events: {e}")
                        logger.error(traceback.format_exc())

                # Start the event listener
                event_listener = asyncio.create_task(listen_for_events())

                # Run the workflow and wait for it to complete
                workflow_future = asyncio.create_task(
                    workflow.run(user_input=user_input, ctx=ctx)
                )

                try:
                    # Wait for the workflow to complete
                    event = await workflow_future

                    # Send message_complete event to signal completion
                    await websocket.send_json(
                        {"type": "message_complete", "data": True}
                    )

                    await websocket.send_json({"type": "status", "data": ""})
                finally:
                    # Cancel the event listener
                    event_listener.cancel()

                # Handle the final event (should be a StopEvent)
                if isinstance(event, StopEvent):
                    # The broker_context should be handled via the streaming mechanism,
                    # so we don't need to check for it here or send another message_complete event
                    pass

            except Exception as e:
                logger.error(f"Error processing chat message: {e}")
                logger.error(traceback.format_exc())
                await websocket.send_json(
                    {
                        "type": "error",
                        "data": f"Error processing your message: {str(e)}",
                    }
                )

    except WebSocketDisconnect:
        logger.info(f"Chat WebSocket disconnected: {session_id}")
        # Clean up the session when the WebSocket disconnects
        emqx_assistant_service.session_manager.delete_session(session_id)
    except Exception as e:
        logger.error(f"Error in chat WebSocket: {e}")
        logger.error(traceback.format_exc())
        try:
            await websocket.send_json({"type": "error", "data": str(e)})
            # Keep the connection open for a moment to ensure the error message is sent
            await asyncio.sleep(1)
        except Exception:
            pass  # Client might be disconnected already
