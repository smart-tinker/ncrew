"""
File-based storage for conversation history and state management.

This module provides asynchronous file storage for managing conversation
histories and application state in JSON format.
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any
import aiofiles
import os

from app.config import Config
from app.utils.logger import get_logger


class FileStorage:
    """
    Asynchronous file-based storage system for NeuroCrew Lab.

    Manages conversation histories and application state using JSON files.
    """

    def __init__(self, data_dir: Optional[Path] = None):
        """
        Initialize the file storage.

        Args:
            data_dir: Data directory path. Uses Config.DATA_DIR if not provided.
        """
        self.data_dir = data_dir or Config.DATA_DIR
        self.conversations_dir = self.data_dir / 'conversations'
        self.logs_dir = self.data_dir / 'logs'
        self.logger = get_logger(f"{self.__class__.__name__}")

        # Ensure directories exist
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Ensure all required directories exist."""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.conversations_dir.mkdir(exist_ok=True)
            self.logs_dir.mkdir(exist_ok=True)
            self.logger.debug(f"Storage directories ensured: {self.data_dir}")
        except Exception as e:
            self.logger.error(f"Failed to create storage directories: {e}")
            raise

    def _get_conversation_file(self, chat_id: int) -> Path:
        """
        Get the file path for a conversation.

        Args:
            chat_id: Telegram chat ID

        Returns:
            Path: File path for the conversation
        """
        return self.conversations_dir / f'chat_{chat_id}.json'

    def _get_conversation_backup_file(self, chat_id: int) -> Path:
        """
        Get the backup file path for a conversation.

        Args:
            chat_id: Telegram chat ID

        Returns:
            Path: Backup file path for the conversation
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self.conversations_dir / f'chat_{chat_id}_backup_{timestamp}.json'

    async def load_conversation(self, chat_id: int) -> List[Dict]:
        """
        Load conversation history from file.

        Args:
            chat_id: Telegram chat ID

        Returns:
            List[Dict]: Conversation history (empty list if file doesn't exist)
        """
        file_path = self._get_conversation_file(chat_id)

        if not file_path.exists():
            self.logger.debug(f"Conversation file for chat {chat_id} not found, starting fresh")
            return []

        try:
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()

                if not content.strip():
                    self.logger.warning(f"Empty conversation file for chat {chat_id}")
                    return []

                data = json.loads(content)

                # Handle new storage format with metadata
                if isinstance(data, dict) and 'conversation' in data:
                    conversation = data['conversation']
                else:
                    # Handle old format (direct list)
                    conversation = data

                # Validate conversation structure
                if not isinstance(conversation, list):
                    self.logger.error(f"Invalid conversation format for chat {chat_id}, expected list")
                    return []

                self.logger.debug(f"Loaded {len(conversation)} messages for chat {chat_id}")
                return conversation

        except json.JSONDecodeError as e:
            self.logger.error(f"JSON decode error for chat {chat_id}: {e}")
            # Try to create backup before starting fresh
            await self._backup_corrupted_file(file_path, chat_id)
            return []
        except Exception as e:
            self.logger.error(f"Error loading conversation for chat {chat_id}: {e}")
            return []

    async def save_conversation(self, chat_id: int, conversation: List[Dict]) -> bool:
        """
        Save conversation history to file.

        Args:
            chat_id: Telegram chat ID
            conversation: Conversation history to save

        Returns:
            bool: True if save was successful, False otherwise
        """
        file_path = self._get_conversation_file(chat_id)

        try:
            # Validate conversation structure
            if not isinstance(conversation, list):
                raise ValueError("Conversation must be a list")

            # Limit conversation length if configured
            if len(conversation) > Config.MAX_CONVERSATION_LENGTH:
                conversation = conversation[-Config.MAX_CONVERSATION_LENGTH:]
                self.logger.debug(f"Truncated conversation for chat {chat_id} to {Config.MAX_CONVERSATION_LENGTH} messages")

            # Add metadata
            metadata = {
                'chat_id': chat_id,
                'message_count': len(conversation),
                'last_updated': datetime.now().isoformat(),
                'version': '1.0'
            }

            # Prepare file content with metadata
            file_content = {
                'metadata': metadata,
                'conversation': conversation
            }

            # Write to temporary file first (atomic operation)
            temp_file = file_path.with_suffix('.tmp')
            async with aiofiles.open(temp_file, 'w', encoding='utf-8') as f:
                json_content = json.dumps(file_content, ensure_ascii=False, indent=2)
                await f.write(json_content)

            # Atomic rename
            temp_file.rename(file_path)

            self.logger.debug(f"Saved {len(conversation)} messages for chat {chat_id}")
            return True

        except Exception as e:
            self.logger.error(f"Error saving conversation for chat {chat_id}: {e}")
            return False

    async def add_message(self, chat_id: int, message: Dict) -> bool:
        """
        Add a single message to the conversation.

        Args:
            chat_id: Telegram chat ID
            message: Message dictionary to add

        Returns:
            bool: True if message was added successfully
        """
        try:
            # Validate message structure
            if not isinstance(message, dict):
                raise ValueError("Message must be a dictionary")

            required_fields = ['role']
            for field in required_fields:
                if field not in message:
                    raise ValueError(f"Message missing required field: {field}")

            # Add timestamp if not present
            if 'timestamp' not in message:
                message['timestamp'] = datetime.now().isoformat()

            # Load existing conversation
            conversation = await self.load_conversation(chat_id)
            conversation.append(message)

            # Save updated conversation
            return await self.save_conversation(chat_id, conversation)

        except Exception as e:
            self.logger.error(f"Error adding message to conversation {chat_id}: {e}")
            return False

    async def get_last_messages(self, chat_id: int, count: int = 5) -> List[Dict]:
        """
        Get the last N messages from a conversation.

        Args:
            chat_id: Telegram chat ID
            count: Number of messages to retrieve

        Returns:
            List[Dict]: Last N messages
        """
        conversation = await self.load_conversation(chat_id)
        return conversation[-count:] if count > 0 else []

    async def clear_conversation(self, chat_id: int) -> bool:
        """
        Clear conversation history for a chat.

        Args:
            chat_id: Telegram chat ID

        Returns:
            bool: True if cleared successfully
        """
        try:
            file_path = self._get_conversation_file(chat_id)

            # Create backup before deleting
            if file_path.exists():
                backup_path = self._get_conversation_backup_file(chat_id)
                file_path.rename(backup_path)
                self.logger.info(f"Created backup of conversation {chat_id}: {backup_path}")

            return True

        except Exception as e:
            self.logger.error(f"Error clearing conversation {chat_id}: {e}")
            return False

    async def get_all_chat_ids(self) -> List[int]:
        """
        Get all chat IDs with stored conversations.

        Returns:
            List[int]: List of chat IDs
        """
        try:
            chat_ids = []
            for file_path in self.conversations_dir.glob('chat_*.json'):
                # Extract chat ID from filename
                parts = file_path.stem.split('_')
                if len(parts) >= 2 and parts[1].isdigit():
                    chat_ids.append(int(parts[1]))

            return sorted(chat_ids)

        except Exception as e:
            self.logger.error(f"Error getting chat IDs: {e}")
            return []

    async def get_storage_stats(self) -> Dict[str, Any]:
        """
        Get storage statistics.

        Returns:
            Dict[str, Any]: Storage statistics
        """
        try:
            chat_ids = await self.get_all_chat_ids()
            total_messages = 0
            total_size = 0

            for chat_id in chat_ids:
                file_path = self._get_conversation_file(chat_id)
                if file_path.exists():
                    total_size += file_path.stat().st_size
                    conversation = await self.load_conversation(chat_id)
                    total_messages += len(conversation)

            return {
                'total_chats': len(chat_ids),
                'total_messages': total_messages,
                'total_size_bytes': total_size,
                'total_size_mb': round(total_size / (1024 * 1024), 2),
                'average_messages_per_chat': round(total_messages / len(chat_ids), 2) if chat_ids else 0
            }

        except Exception as e:
            self.logger.error(f"Error getting storage stats: {e}")
            return {}

    async def cleanup_old_backups(self, days_to_keep: int = 7) -> int:
        """
        Clean up old backup files.

        Args:
            days_to_keep: Number of days to keep backup files

        Returns:
            int: Number of files cleaned up
        """
        try:
            cutoff_time = datetime.now().timestamp() - (days_to_keep * 24 * 3600)
            cleaned_count = 0

            for backup_file in self.conversations_dir.glob('*_backup_*.json'):
                if backup_file.stat().st_mtime < cutoff_time:
                    backup_file.unlink()
                    cleaned_count += 1
                    self.logger.debug(f"Deleted old backup: {backup_file}")

            self.logger.info(f"Cleaned up {cleaned_count} old backup files")
            return cleaned_count

        except Exception as e:
            self.logger.error(f"Error cleaning up backups: {e}")
            return 0

    async def _backup_corrupted_file(self, file_path: Path, chat_id: int) -> None:
        """
        Create backup of a corrupted file.

        Args:
            file_path: Path to corrupted file
            chat_id: Chat ID for naming
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = self.conversations_dir / f'chat_{chat_id}_corrupted_{timestamp}.json'
            file_path.rename(backup_path)
            self.logger.warning(f"Corrupted file backed up: {backup_path}")
        except Exception as e:
            self.logger.error(f"Failed to backup corrupted file {file_path}: {e}")

    async def verify_integrity(self, chat_id: int) -> Dict[str, bool]:
        """
        Verify conversation integrity for a chat.

        Args:
            chat_id: Telegram chat ID

        Returns:
            Dict[str, bool]: Integrity check results
        """
        results = {
            'file_exists': False,
            'file_readable': False,
            'valid_json': False,
            'valid_structure': False,
            'has_timestamps': False
        }

        try:
            file_path = self._get_conversation_file(chat_id)
            results['file_exists'] = file_path.exists()

            if not results['file_exists']:
                return results

            # Test file readability
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
            results['file_readable'] = True

            # Test JSON validity
            data = json.loads(content)
            results['valid_json'] = True

            # Test structure (new format with metadata)
            if isinstance(data, dict) and 'conversation' in data:
                conversation = data['conversation']
            elif isinstance(data, list):
                conversation = data  # Legacy format
            else:
                return results

            results['valid_structure'] = isinstance(conversation, list)

            # Test timestamps
            if results['valid_structure'] and conversation:
                has_timestamps = all(
                    'timestamp' in msg for msg in conversation
                )
                results['has_timestamps'] = has_timestamps

        except Exception as e:
            self.logger.debug(f"Integrity check failed for chat {chat_id}: {e}")

        return results