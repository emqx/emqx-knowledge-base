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
            logger.debug(f"Processing {len(files)} uploaded files")
            for file in files:
                try:
                    # Create a temporary file
                    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_file:
                        # Write the file content
                        content = await file.read()
                        temp_file.write(content)
                        temp_file.flush()
                        
                        # Determine file type
                        file_extension = os.path.splitext(file.filename)[1].lower()
                        file_type = FileType.OTHER
                        if file_extension in ['.log', '.txt']:
                            file_type = FileType.LOG
                        elif file_extension in ['.jpg', '.jpeg', '.png', '.gif']:
                            file_type = FileType.IMAGE
                        elif file_extension == '.pdf':
                            file_type = FileType.PDF
                            
                        # Create a file attachment
                        file_attachment = FileAttachment(
                            channel_id="web_ui",
                            thread_ts="web_ui",
                            user_id="web_ui",
                            file_name=file.filename,
                            file_type=file_type,
                            file_url=temp_file.name,
                            content_summary=f"Uploaded file: {file.filename}"
                        )
                        
                        # Create embedding for the file content
                        if file_type in [FileType.LOG, FileType.OTHER]:
                            # For text files, use the content directly
                            file_attachment.content_text = content.decode('utf-8', errors='ignore')
                            file_attachment.embedding = openai_service.create_embedding(file_attachment.content_text)
                        
                        uploaded_file_attachments.append(file_attachment)
                        
                except Exception as e:
                    logger.error(f"Error processing file {file.filename}: {e}")
                    logger.error(traceback.format_exc())
        
        # Create embedding for the question
        question_embedding = openai_service.create_embedding(question_text)
        
        # Find similar entries in the knowledge base
        similar_entries = db_service.find_similar_entries(
            question_embedding, 
            limit=5, 
            threshold=0.5
        )
        
        # Get file attachments that might be relevant
        similar_file_attachments = db_service.find_similar_file_attachments(
            question_embedding,
            limit=3,
            threshold=0.5
        )
        
        # Extract just the file attachments from the tuples
        file_attachments = [attachment for attachment, _ in similar_file_attachments]
        
        # Add uploaded files to the file attachments
        file_attachments.extend(uploaded_file_attachments)
        
        # Generate a response using OpenAI
        entries = [entry for entry, _ in similar_entries]
        response = openai_service.generate_response(
            question_text, 
            entries, 
            file_attachments
        )

        # Convert to API response format
        source_references = []
        for source in response.sources:
            # Get a snippet of the content (first 100 characters)
            content_snippet = source.content[:100] + "..." if len(source.content) > 100 else source.content
            source_references.append(
                SourceReference(
                    id=source.id,
                    content_snippet=content_snippet
                )
            )

        file_references = []
        for file in response.file_sources:
            file_references.append(
                FileReference(
                    id=file.id,
                    file_name=file.file_name,
                    file_type=file.file_type
                )
            )

        return AnswerResponse(
            answer=response.answer,
            sources=source_references,
            file_sources=file_references,
            confidence=response.confidence
        )

    except Exception as e:
        logger.error(f"Error answering question: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while processing your question: {str(e)}"
        )
