"""API routes for the application."""
import logging
import traceback
from typing import List, Optional
import tempfile
import os

from fastapi import APIRouter, HTTPException, UploadFile, File, Form

from app.api.models import AnswerResponse, QuestionRequest, SourceReference, FileReference
from app.models.knowledge import FileType, FileAttachment
from app.services.database import db_service
from app.services.openai_service import openai_service
from app.services.file_service import file_service
from app.services.llama_index_service import llama_index_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/ask", response_model=AnswerResponse)
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
    try:
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
        question_embedding = openai_service.create_embedding(question_text)
        
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
    except Exception as e:
        logger.error(f"Error processing question: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze-log", response_model=AnswerResponse)
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


@router.get("/health")
async def health_check():
    """Health check endpoint.

    Returns:
        A simple health check response.
    """
    return {"status": "ok"}
