"""Async task-based streaming for MCP protocol.

Since MCP protocol (JSON-RPC 2.0) doesn't support true streaming,
we implement a polling-based solution with background tasks.

Architecture:
1. Client calls kiro_chat_async to start a background task
2. Client polls kiro_task_status to get progress and partial results
3. When task completes, full response is available

This gives users real-time feedback instead of waiting silently.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """Status of an async task."""
    
    PENDING = "pending"
    RUNNING = "running"
    STREAMING = "streaming"  # Actively receiving chunks
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class StreamChunk:
    """A chunk of streamed content."""
    
    content: str
    index: int
    timestamp: datetime = field(default_factory=datetime.now)
    is_final: bool = False
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "content": self.content,
            "index": self.index,
            "timestamp": self.timestamp.isoformat(),
            "is_final": self.is_final,
        }


@dataclass
class AsyncTask:
    """An async task with streaming support."""
    
    task_id: str
    session_id: str
    message: str
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    
    # Progress tracking
    chunks: list[StreamChunk] = field(default_factory=list)
    last_chunk_index: int = 0
    total_bytes_received: int = 0
    
    # Result
    result: str | None = None
    error: str | None = None
    
    # Internal
    _task: asyncio.Task[Any] | None = field(default=None, repr=False)
    _cancelled: bool = False
    
    @property
    def is_done(self) -> bool:
        """Check if task is in a terminal state."""
        return self.status in (
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        )
    
    @property
    def duration_seconds(self) -> float | None:
        """Get task duration in seconds."""
        if self.started_at is None:
            return None
        end = self.completed_at or datetime.now()
        return (end - self.started_at).total_seconds()
    
    @property
    def progress_text(self) -> str:
        """Get current accumulated text from chunks."""
        return "".join(chunk.content for chunk in self.chunks)
    
    def add_chunk(self, content: str, is_final: bool = False) -> StreamChunk:
        """Add a new chunk to the task."""
        chunk = StreamChunk(
            content=content,
            index=len(self.chunks),
            is_final=is_final,
        )
        self.chunks.append(chunk)
        self.total_bytes_received += len(content.encode())
        self.last_chunk_index = chunk.index
        return chunk
    
    def get_chunks_since(self, from_index: int = 0) -> list[StreamChunk]:
        """Get chunks since a given index."""
        return [c for c in self.chunks if c.index >= from_index]
    
    def to_dict(self, include_chunks: bool = False) -> dict[str, Any]:
        """Convert to dictionary for JSON response."""
        data: dict[str, Any] = {
            "task_id": self.task_id,
            "session_id": self.session_id,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "total_bytes_received": self.total_bytes_received,
            "chunks_count": len(self.chunks),
            "last_chunk_index": self.last_chunk_index,
        }
        
        if self.status == TaskStatus.COMPLETED:
            data["result"] = self.result
        elif self.status == TaskStatus.FAILED:
            data["error"] = self.error
        
        if include_chunks:
            data["chunks"] = [c.to_dict() for c in self.chunks]
        
        return data
    
    def to_status_dict(self, from_chunk_index: int = 0) -> dict[str, Any]:
        """Get status with new chunks since last poll."""
        new_chunks = self.get_chunks_since(from_chunk_index)
        
        data: dict[str, Any] = {
            "task_id": self.task_id,
            "status": self.status.value,
            "is_done": self.is_done,
            "total_bytes_received": self.total_bytes_received,
            "last_chunk_index": self.last_chunk_index,
            "new_chunks": [c.to_dict() for c in new_chunks],
            "new_content": "".join(c.content for c in new_chunks),
        }
        
        if self.status == TaskStatus.COMPLETED:
            data["result"] = self.result
        elif self.status == TaskStatus.FAILED:
            data["error"] = self.error
        
        return data


# Type alias for task executor function
TaskExecutor = Callable[[AsyncTask], Awaitable[str]]


class StreamingTaskManager:
    """Manager for async streaming tasks.
    
    This provides polling-based streaming for MCP clients.
    
    Usage:
    1. start_task() - Start a background task
    2. get_task_status() - Poll for updates
    3. cancel_task() - Cancel if needed
    
    Example flow:
    ```
    # Start task
    task = await manager.start_task(
        session_id="session-123",
        message="Explain Python",
        executor=chat_executor,
    )
    
    # Poll for updates
    while True:
        status = await manager.get_task_status(task.task_id)
        if status["is_done"]:
            break
        print(status["new_content"], end="", flush=True)
        await asyncio.sleep(0.5)
    
    print(status["result"])
    ```
    """
    
    def __init__(
        self,
        max_tasks: int = 100,
        task_ttl: float = 3600.0,  # 1 hour
        cleanup_interval: float = 60.0,  # 1 minute
    ) -> None:
        self.max_tasks = max_tasks
        self.task_ttl = task_ttl
        self.cleanup_interval = cleanup_interval
        
        self._tasks: dict[str, AsyncTask] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task[None] | None = None
        self._shutdown = False
    
    async def start(self) -> None:
        """Start the background cleanup task."""
        if self._cleanup_task is not None:
            return
        
        async def cleanup_loop() -> None:
            while not self._shutdown:
                try:
                    await asyncio.sleep(self.cleanup_interval)
                    await self._cleanup_old_tasks()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.warning(f"Task cleanup error: {e}")
        
        self._cleanup_task = asyncio.create_task(cleanup_loop())
        logger.info("🔄 Streaming task manager started")
    
    async def stop(self) -> None:
        """Stop the manager and cancel all tasks."""
        self._shutdown = True
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
        
        # Cancel all running tasks
        async with self._lock:
            for task in self._tasks.values():
                if task._task and not task._task.done():
                    task._task.cancel()
            self._tasks.clear()
        
        logger.info("✅ Streaming task manager stopped")
    
    async def _cleanup_old_tasks(self) -> None:
        """Clean up completed tasks older than TTL."""
        now = datetime.now()
        
        async with self._lock:
            to_remove: list[str] = []
            
            for task_id, task in self._tasks.items():
                if task.is_done:
                    completed = task.completed_at or task.created_at
                    age = (now - completed).total_seconds()
                    if age > self.task_ttl:
                        to_remove.append(task_id)
            
            for task_id in to_remove:
                del self._tasks[task_id]
            
            if to_remove:
                logger.debug(f"Cleaned up {len(to_remove)} old tasks")
    
    def _generate_task_id(self) -> str:
        """Generate unique task ID."""
        return f"task-{uuid.uuid4().hex[:12]}"
    
    async def start_task(
        self,
        session_id: str,
        message: str,
        executor: TaskExecutor,
    ) -> AsyncTask:
        """Start a new async task.
        
        Args:
            session_id: Session ID for the task
            message: The message to process
            executor: Async function to execute the task
            
        Returns:
            The created AsyncTask
        """
        async with self._lock:
            # Check capacity
            active_count = sum(1 for t in self._tasks.values() if not t.is_done)
            if active_count >= self.max_tasks:
                raise RuntimeError(f"Maximum concurrent tasks ({self.max_tasks}) reached")
            
            # Create task
            task_id = self._generate_task_id()
            task = AsyncTask(
                task_id=task_id,
                session_id=session_id,
                message=message,
            )
            
            self._tasks[task_id] = task
        
        # Start background execution
        async def run_task() -> None:
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now()
            
            try:
                result = await executor(task)
                task.result = result
                task.status = TaskStatus.COMPLETED
            except asyncio.CancelledError:
                task.status = TaskStatus.CANCELLED
                raise
            except Exception as e:
                task.error = str(e)
                task.status = TaskStatus.FAILED
                logger.error(f"Task {task_id} failed: {e}")
            finally:
                task.completed_at = datetime.now()
        
        task._task = asyncio.create_task(run_task())
        logger.info(f"Started task {task_id} for session {session_id}")
        
        return task
    
    async def get_task(self, task_id: str) -> AsyncTask | None:
        """Get a task by ID."""
        return self._tasks.get(task_id)
    
    async def get_task_status(
        self,
        task_id: str,
        from_chunk_index: int = 0,
    ) -> dict[str, Any] | None:
        """Get task status with new chunks since last poll.
        
        Args:
            task_id: Task ID to check
            from_chunk_index: Get chunks starting from this index
            
        Returns:
            Status dict or None if task not found
        """
        task = self._tasks.get(task_id)
        if task is None:
            return None
        return task.to_status_dict(from_chunk_index)
    
    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task.
        
        Args:
            task_id: Task ID to cancel
            
        Returns:
            True if task was cancelled
        """
        task = self._tasks.get(task_id)
        if task is None:
            return False
        
        if task._task and not task._task.done():
            task._cancelled = True
            task._task.cancel()
            try:
                await task._task
            except asyncio.CancelledError:
                pass
            return True
        
        return False
    
    async def list_tasks(
        self,
        session_id: str | None = None,
        include_done: bool = False,
    ) -> list[AsyncTask]:
        """List tasks, optionally filtered by session.
        
        Args:
            session_id: Filter by session ID
            include_done: Include completed/failed tasks
            
        Returns:
            List of matching tasks
        """
        tasks = list(self._tasks.values())
        
        if session_id:
            tasks = [t for t in tasks if t.session_id == session_id]
        
        if not include_done:
            tasks = [t for t in tasks if not t.is_done]
        
        return tasks


class StreamingChatExecutor:
    """Executor that provides chunk-based progress updates.
    
    This wraps the actual chat execution to provide streaming chunks
    to the task for progress updates.
    """
    
    def __init__(
        self,
        command_executor: Any,  # CommandExecutor
        chunk_size: int = 256,
        progress_interval: float = 0.5,
    ) -> None:
        self.command_executor = command_executor
        self.chunk_size = chunk_size
        self.progress_interval = progress_interval
    
    async def execute(
        self,
        task: AsyncTask,
        session: Any,  # Session
    ) -> str:
        """Execute chat with streaming progress updates.
        
        This method:
        1. Starts the actual chat execution
        2. Periodically adds progress chunks to the task
        3. Returns final result
        
        Args:
            task: The AsyncTask to update with progress
            session: The session to use
            
        Returns:
            Final response text
        """
        task.status = TaskStatus.STREAMING
        
        # Add initial progress message
        task.add_chunk("Processing your request...\n")
        
        # Execute the actual chat
        try:
            response = await self.command_executor.execute_chat(
                session,
                task.message,
                stream=False,  # We handle chunking ourselves
            )
            
            # Add the response as a final chunk
            content = response.content if hasattr(response, 'content') else str(response)
            task.add_chunk(content, is_final=True)
            
            return content
            
        except Exception as e:
            task.add_chunk(f"\nError: {e}", is_final=True)
            raise


def create_chat_task_executor(
    command_executor: Any,
    session: Any,
) -> TaskExecutor:
    """Create a task executor for chat.
    
    Args:
        command_executor: The CommandExecutor to use
        session: The Session to use
        
    Returns:
        A TaskExecutor function
    """
    streaming_executor = StreamingChatExecutor(command_executor)
    
    async def executor(task: AsyncTask) -> str:
        return await streaming_executor.execute(task, session)
    
    return executor
