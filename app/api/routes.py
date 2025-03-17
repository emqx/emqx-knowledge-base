"""API routes for the application."""
import logging
import traceback
from typing import List, Optional
import tempfile
import os
import asyncio
import functools
import time

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
import json

from app.api.models import AnswerResponse, QuestionRequest, SourceReference, FileReference
from app.models.knowledge import FileType, FileAttachment
from app.services.database import db_service
from app.services.file_service import file_service
from app.services.llama_index_service import llama_index_service
from llama_index.core.workflow import InputRequiredEvent, HumanResponseEvent, StopEvent
from llama_index.core.workflow import Context

logger = logging.getLogger(__name__)

router = APIRouter()

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
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    return wrapper


@router.post("/ask", response_model=AnswerResponse)
@api_error_handler
async def ask_question(
    request: Optional[QuestionRequest] = None,
    question: Optional[str] = Form(None),
    files: List[UploadFile] = File([])
) -> AnswerResponse:
    """Ask a question to the knowledge base.

    Args:
        request: The question request.
        question: The question text.
        files: List of uploaded files.

    Returns:
        The answer response.
    """
    # Get the question from either the JSON body or form field
    question_text = ""
    if request:
        question_text = request.question
    elif question:
        question_text = question
    else:
        raise HTTPException(status_code=400, detail="Question is required")
            
    logger.debug(f"Received question: {question_text}")
    
    # Process uploaded files if any
    uploaded_file_attachments = []
    if files:
        for file in files:
            try:
                # Create a temporary file
                with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                    # Write the content to the temporary file
                    content = await file.read()
                    temp_file.write(content)
                    temp_file.flush()
                    
                    # Process the file
                    file_attachment = FileAttachment(
                        file_name=file.filename,
                        file_size=len(content),
                        file_type=FileType.determine_file_type(file.filename),
                        content=""
                    )
                    
                    processed_file = await file_service.process_temp_file(
                        temp_file.name,
                        file.filename,
                        file_attachment
                    )
                    
                    if processed_file:
                        uploaded_file_attachments.append(processed_file)
                    
                    # Clean up the temporary file
                    os.unlink(temp_file.name)
            except Exception as e:
                logger.error(f"Error processing file {file.filename}: {e}")
                logger.error(traceback.format_exc())
    
    # Create embedding for the question
    question_embedding = llama_index_service.create_embedding(question_text)
    
    # Search for relevant knowledge entries
    search_results = db_service.search_knowledge(question_embedding)
    
    # Use LlamaIndex to generate a response
    response = await llama_index_service.generate_response(
        question_text, 
        search_results, 
        uploaded_file_attachments
    )
    
    # Convert to API response format
    source_references = []
    for source in response.sources:
        source_references.append(
            SourceReference(
                title=source.title,
                url=source.url,
                content_snippet=source.content[:200] + "..." if len(source.content) > 200 else source.content
            )
        )
    
    file_references = []
    for file in response.file_sources:
        file_references.append(
            FileReference(
                file_name=file.file_name,
                file_type=file.file_type
            )
        )
    
    return AnswerResponse(
        answer=response.answer,
        sources=source_references,
        file_sources=file_references
    )


@router.post("/analyze-log", response_model=AnswerResponse)
@api_error_handler
async def analyze_log(
    request: Optional[QuestionRequest] = None,
    log_text: Optional[str] = Form(None),
    files: List[UploadFile] = File([])
) -> AnswerResponse:
    """Analyze a log entry.

    Args:
        request: The request containing the log text.
        log_text: The log text from a form.
        files: List of uploaded log files.

    Returns:
        The analysis response.
    """
    try:
        # Get the log text from either the JSON body, form field, or files
        text_to_analyze = ""
        if request and hasattr(request, 'question'):
            text_to_analyze = request.question
        elif log_text:
            text_to_analyze = log_text
        elif files and len(files) > 0:
            # Read the first file
            file = files[0]
            content = await file.read()
            text_to_analyze = content.decode('utf-8')
        else:
            raise HTTPException(status_code=400, detail="Log text is required")
            
        logger.debug(f"Received log text: {text_to_analyze[:100]}...")
        
        # Use LlamaIndex to analyze the log
        analysis_result = await llama_index_service.analyze_log(text_to_analyze)
        
        return AnswerResponse(
            answer=analysis_result,
            sources=[],
            file_sources=[]
        )
    except Exception as e:
        logger.error(f"Error analyzing log: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze-log/stream")
@api_error_handler
async def analyze_log_stream(
    request: Optional[QuestionRequest] = None,
    log_text: Optional[str] = Form(None),
    files: List[UploadFile] = File([])
):
    """Stream the analysis of a log entry.

    Args:
        request: The request containing the log text.
        log_text: The log text from a form.
        files: List of uploaded log files.

    Returns:
        A streaming response with the analysis.
    """
    try:
        # Get the log text from either the JSON body, form field, or files
        text_to_analyze = ""
        if request and hasattr(request, 'question'):
            text_to_analyze = request.question
        elif log_text:
            text_to_analyze = log_text
        elif files and len(files) > 0:
            # Read the first file
            file = files[0]
            content = await file.read()
            text_to_analyze = content.decode('utf-8')
        else:
            raise HTTPException(status_code=400, detail="Log text is required")
            
        logger.debug(f"Received log text for streaming: {text_to_analyze[:100]}...")
        
        async def event_generator():
            """Generate events for the streaming response."""
            try:
                # Create a new memory for this session to avoid conflicts
                session_memory = llama_index_service.memory.__class__(token_limit=8000)
                
                workflow = llama_index_service.LogAnalysis(
                    timeout=60,  # Add a timeout to prevent hanging
                    verbose=True, 
                    llm=llama_index_service.llm,
                    memory=session_memory
                )
                ctx = Context(workflow)
                
                # Start the workflow
                handler = workflow.run(user_input=text_to_analyze, ctx=ctx)
                
                # Track if we're waiting for input
                waiting_for_input = False
                final_result = None
                
                # Send an initial event to establish the connection
                yield {"event": "message", "data": "Starting log analysis..."}
                
                # Process events with a timeout
                try:
                    async for event in handler.stream_events():
                        event_type = type(event).__name__
                        logger.debug(f"Received event: {event_type}")
                        
                        if hasattr(event, 'token') and event.token:
                            # Ensure token is a string
                            token = str(event.token)
                            if token.strip():  # Only send non-empty tokens
                                yield {"event": "token", "data": token}
                        elif isinstance(event, InputRequiredEvent):
                            waiting_for_input = True
                            yield {"event": "input_required", "data": event.prefix}
                            # Auto-respond with "done" to avoid hanging
                            await asyncio.sleep(0.5)  # Small delay for frontend to process
                            handler.ctx.send_event(HumanResponseEvent(response="done"))
                            waiting_for_input = False
                        elif hasattr(event, 'message') and event.message:
                            # Ensure message is a string
                            message = str(event.message)
                            if message.strip():  # Only send non-empty messages
                                yield {"event": "message", "data": message}
                        elif isinstance(event, StopEvent):
                            # Store the final result
                            if hasattr(event, 'message'):
                                final_result = str(event.message)
                                logger.debug(f"Received StopEvent with message: {final_result[:100]}...")
                            else:
                                logger.debug("Received StopEvent without message")
                        
                        # Add a small delay to prevent CPU spinning
                        await asyncio.sleep(0.01)
                    
                    # Wait for the handler to complete
                    await asyncio.wait_for(handler, timeout=30)
                    
                except asyncio.TimeoutError:
                    logger.warning("Streaming timed out, sending completion event")
                    if waiting_for_input:
                        # If we're waiting for input, send a default response
                        handler.ctx.send_event(HumanResponseEvent(response="done"))
                
                # Send the final result if we have one
                if final_result and final_result.strip():
                    logger.debug("Sending final result")
                    yield {"event": "message", "data": final_result}
                
                yield {"event": "done", "data": "Analysis complete"}
                
            except Exception as e:
                logger.error(f"Error in streaming log analysis: {e}")
                logger.error(traceback.format_exc())
                yield {"event": "error", "data": str(e)}
        
        return EventSourceResponse(
            event_generator(),
            media_type="text/event-stream",
            ping=10000,  # Send a ping every 10 seconds to keep the connection alive
        )
        
    except Exception as e:
        logger.error(f"Error setting up streaming log analysis: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze-log/respond")
@api_error_handler
async def analyze_log_respond(
    conversation_id: Optional[str] = Form(None),
    user_response: str = Form(...),
):
    """Handle a user response to a streaming log analysis.

    Args:
        conversation_id: An optional ID to identify the conversation.
        user_response: The user's response to a prompt.

    Returns:
        A streaming response with the continued analysis.
    """
    try:
        logger.debug(f"Received user response: {user_response}")
        
        async def event_generator():
            """Generate events for the streaming response."""
            try:
                # Send an initial event to establish the connection
                yield {"event": "message", "data": f"Processing your response: {user_response}"}
                
                # In a real implementation, you would retrieve the existing workflow
                # based on the conversation_id. For now, we'll create a new one.
                session_memory = llama_index_service.memory.__class__(token_limit=8000)
                
                workflow = llama_index_service.LogAnalysis(
                    timeout=30, 
                    verbose=True, 
                    llm=llama_index_service.llm,
                    memory=session_memory
                )
                ctx = Context(workflow)
                
                # Send the user response event
                ctx.send_event(HumanResponseEvent(response=user_response))
                
                # In a real implementation, you would continue the existing workflow
                # For now, we'll just generate a simple response
                response = f"Thank you for your response: '{user_response}'. In a real implementation, this would continue the conversation with the LLM."
                
                # Stream the response token by token
                for char in response:
                    if char.strip():  # Only send non-empty characters
                        yield {"event": "token", "data": char}
                    await asyncio.sleep(0.01)  # Simulate streaming
                
                yield {"event": "done", "data": "Response complete"}
                
            except Exception as e:
                logger.error(f"Error processing user response: {e}")
                logger.error(traceback.format_exc())
                yield {"event": "error", "data": str(e)}
        
        return EventSourceResponse(
            event_generator(),
            media_type="text/event-stream",
            ping=5000,  # Send a ping every 5 seconds to keep the connection alive
        )
        
    except Exception as e:
        logger.error(f"Error setting up response handling: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.websocket("/ws/analyze-log")
async def analyze_log_websocket(websocket: WebSocket):
    """WebSocket endpoint for streaming log analysis.
    
    This provides a more efficient bidirectional communication channel
    compared to the SSE implementation.
    """
    await websocket.accept()
    
    # Generate a unique session ID for this connection
    session_id = f"ws_{id(websocket)}_{int(time.time())}"
    
    try:
        while True:  # Keep the connection open for multiple interactions
            # Receive the next message from the client
            data = await websocket.receive_json()
            
            # Handle ping messages to keep the connection alive
            if data.get("ping") is True:
                # Refresh the session if it exists
                if session_id:
                    llama_index_service.session_manager.refresh_session(session_id)
                await websocket.send_json({"type": "pong", "data": "pong"})
                continue
            
            # Get the message content and log text
            message = data.get("message", "")
            log_text = data.get("log_text", "")
            
            # We need either a message or log text
            if not message and not log_text:
                await websocket.send_json({"type": "error", "data": "Message or log text is required"})
                continue
            
            # Check if we have an existing session
            session = llama_index_service.session_manager.get_session(session_id)
            
            # Send appropriate initial message
            if session is None and log_text:
                await websocket.send_json({"type": "message", "data": "Starting log analysis..."})
            else:
                await websocket.send_json({"type": "message", "data": "Processing your message..."})
            
            try:
                # If we don't have a session but have log text, create a new session
                if session is None:
                    if not log_text:
                        await websocket.send_json({
                            "type": "error", 
                            "data": "No active session found and no log text provided. Please provide log text to start a new analysis."
                        })
                        continue
                    
                    # Create a new session
                    workflow, ctx, session_memory = llama_index_service.session_manager.create_session(
                        session_id, llama_index_service.llm
                    )
                    
                    # Process the log text
                    user_input = log_text
                    if message:
                        # If we also have a message, include it with the log text
                        user_input = f"{log_text}\n\nQuestion: {message}"
                else:
                    # Use the existing session
                    workflow, ctx, session_memory = session
                    
                    # Update the last accessed time
                    llama_index_service.session_manager.last_accessed[session_id] = time.time()
                    
                    # Process the message
                    user_input = message
                
                # Run the workflow with the appropriate input
                handler = workflow.run(user_input=user_input, ctx=ctx)
                
                # Process the events
                await process_workflow_events(websocket, workflow, ctx, handler)
                
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                logger.error(traceback.format_exc())
                await websocket.send_json({"type": "error", "data": f"Error processing message: {str(e)}"})
            
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
        # Clean up the session when the WebSocket disconnects
        if session_id:
            llama_index_service.session_manager.delete_session(session_id)
    except Exception as e:
        logger.error(f"Error in WebSocket log analysis: {e}")
        logger.error(traceback.format_exc())
        try:
            await websocket.send_json({"type": "error", "data": str(e)})
            # Keep the connection open for a moment to ensure the error message is sent
            await asyncio.sleep(1)
        except:
            pass  # Client might be disconnected already


async def process_workflow_events(websocket: WebSocket, workflow, ctx, handler=None):
    """Process events from a workflow and send them to the WebSocket client."""
    if handler is None:
        return
    
    event_handlers = {
        StopEvent: handle_stop_event,
        InputRequiredEvent: handle_input_required_event,
    }
    
    waiting_for_input = False
    final_analysis_started = False
    current_step = None
    tokens_streamed = 0  # Track how many tokens have been streamed
    
    try:
        async for event in handler.stream_events():
            # Handle different event types
            event_type = type(event)
            
            # Identify the current workflow step if possible
            if hasattr(event, '_step_name'):
                previous_step = current_step
                current_step = event._step_name
                
                # Check if we've moved to the final analysis step
                if current_step == "llm_analysis_log" and previous_step != "llm_analysis_log":
                    final_analysis_started = True
                    tokens_streamed = 0  # Reset token counter for final analysis
                    # Clear any previous content
                    await websocket.send_json({"type": "clear_analysis", "data": True})
                    logger.info("Final analysis step started, clearing previous content")
            
            # Alternative detection based on message content
            if hasattr(event, 'message') and event.message and isinstance(event.message, str):
                if not final_analysis_started:
                    # Look for the title that indicates the final analysis
                    if "EMQX Log Analysis - Final Report" in event.message:
                        final_analysis_started = True
                        tokens_streamed = 0  # Reset token counter for final analysis
                        # Clear any previous content
                        await websocket.send_json({"type": "clear_analysis", "data": True})
                        logger.info("Final analysis detected by title, clearing previous content")
            
            # Important: Always stream tokens from all steps 
            if hasattr(event, 'token') and event.token:
                # For the llm_analysis_log step, we want to stream all tokens
                # For other steps, only stream if we're in the final analysis
                if current_step == "llm_analysis_log" or final_analysis_started:
                    token = str(event.token)
                    tokens_streamed += len(token)
                    await websocket.send_json({"type": "token", "data": token})
                    logger.debug(f"Streaming token: {token}")
                    
                    # Log progress occasionally
                    if tokens_streamed % 500 == 0:
                        logger.info(f"Streamed {tokens_streamed} tokens so far for final analysis")
            
            # Handle events based on type (like StopEvent)
            elif event_type in event_handlers:
                if event_type == StopEvent and current_step == "llm_analysis_log":
                    logger.info(f"Final analysis complete, streamed {tokens_streamed} tokens")
                await event_handlers[event_type](websocket, ctx, event, waiting_for_input)
            
            # Handle full messages (not tokens)
            elif hasattr(event, 'message') and event.message:
                # Only send the message if it's part of the final analysis or a special event type
                message = str(event.message)
                if message.strip():
                    if final_analysis_started or current_step == "llm_analysis_log":
                        # For the final analysis step, we don't want to send full messages
                        # as they should be streamed token by token instead
                        logger.debug(f"Skipping full message for final analysis: {message[:30]}...")
                    else:
                        # For other steps, we can send the message
                        await websocket.send_json({"type": "message", "data": message})
    except Exception as e:
        logger.error(f"Error processing workflow events: {e}")
        logger.error(traceback.format_exc())
        await websocket.send_json({"type": "error", "data": str(e)})


async def handle_stop_event(websocket, ctx, event, waiting_for_input):
    """Handle a StopEvent."""
    # Check if the StopEvent has a message that wasn't fully streamed
    if hasattr(event, 'message') and event.message and isinstance(event.message, str):
        message = str(event.message)
        if message.strip():
            # Log that we're sending the final report
            logger.info(f"Ensuring final report is sent (length: {len(message)})")
            
            # Check if this appears to be the final report
            if "EMQX Log Analysis - Final Report" in message:
                logger.info("Final report title detected in StopEvent message, ensuring it's sent")
                
                # Send the message as a special final_report type to ensure it's properly handled
                await websocket.send_json({"type": "final_report", "data": message})
            else:
                logger.info("StopEvent message doesn't appear to be the final report")
    
    # Send the done signal
    logger.info("Sending 'done' signal")
    await websocket.send_json({"type": "done", "data": "Analysis complete"})


async def handle_input_required_event(websocket, ctx, event, waiting_for_input):
    """Handle an InputRequiredEvent."""
    waiting_for_input = True
    await websocket.send_json({"type": "input_required", "data": event.prefix})
    
    # Wait for user response
    try:
        # Set a timeout for user response
        response_data = await asyncio.wait_for(
            websocket.receive_json(), 
            timeout=60  # 60 second timeout for user response
        )
        user_response = response_data.get("response", "done")
        ctx.send_event(HumanResponseEvent(response=user_response))
    except asyncio.TimeoutError:
        # Auto-respond with "done" if user doesn't respond in time
        ctx.send_event(HumanResponseEvent(response="done"))
        await websocket.send_json({"type": "message", "data": "Response timeout, continuing analysis..."})
    
    waiting_for_input = False


@router.get("/health")
async def health_check():
    """Health check endpoint.

    Returns:
        A simple health check response.
    """
    return {"status": "ok"}
