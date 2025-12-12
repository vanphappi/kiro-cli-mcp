"""Main MCP Server implementation for Kiro CLI."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, AsyncIterator

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.types import (
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
)

from .config import ServerConfig, ConfigManager
from .session import SessionManager
from .executor import CommandExecutor
from .tools import get_all_tools, get_tool_by_name
from .resources import get_all_resources, get_resource_by_uri
from .errors import MCPError, ErrorCode
from .streaming import StreamingTaskManager, create_chat_task_executor

logger = logging.getLogger(__name__)


def create_mcp_server(config: ServerConfig) -> Server:
    """Create and configure MCP server with all handlers.

    Args:
        config: Server configuration

    Returns:
        Configured MCP Server instance
    """
    # Create MCP server
    server = Server("kiro-cli-mcp")

    # Create internal components
    session_manager = SessionManager(config)
    command_executor = CommandExecutor(config)
    task_manager = StreamingTaskManager(
        max_tasks=config.max_async_tasks,
        task_ttl=config.task_ttl,
    )
    
    # Flag to track if services started
    _services_started = False
    
    async def _ensure_services_started() -> None:
        nonlocal _services_started
        if not _services_started:
            await session_manager.start_background_cleanup(config.cleanup_interval)
            await command_executor.start_pool()
            await task_manager.start()
            _services_started = True
            logger.info(
                f"🚀 Services started: "
                f"cleanup={config.cleanup_interval}s, "
                f"pool={'enabled' if config.pool_enabled else 'disabled'}, "
                f"max_tasks={config.max_async_tasks}"
            )

    # Register list_tools handler
    @server.list_tools()
    async def handle_list_tools() -> list[Tool]:
        """List available tools."""
        tools_data = get_all_tools()
        return [
            Tool(
                name=tool["name"],
                description=tool["description"],
                inputSchema=tool["inputSchema"]
            )
            for tool in tools_data
        ]

    # Register call_tool handler
    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent | ImageContent | EmbeddedResource]:
        """Handle tool calls."""
        logger.debug(f"Tool call: {name} with args: {arguments}")
        
        # Ensure services are running on first tool call
        await _ensure_services_started()
        
        # Update heartbeat for session if provided
        session_id = arguments.get("session_id")
        if session_id:
            session_manager.heartbeat(session_id)

        try:
            # Route to appropriate handler
            if name == "kiro_chat":
                result = await _handle_chat(session_manager, command_executor, arguments)
            elif name == "kiro_session_create":
                result = await _handle_session_create(session_manager, arguments)
            elif name == "kiro_session_list":
                result = await _handle_session_list(session_manager)
            elif name == "kiro_session_switch":
                result = await _handle_session_switch(session_manager, arguments)
            elif name == "kiro_session_end":
                result = await _handle_session_end(session_manager, arguments)
            elif name == "kiro_command":
                result = await _handle_command(session_manager, command_executor, arguments)
            elif name == "kiro_agents_list":
                result = await _handle_agents_list(command_executor)
            elif name == "kiro_history":
                result = await _handle_history(session_manager, arguments)
            elif name == "kiro_history_clear":
                result = await _handle_history_clear(session_manager, arguments)
            # New streaming/async tools
            elif name == "kiro_chat_async":
                result = await _handle_chat_async(
                    session_manager, command_executor, task_manager, arguments
                )
            elif name == "kiro_task_status":
                result = await _handle_task_status(task_manager, arguments)
            elif name == "kiro_task_cancel":
                result = await _handle_task_cancel(task_manager, arguments)
            elif name == "kiro_task_list":
                result = await _handle_task_list(task_manager, arguments)
            elif name == "kiro_pool_stats":
                result = await _handle_pool_stats(command_executor)
            elif name == "kiro_session_clear":
                result = await _handle_session_clear(session_manager, arguments)
            elif name == "kiro_session_save":
                result = await _handle_session_save(
                    session_manager, command_executor, arguments
                )
            else:
                raise MCPError(
                    code=ErrorCode.INVALID_COMMAND,
                    message=f"Unknown tool: {name}",
                )

            # Return as TextContent
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        except MCPError as e:
            logger.error(f"Tool call error: {e}")
            return [TextContent(
                type="text",
                text=json.dumps(e.to_dict(), indent=2)
            )]
        except Exception as e:
            logger.exception(f"Unexpected error in tool call: {name}")
            return [TextContent(
                type="text",
                text=json.dumps({
                    "error": str(e),
                    "tool": name
                }, indent=2)
            )]

    # Register list_resources handler
    @server.list_resources()
    async def handle_list_resources() -> list[dict[str, Any]]:
        """List available resources."""
        return get_all_resources()

    # Register read_resource handler
    @server.read_resource()
    async def handle_read_resource(uri: str) -> str:
        """Read a resource by URI."""
        if uri == "kiro://sessions":
            sessions = await session_manager.list_sessions()
            result = {
                "sessions": [s.to_info().to_dict() for s in sessions],
                "active_session_id": session_manager.active_session_id,
            }
        elif uri == "kiro://agents":
            agents = await command_executor.list_agents()
            result = {
                "agents": [a.to_dict() for a in agents],
            }
        elif uri == "kiro://config":
            result = config.to_dict()
        else:
            raise MCPError(
                code=ErrorCode.INVALID_COMMAND,
                message=f"Unknown resource URI: {uri}",
            )

        return json.dumps(result, indent=2)

    return server


# Tool handler functions
async def _handle_chat(
    session_manager: SessionManager,
    command_executor: CommandExecutor,
    arguments: dict[str, Any]
) -> dict[str, Any]:
    """Handle kiro_chat tool call."""
    message = arguments.get("message", "")
    session_id = arguments.get("session_id")
    stream = arguments.get("stream", False)

    session = await session_manager.get_or_create_session(session_id)

    if stream:
        # Note: Streaming not fully supported in current MCP SDK
        # Fall back to non-streaming
        logger.warning("Streaming requested but not fully supported, using non-streaming")

    response = await command_executor.execute_chat(session, message)
    return response.to_dict()


async def _handle_session_create(
    session_manager: SessionManager,
    arguments: dict[str, Any]
) -> dict[str, Any]:
    """Handle kiro_session_create tool call."""
    agent = arguments.get("agent")
    working_directory = arguments.get("working_directory")

    session = await session_manager.create_session(agent, working_directory)
    return session.to_info().to_dict()


async def _handle_session_list(session_manager: SessionManager) -> dict[str, Any]:
    """Handle kiro_session_list tool call."""
    sessions = await session_manager.list_sessions()
    return {
        "sessions": [s.to_info().to_dict() for s in sessions],
        "active_session_id": session_manager.active_session_id,
        "count": len(sessions),
    }


async def _handle_session_switch(
    session_manager: SessionManager,
    arguments: dict[str, Any]
) -> dict[str, Any]:
    """Handle kiro_session_switch tool call."""
    session_id = arguments.get("session_id", "")
    await session_manager.switch_session(session_id)
    return {
        "success": True,
        "active_session_id": session_id,
    }


async def _handle_session_end(
    session_manager: SessionManager,
    arguments: dict[str, Any]
) -> dict[str, Any]:
    """Handle kiro_session_end tool call."""
    session_id = arguments.get("session_id", "")
    await session_manager.end_session(session_id)
    return {
        "success": True,
        "session_id": session_id,
    }


async def _handle_command(
    session_manager: SessionManager,
    command_executor: CommandExecutor,
    arguments: dict[str, Any]
) -> dict[str, Any]:
    """Handle kiro_command tool call."""
    command = arguments.get("command", "")
    session_id = arguments.get("session_id")

    session = await session_manager.get_or_create_session(session_id)
    result = await command_executor.execute_command(session, command)

    return result.to_dict()


async def _handle_agents_list(command_executor: CommandExecutor) -> dict[str, Any]:
    """Handle kiro_agents_list tool call."""
    agents = await command_executor.list_agents()
    return {
        "agents": [a.to_dict() for a in agents],
        "count": len(agents),
    }


async def _handle_history(
    session_manager: SessionManager,
    arguments: dict[str, Any]
) -> dict[str, Any]:
    """Handle kiro_history tool call."""
    session_id = arguments.get("session_id")
    limit = arguments.get("limit", 50)

    session = await session_manager.get_or_create_session(session_id)
    history = session.get_history(limit)

    return {
        "session_id": session.id,
        "history": [msg.to_dict() for msg in history],
        "count": len(history),
    }


async def _handle_history_clear(
    session_manager: SessionManager,
    arguments: dict[str, Any]
) -> dict[str, Any]:
    """Handle kiro_history_clear tool call."""
    session_id = arguments.get("session_id")

    session = await session_manager.get_or_create_session(session_id)
    session.clear_history()

    return {
        "success": True,
        "session_id": session.id,
    }


async def _handle_chat_async(
    session_manager: SessionManager,
    command_executor: CommandExecutor,
    task_manager: StreamingTaskManager,
    arguments: dict[str, Any]
) -> dict[str, Any]:
    """Handle kiro_chat_async tool call - start async chat with polling support."""
    message = arguments.get("message", "")
    session_id = arguments.get("session_id")
    
    session = await session_manager.get_or_create_session(session_id)
    
    # Create task executor
    executor = create_chat_task_executor(command_executor, session)
    
    # Start async task
    task = await task_manager.start_task(
        session_id=session.id,
        message=message,
        executor=executor,
    )
    
    return {
        "task_id": task.task_id,
        "session_id": session.id,
        "status": task.status.value,
        "message": "Task started. Poll kiro_task_status for updates.",
    }


async def _handle_task_status(
    task_manager: StreamingTaskManager,
    arguments: dict[str, Any]
) -> dict[str, Any]:
    """Handle kiro_task_status tool call - get task status and partial results."""
    task_id = arguments.get("task_id", "")
    from_chunk_index = arguments.get("from_chunk_index", 0)
    
    status = await task_manager.get_task_status(task_id, from_chunk_index)
    
    if status is None:
        return {
            "error": "Task not found",
            "task_id": task_id,
        }
    
    return status


async def _handle_task_cancel(
    task_manager: StreamingTaskManager,
    arguments: dict[str, Any]
) -> dict[str, Any]:
    """Handle kiro_task_cancel tool call - cancel a running task."""
    task_id = arguments.get("task_id", "")
    
    cancelled = await task_manager.cancel_task(task_id)
    
    return {
        "success": cancelled,
        "task_id": task_id,
        "message": "Task cancelled" if cancelled else "Task not found or already completed",
    }


async def _handle_task_list(
    task_manager: StreamingTaskManager,
    arguments: dict[str, Any]
) -> dict[str, Any]:
    """Handle kiro_task_list tool call - list active tasks."""
    session_id = arguments.get("session_id")
    include_done = arguments.get("include_done", False)
    
    tasks = await task_manager.list_tasks(session_id, include_done)
    
    return {
        "tasks": [t.to_dict() for t in tasks],
        "count": len(tasks),
    }


async def _handle_pool_stats(
    command_executor: CommandExecutor,
) -> dict[str, Any]:
    """Handle kiro_pool_stats tool call - get process pool statistics."""
    return {
        "pool_stats": command_executor.pool_stats,
    }


async def _handle_session_clear(
    session_manager: SessionManager,
    arguments: dict[str, Any]
) -> dict[str, Any]:
    """Handle kiro_session_clear tool call - clear kiro-cli session file."""
    session_id = arguments.get("session_id")
    session = await session_manager.get_or_create_session(session_id)
    
    # Delete .kiro/session.json in working directory
    working_dir = session.working_directory or "."
    session_file = Path(working_dir) / ".kiro" / "session.json"
    
    if session_file.exists():
        session_file.unlink()
        logger.info(f"Cleared kiro-cli session file: {session_file}")
        return {
            "success": True,
            "message": f"Cleared kiro-cli session in {working_dir}",
            "path": str(session_file),
        }
    else:
        return {
            "success": False,
            "message": "No kiro-cli session file found",
            "path": str(session_file),
        }


async def _handle_session_save(
    session_manager: SessionManager,
    command_executor: CommandExecutor,
    arguments: dict[str, Any]
) -> dict[str, Any]:
    """Handle kiro_session_save tool call - save session using /save command."""
    session_id = arguments.get("session_id")
    save_path = arguments.get("path", "")
    
    if not save_path:
        return {
            "success": False,
            "error": "Path is required",
        }
    
    session = await session_manager.get_or_create_session(session_id)
    
    # Execute /save command
    result = await command_executor.execute_command(
        session,
        f"/save {save_path}"
    )
    
    return {
        **result.to_dict(),
        "session_id": session.id,
        "save_path": save_path,
    }


# Keep the old class for backward compatibility
class KiroCliMCPServer:
    """MCP Server for orchestrating kiro-cli from Kiro IDE."""
    
    def __init__(self, config: ServerConfig | None = None) -> None:
        self.config = config or ConfigManager.get_default()
        self.session_manager = SessionManager(self.config)
        self.command_executor = CommandExecutor(self.config)
        self._setup_logging()
    
    def _setup_logging(self) -> None:
        """Configure logging based on config."""
        logging.basicConfig(
            level=getattr(logging, self.config.log_level),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    
    async def list_tools(self) -> list[dict[str, Any]]:
        """Return list of available tools."""
        return get_all_tools()
    
    async def list_resources(self) -> list[dict[str, Any]]:
        """Return list of available resources."""
        return get_all_resources()
    
    async def read_resource(self, uri: str) -> dict[str, Any]:
        """Read a resource by URI.
        
        Args:
            uri: Resource URI
            
        Returns:
            Resource content
        """
        if uri == "kiro://sessions":
            sessions = await self.session_manager.list_sessions()
            return {
                "sessions": [s.to_info().to_dict() for s in sessions],
                "active_session_id": self.session_manager.active_session_id,
            }
        
        elif uri == "kiro://agents":
            agents = await self.command_executor.list_agents()
            return {
                "agents": [a.to_dict() for a in agents],
            }
        
        elif uri == "kiro://config":
            return self.config.to_dict()
        
        else:
            raise MCPError(
                code=ErrorCode.INVALID_COMMAND,
                message=f"Unknown resource URI: {uri}",
            )
    
    async def handle_tool_call(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any] | AsyncIterator[str]:
        """Handle incoming tool calls.
        
        Args:
            name: Tool name
            arguments: Tool arguments
            
        Returns:
            Tool result or async iterator for streaming
        """
        logger.debug(f"Tool call: {name} with args: {arguments}")
        
        try:
            if name == "kiro_chat":
                return await self._handle_chat(arguments)
            
            elif name == "kiro_session_create":
                return await self._handle_session_create(arguments)
            
            elif name == "kiro_session_list":
                return await self._handle_session_list()
            
            elif name == "kiro_session_switch":
                return await self._handle_session_switch(arguments)
            
            elif name == "kiro_session_end":
                return await self._handle_session_end(arguments)
            
            elif name == "kiro_command":
                return await self._handle_command(arguments)
            
            elif name == "kiro_agents_list":
                return await self._handle_agents_list()
            
            elif name == "kiro_history":
                return await self._handle_history(arguments)
            
            elif name == "kiro_history_clear":
                return await self._handle_history_clear(arguments)
            
            else:
                raise MCPError(
                    code=ErrorCode.INVALID_COMMAND,
                    message=f"Unknown tool: {name}",
                )
        
        except MCPError:
            raise
        except Exception as e:
            logger.exception(f"Error handling tool call {name}")
            raise MCPError(
                code=ErrorCode.EXECUTION_ERROR,
                message=str(e),
            )
    
    async def _handle_chat(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handle kiro_chat tool call."""
        message = arguments.get("message", "")
        session_id = arguments.get("session_id")
        stream = arguments.get("stream", False)
        
        session = await self.session_manager.get_or_create_session(session_id)
        
        if stream:
            # Return streaming response
            async def stream_response() -> AsyncIterator[str]:
                async for chunk in await self.command_executor.execute_chat(
                    session, message, stream=True
                ):
                    yield chunk
            return {"stream": stream_response()}
        else:
            response = await self.command_executor.execute_chat(session, message)
            return response.to_dict()
    
    async def _handle_session_create(
        self, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle kiro_session_create tool call."""
        agent = arguments.get("agent")
        working_directory = arguments.get("working_directory")
        
        session = await self.session_manager.create_session(
            agent=agent,
            working_directory=working_directory,
        )
        
        return {
            "session_id": session.id,
            "message": f"Session {session.id} created successfully",
            "session": session.to_info().to_dict(),
        }
    
    async def _handle_session_list(self) -> dict[str, Any]:
        """Handle kiro_session_list tool call."""
        sessions = await self.session_manager.list_sessions()
        return {
            "sessions": [s.to_info().to_dict() for s in sessions],
            "count": len(sessions),
            "active_session_id": self.session_manager.active_session_id,
        }
    
    async def _handle_session_switch(
        self, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle kiro_session_switch tool call."""
        session_id = arguments.get("session_id", "")
        
        session = await self.session_manager.switch_session(session_id)
        
        return {
            "session_id": session.id,
            "message": f"Switched to session {session.id}",
            "session": session.to_info().to_dict(),
        }
    
    async def _handle_session_end(
        self, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle kiro_session_end tool call."""
        session_id = arguments.get("session_id", "")
        
        await self.session_manager.end_session(session_id)
        
        return {
            "session_id": session_id,
            "message": f"Session {session_id} ended successfully",
        }
    
    async def _handle_command(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handle kiro_command tool call."""
        command = arguments.get("command", "")
        session_id = arguments.get("session_id")
        
        session = await self.session_manager.get_or_create_session(session_id)
        result = await self.command_executor.execute_command(session, command)
        
        return result.to_dict()
    
    async def _handle_agents_list(self) -> dict[str, Any]:
        """Handle kiro_agents_list tool call."""
        agents = await self.command_executor.list_agents()
        return {
            "agents": [a.to_dict() for a in agents],
            "count": len(agents),
        }
    
    async def _handle_history(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handle kiro_history tool call."""
        session_id = arguments.get("session_id")
        limit = arguments.get("limit", 50)
        
        session = await self.session_manager.get_or_create_session(session_id)
        history = session.get_history(limit=limit)
        
        return {
            "session_id": session.id,
            "messages": [h.to_dict() for h in history],
            "count": len(history),
        }
    
    async def _handle_history_clear(
        self, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle kiro_history_clear tool call."""
        session_id = arguments.get("session_id")
        
        session = await self.session_manager.get_or_create_session(session_id)
        session.clear_history()
        
        return {
            "session_id": session.id,
            "message": "History cleared successfully",
        }
