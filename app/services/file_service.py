"""Service for processing file attachments."""
import logging
import os
import requests
import tempfile
from typing import Optional, Tuple

from app.config import config
from app.models.knowledge import FileAttachment, FileType
from app.services.database import db_service
from app.services.openai_service import openai_service

logger = logging.getLogger(__name__)


class FileService:
    """Service for processing file attachments."""

    def process_file(
        self, file_url: str, file_name: str, channel_id: str, thread_ts: str, user_id: str
    ) -> Optional[FileAttachment]:
        """Process a file attachment and save it to the database.
        
        Args:
            file_url: The URL of the file.
            file_name: The name of the file.
            channel_id: The Slack channel ID.
            thread_ts: The Slack thread timestamp.
            user_id: The Slack user ID.
            
        Returns:
            The saved file attachment, or None if processing failed.
        """
        try:
            # Determine file type
            file_type, content_text = self._extract_file_content(file_url, file_name)
            
            # Generate a summary of the file content
            content_summary = self._generate_file_summary(content_text, file_type, file_name)
            
            # Create embedding for the file content
            embedding = []
            if content_text:
                # Use a combination of summary and content for embedding
                embedding_text = f"{content_summary}\n\n{content_text[:1000]}"  # Limit content length
                embedding = openai_service.create_embedding(embedding_text)
            
            # Create and save the file attachment
            attachment = FileAttachment(
                channel_id=channel_id,
                thread_ts=thread_ts,
                user_id=user_id,
                file_name=file_name,
                file_type=file_type,
                file_url=file_url,
                content_summary=content_summary,
                content_text=content_text,
                embedding=embedding,
            )
            
            attachment_id = db_service.save_file_attachment(attachment)
            attachment.id = attachment_id
            
            return attachment
        except Exception as e:
            logger.error(f"Error processing file {file_name}: {e}")
            return None
    
    def _extract_file_content(self, file_url: str, file_name: str) -> Tuple[FileType, str]:
        """Extract content from a file.
        
        Args:
            file_url: The URL of the file.
            file_name: The name of the file.
            
        Returns:
            A tuple of (file_type, content_text).
        """
        # Determine file type based on extension
        extension = os.path.splitext(file_name)[1].lower()
        
        try:
            # Download the file from Slack
            # Slack private URLs require authentication
            headers = {"Authorization": f"Bearer {config.slack_bot_token}"}
            
            response = requests.get(file_url, headers=headers, timeout=30)
            
            if response.status_code != 200:
                logger.error(f"Failed to download file: {response.status_code}")
                return self._determine_file_type(extension), f"Error downloading file: {response.status_code}"
            
            # Save the file to a temporary location
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_file.write(response.content)
                temp_path = temp_file.name
            
            # Extract content based on file type
            content = self._extract_content_by_type(temp_path, extension)
            
            # Clean up the temporary file
            os.unlink(temp_path)
            
            file_type = self._determine_file_type(extension)
            return file_type, content
            
        except Exception as e:
            logger.error(f"Error extracting content from file {file_name}: {e}")
            # Return a placeholder for now
            return self._determine_file_type(extension), f"Error extracting content: {str(e)}"
    
    def _determine_file_type(self, extension: str) -> FileType:
        """Determine the file type based on extension.
        
        Args:
            extension: The file extension.
            
        Returns:
            The file type.
        """
        if extension in ['.log', '.txt', '.json', '.yml', '.yaml', '.xml']:
            return FileType.LOG
        elif extension in ['.png', '.jpg', '.jpeg', '.gif']:
            return FileType.IMAGE
        elif extension == '.pdf':
            return FileType.PDF
        else:
            return FileType.OTHER
    
    def _extract_content_by_type(self, file_path: str, extension: str) -> str:
        """Extract content from a file based on its type.
        
        Args:
            file_path: The path to the file.
            extension: The file extension.
            
        Returns:
            The extracted content.
        """
        # In a real implementation, you would use appropriate libraries for each file type
        # This is a simplified version that just reads text files
        
        if extension in ['.log', '.txt', '.json', '.yml', '.yaml', '.xml']:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        
        # For other file types, return a placeholder
        # In a real implementation, you would use OCR for images, PDF extraction for PDFs, etc.
        return f"Content extracted from {os.path.basename(file_path)}"
    
    def _generate_file_summary(self, content_text: str, file_type: FileType, file_name: str) -> str:
        """Generate a summary of the file content.
        
        Args:
            content_text: The extracted text content.
            file_type: The type of file.
            file_name: The name of the file.
            
        Returns:
            A summary of the file content.
        """
        # In a real implementation, you would use OpenAI to generate a summary
        # This is a simplified placeholder
        if not content_text:
            return f"File: {file_name} (No extractable content)"
        
        if file_type == FileType.LOG:
            return f"Log file: {file_name} containing system logs"
        elif file_type == FileType.IMAGE:
            return f"Image file: {file_name} showing a screenshot or diagram"
        elif file_type == FileType.PDF:
            return f"PDF document: {file_name} with technical content"
        else:
            return f"File: {file_name} with miscellaneous content"


# Create a global file service instance
file_service = FileService() 