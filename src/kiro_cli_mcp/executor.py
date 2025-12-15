"""Command execution for Kiro CLI MCP Server."""

import asyncio
import logging
import os
import re
import shutil
import signal
import sys
from pathlib import Path
from typing import AsyncIterator, Any

import psutil

# Regex to strip ANSI escape codes (colors, cursor movement, etc.)
ANSI_ESCAPE_PATTERN = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')


def strip_ansi_codes(text: str) -> str:
    """Remove ANSI escape codes from text for cleaner logging."""
    return ANSI_ESCAPE_PATTERN.sub('', text)

from .config import ServerConfig
from .errors import (
    ExecutionError,
    ValidationError,
    ErrorCode,
    TimeoutError as MCPTimeoutError,
)
from .models import CommandResult, AgentInfo, ChatResponse
from .session import Session, register_process, unregister_process
from .process_pool import ProcessPool

logger = logging.getLogger(__name__)

# Check if we're on Unix-like system (for process group support)
IS_UNIX = sys.platform != 'win32'


class CommandExecutor:
    """Executes kiro-cli commands.
    
    Performance optimizations:
    - Uses ProcessPool for process reuse (when available)
    - Falls back to direct process spawning if pool not started
    - Mock mode for testing without kiro-cli
    """

    def __init__(self, config: ServerConfig) -> None:
        self.config = config
        self.kiro_cli_path = config.kiro_cli_path
        self.default_timeout = config.command_timeout
        self._kiro_cli_available: bool | None = None
        self._mock_mode = False
        
        # Process pool for performance
        self._process_pool: ProcessPool | None = None
        self._pool_enabled = config.pool_enabled if hasattr(config, 'pool_enabled') else True
        self._pool_started = False
    
    async def start_pool(self) -> None:
        """Start the process pool for improved performance.
        
        Call this during server startup for best performance.
        If not called, executor will spawn processes directly.
        """
        if not self._pool_enabled:
            logger.info("Process pool disabled by configuration")
            return
        
        if self._pool_started:
            return
        
        self._process_pool = ProcessPool(
            kiro_cli_path=self.kiro_cli_path,
            max_pool_size=getattr(self.config, 'pool_size', 5),
            max_idle_time=getattr(self.config, 'pool_idle_time', 300.0),
            default_model=self.config.default_model,
        )
        await self._process_pool.start()
        self._pool_started = True
        logger.info("🚀 Process pool initialized for improved performance")
    
    async def stop_pool(self) -> None:
        """Stop the process pool."""
        if self._process_pool:
            await self._process_pool.stop()
            self._process_pool = None
            self._pool_started = False
    
    @property
    def pool_stats(self) -> dict[str, Any]:
        """Get process pool statistics."""
        if self._process_pool:
            return self._process_pool.stats
        return {"enabled": False}
    
    def _validate_message(self, message: str) -> None:
        """Validate chat message.
        
        Args:
            message: The message to validate
            
        Raises:
            ValidationError: If message is empty or whitespace only
        """
        if not message or not message.strip():
            raise ValidationError(
                code=ErrorCode.INVALID_MESSAGE,
                details={"message": message},
            )
    
    def _validate_command(self, command: str) -> None:
        """Validate command format.

        Args:
            command: The command to validate

        Raises:
            ValidationError: If command is invalid
        """
        if not command or not command.strip():
            raise ValidationError(
                code=ErrorCode.INVALID_COMMAND,
                details={"command": command},
            )

    async def _terminate_process_tree(self, process: asyncio.subprocess.Process, timeout: float = 5.0) -> None:
        """Terminate a process and ALL its descendants (full process tree cleanup).

        This is critical for preventing orphaned processes when kiro-cli spawns
        MCP servers (like augment-context/auggie) or other child processes.

        Strategy using psutil for reliable recursive kill:
        1. Get all descendant processes (children, grandchildren, etc.)
        2. Send SIGTERM to all descendants (graceful shutdown)
        3. Wait for timeout
        4. Send SIGKILL to remaining processes (forceful kill)

        Args:
            process: The process to terminate
            timeout: Graceful shutdown timeout in seconds
        """
        if process.returncode is not None:
            return

        pid = process.pid

        try:
            parent = psutil.Process(pid)
        except psutil.NoSuchProcess:
            logger.debug(f"Process {pid} already gone")
            return

        try:
            children = parent.children(recursive=True)
            all_procs = children + [parent]
            
            logger.info(f"🧹 Terminating process tree (pid={pid}, {len(children)} descendants)")
            for child in children:
                logger.debug(f"   Found descendant: pid={child.pid}, name={child.name()}")

            for proc in all_procs:
                try:
                    proc.terminate()
                    logger.debug(f"   Sent SIGTERM to pid={proc.pid}")
                except psutil.NoSuchProcess:
                    pass

            gone, alive = psutil.wait_procs(all_procs, timeout=timeout)
            
            if alive:
                logger.warning(f"⏱️  {len(alive)} processes did not terminate gracefully, force killing...")
                for proc in alive:
                    try:
                        proc.kill()
                        logger.debug(f"   Sent SIGKILL to pid={proc.pid}")
                    except psutil.NoSuchProcess:
                        pass
                
                psutil.wait_procs(alive, timeout=2.0)
            
            logger.info(f"✅ Process tree terminated: {len(gone)} graceful, {len(alive)} forced")

        except psutil.NoSuchProcess:
            logger.debug(f"Process {pid} already gone during cleanup")
        except Exception as e:
            logger.error(f"Error terminating process tree with psutil: {e}")
            try:
                if IS_UNIX:
                    pgid = os.getpgid(pid)
                    os.killpg(pgid, signal.SIGKILL)
                else:
                    process.kill()
                await process.wait()
            except Exception:
                pass
    
    async def _check_kiro_cli_available(self) -> bool:
        """Check if kiro-cli is available.

        Returns:
            True if kiro-cli is available, False otherwise
        """
        if self._kiro_cli_available is not None:
            logger.debug(f"Using cached kiro-cli availability: {self._kiro_cli_available}")
            return self._kiro_cli_available

        try:
            logger.info("🔍 Checking kiro-cli availability...")
            kiro_cli = self._find_kiro_cli()
            logger.info(f"   Testing: {kiro_cli}")

            # Try to run kiro-cli --version
            process = await asyncio.create_subprocess_exec(
                kiro_cli,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=5.0,
            )

            self._kiro_cli_available = process.returncode == 0
            if self._kiro_cli_available:
                version = stdout.decode().strip()
                logger.info(f"✅ kiro-cli is available")
                logger.info(f"   Path: {kiro_cli}")
                logger.info(f"   Version: {version}")
            else:
                error = stderr.decode().strip()
                logger.warning(f"⚠️  kiro-cli not working properly")
                logger.warning(f"   Error: {error[:200]}{'...' if len(error) > 200 else ''}")

            return self._kiro_cli_available

        except (FileNotFoundError, asyncio.TimeoutError) as e:
            logger.warning(f"❌ kiro-cli not available: {e}")
            logger.warning(f"   Enabling mock mode")
            self._kiro_cli_available = False
            self._mock_mode = True
            return False

    def _find_kiro_cli(self) -> str:
        """Find kiro-cli executable.

        Returns:
            Path to kiro-cli executable (preserves symlinks)

        Raises:
            ExecutionError: If kiro-cli not found
        """
        # Check configured path first
        if self.kiro_cli_path != "kiro-cli":
            path_obj = Path(self.kiro_cli_path)
            if path_obj.exists() and path_obj.is_file():
                # Check if executable
                if os.access(self.kiro_cli_path, os.X_OK):
                    # Log resolved path for debugging, but return original
                    if path_obj.is_symlink():
                        resolved = path_obj.resolve()
                        logger.debug(f"kiro-cli symlink: {self.kiro_cli_path} -> {resolved}")
                    logger.info(f"kiro-cli found at: {self.kiro_cli_path}")
                    return self.kiro_cli_path
            else:
                # If explicit path was configured but doesn't exist, don't fallback
                # This allows tests to force mock mode by setting a non-existent path
                logger.warning(f"Configured kiro-cli path does not exist: {self.kiro_cli_path}")
                return self.kiro_cli_path

        # Try to find in PATH
        path = shutil.which("kiro-cli")
        if path:
            # Log resolved path for debugging, but return original
            path_obj = Path(path)
            if path_obj.is_symlink():
                resolved = path_obj.resolve()
                logger.debug(f"kiro-cli symlink: {path} -> {resolved}")
            logger.info(f"kiro-cli found at: {path}")
            return path

        # Check common locations
        common_paths = [
            "/usr/local/bin/kiro-cli",
            "/usr/bin/kiro-cli",
            str(Path.home() / ".local" / "bin" / "kiro-cli"),
        ]

        for path_str in common_paths:
            path_obj = Path(path_str)
            if path_obj.exists() and path_obj.is_file():
                # Check if executable
                if os.access(path_str, os.X_OK):
                    # Log resolved path for debugging, but return original
                    if path_obj.is_symlink():
                        resolved = path_obj.resolve()
                        logger.debug(f"kiro-cli symlink: {path_str} -> {resolved}")
                    logger.info(f"kiro-cli found at: {path_str}")
                    return path_str

        # Default to configured path (may not exist)
        return self.kiro_cli_path

    async def _execute_mock_chat(
        self,
        session: Session,
        message: str,
    ) -> ChatResponse:
        """Execute chat in mock mode (for testing when kiro-cli not available).

        Args:
            session: The session to use
            message: The message to send

        Returns:
            Mock ChatResponse
        """
        logger.debug(f"Mock chat execution: {message[:50]}...")

        # Simulate processing delay
        await asyncio.sleep(0.1)

        # Generate mock response
        mock_response = f"[MOCK MODE] Received your message: '{message[:100]}...'\n\n"
        mock_response += "This is a mock response because kiro-cli is not available.\n"
        mock_response += f"Session: {session.id}\n"
        if session.agent:
            mock_response += f"Agent: {session.agent}\n"

        # Add to history
        session.add_message("assistant", mock_response)

        return ChatResponse(
            content=mock_response,
            session_id=session.id,
            is_complete=True,
        )
    
    async def execute_chat(
        self,
        session: Session,
        message: str,
        stream: bool = False,
    ) -> ChatResponse | AsyncIterator[str]:
        """Send chat message and get response.

        Args:
            session: The session to use
            message: The message to send
            stream: Whether to stream the response

        Returns:
            ChatResponse or async iterator of chunks if streaming

        Raises:
            ValidationError: If message is invalid
            ExecutionError: If execution fails
            TimeoutError: If execution times out
        """
        self._validate_message(message)

        # Add user message to history
        session.add_message("user", message)

        # Check if kiro-cli is available
        is_available = await self._check_kiro_cli_available()

        if not is_available or self._mock_mode:
            # Use mock mode
            return await self._execute_mock_chat(session, message)

        if stream:
            return self._execute_chat_streaming(session, message)
        elif self._pool_started and self._process_pool:
            # Use pooled execution for better performance
            return await self._execute_chat_pooled(session, message)
        else:
            return await self._execute_chat_sync(session, message)
    
    async def _execute_chat_pooled(
        self,
        session: Session,
        message: str,
    ) -> ChatResponse:
        """Execute chat using process pool for better performance."""
        if not self._process_pool:
            # Fall back to sync execution
            return await self._execute_chat_sync(session, message)
        
        logger.info("🔄 Using pooled process execution")
        
        try:
            stdout, stderr, return_code = await self._process_pool.execute_message(
                message=message,
                working_directory=session.working_directory,
                agent=session.agent or self.config.default_agent,
                model=self.config.default_model,
                timeout=self.default_timeout if self.default_timeout > 0 else None,
            )
            
            if return_code != 0:
                error_msg = stderr or "Unknown error"
                logger.error(f"❌ Pooled execution failed with code {return_code}")
                raise ExecutionError(
                    code=ErrorCode.COMMAND_FAILED,
                    message=error_msg,
                    details={"exit_code": return_code},
                )
            
            content = stdout.strip()
            logger.info(f"✅ Pooled chat completed ({len(content)} chars)")
            
            if self.config.log_response:
                clean_content = strip_ansi_codes(content)
                logger.info(f"📝 CLI Response:\n{'='*60}\n{clean_content}\n{'='*60}")
            
            session.add_message("assistant", content)
            
            return ChatResponse(
                content=content,
                session_id=session.id,
                is_complete=True,
            )
            
        except asyncio.TimeoutError:
            raise MCPTimeoutError(
                code=ErrorCode.COMMAND_TIMEOUT,
                details={"timeout": self.default_timeout},
            )
    
    async def _execute_chat_sync(
        self,
        session: Session,
        message: str,
    ) -> ChatResponse:
        """Execute chat synchronously (fallback when pool not available)."""
        kiro_cli = self._find_kiro_cli()

        # Determine working directory (fallback to current directory if None)
        cwd = session.working_directory or os.getcwd()

        # Validate working directory exists
        if not os.path.isdir(cwd):
            logger.warning(f"Working directory does not exist: {cwd}, falling back to current directory")
            cwd = os.getcwd()

        logger.debug(f"Executing kiro-cli in directory: {cwd}")

        # Build command
        cmd = [kiro_cli, "chat"]
        
        # Use session agent or fallback to default agent from config
        agent = session.agent or self.config.default_agent
        
        # Only add --model if using kiro_default agent
        if agent == "kiro_default":
            cmd.extend(["--model", self.config.default_model])
        
        if agent:
            cmd.extend(["--agent", agent])
        
        # ✅ Enable session persistence via --resume
        # Kiro-CLI will save/load conversation history to/from
        # .kiro/session.json in the working directory
        cmd.append("--resume")
        
        # Run in non-interactive mode with auto-approve tools (required for MCP)
        cmd.extend(["--no-interactive", "--trust-all-tools"])

        process = None
        try:
            logger.info(f"🚀 Executing kiro-cli chat")
            logger.info(f"   Command: {' '.join(cmd)}")
            if agent == "kiro_default":
                logger.info(f"   Model: {self.config.default_model}")
            logger.info(f"   Agent: {agent or 'None'}")
            logger.info(f"   Working directory: {cwd}")
            logger.info(f"   Message: {message[:100]}{'...' if len(message) > 100 else ''}")

            # Create process with process group for proper cleanup
            # This ensures all child processes (MCP servers spawned by kiro-cli)
            # are killed when we terminate the parent
            if IS_UNIX:
                # On Unix: create new process group
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    preexec_fn=os.setpgrp,  # Create new process group
                )
            else:
                # On Windows: use CREATE_NEW_PROCESS_GROUP flag
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    creationflags=0x00000200 if sys.platform == 'win32' else 0,  # CREATE_NEW_PROCESS_GROUP
                )

            register_process(process)
            logger.info(f"   Process started: pid={process.pid}")
            if IS_UNIX:
                logger.debug(f"   Process group: {os.getpgid(process.pid)}")

            # Send message and get response
            timeout = self.default_timeout if self.default_timeout > 0 else None
            logger.debug(f"Waiting for response (timeout={timeout or 'unlimited'})...")
            
            # Use incremental reading to show progress and prevent client timeout
            if process.stdin:
                process.stdin.write(message.encode())
                await process.stdin.drain()
                process.stdin.close()
            
            stdout_chunks = []
            stderr_chunks = []
            
            # Read stdout with progress logging
            async def read_with_progress():
                last_log = asyncio.get_event_loop().time()
                while True:
                    if process.stdout:
                        chunk = await process.stdout.read(4096)
                        if not chunk:
                            break
                        stdout_chunks.append(chunk)
                        
                        # Log progress every 10 seconds to keep connection alive
                        now = asyncio.get_event_loop().time()
                        if now - last_log > 10:
                            logger.info(f"   ⏳ Still processing... ({len(b''.join(stdout_chunks))} bytes received)")
                            last_log = now
                    else:
                        break
            
            # Read stderr
            async def read_stderr():
                while True:
                    if process.stderr:
                        chunk = await process.stderr.read(4096)
                        if not chunk:
                            break
                        stderr_chunks.append(chunk)
                    else:
                        break
            
            if timeout:
                await asyncio.wait_for(
                    asyncio.gather(read_with_progress(), read_stderr()),
                    timeout=timeout,
                )
            else:
                await asyncio.gather(read_with_progress(), read_stderr())
                
            await process.wait()
            # Ensure ALL descendants (MCP subprocesses) are terminated
            await self._terminate_process_tree(process)
            unregister_process(process)
            stdout = b''.join(stdout_chunks)
            stderr = b''.join(stderr_chunks)

            logger.info(f"   Process completed: returncode={process.returncode}")

            if stderr:
                stderr_text = stderr.decode().strip()
                if stderr_text:
                    logger.debug(f"   Stderr: {stderr_text[:200]}{'...' if len(stderr_text) > 200 else ''}")

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.error(f"❌ Command failed with exit code {process.returncode}")
                logger.error(f"   Error: {error_msg[:200]}{'...' if len(error_msg) > 200 else ''}")
                raise ExecutionError(
                    code=ErrorCode.COMMAND_FAILED,
                    message=error_msg,
                    details={"exit_code": process.returncode},
                )

            content = stdout.decode().strip()
            logger.info(f"✅ Chat completed successfully")
            logger.info(f"   Response length: {len(content)} chars")
            
            # Log full response if enabled (for debugging)
            if self.config.log_response:
                clean_content = strip_ansi_codes(content)
                logger.info(f"📝 CLI Response:\n{'='*60}\n{clean_content}\n{'='*60}")
            else:
                logger.debug(f"   Response preview: {content[:200]}{'...' if len(content) > 200 else ''}")

            # Add assistant response to history
            session.add_message("assistant", content)

            return ChatResponse(
                content=content,
                session_id=session.id,
                is_complete=True,
            )

        except asyncio.TimeoutError:
            # Kill the process if it's still running
            if process and process.returncode is None:
                logger.error(f"⏱️  Timeout after {self.default_timeout}s - killing process {process.pid}")
                try:
                    await self._terminate_process_tree(process)
                    unregister_process(process)
                except Exception as e:
                    logger.error(f"Failed to kill process: {e}")

            raise MCPTimeoutError(
                code=ErrorCode.COMMAND_TIMEOUT,
                details={"timeout": self.default_timeout},
            )
        except FileNotFoundError as e:
            logger.error(f"FileNotFoundError when executing kiro-cli: {e}")
            logger.error(f"Command: {cmd}, cwd: {cwd}")
            if process and process.returncode is None:
                await self._terminate_process_tree(process)
            if process:
                unregister_process(process)
            raise ExecutionError(
                code=ErrorCode.KIRO_CLI_NOT_FOUND,
                details={"path": kiro_cli, "error": str(e)},
            )
        except Exception as e:
            logger.error(f"Unexpected error executing kiro-cli: {type(e).__name__}: {e}")
            logger.error(f"Command: {cmd}, cwd: {cwd}")
            if process and process.returncode is None:
                await self._terminate_process_tree(process)
            if process:
                unregister_process(process)
            raise
    
    async def _execute_chat_streaming(
        self,
        session: Session,
        message: str,
    ) -> AsyncIterator[str]:
        """Execute chat with streaming response."""
        kiro_cli = self._find_kiro_cli()

        # Determine and validate working directory
        cwd = session.working_directory or os.getcwd()
        if not os.path.isdir(cwd):
            logger.warning(f"Working directory does not exist: {cwd}, falling back to current directory")
            cwd = os.getcwd()

        cmd = [kiro_cli, "chat"]
        
        # Use session agent or fallback to default agent from config
        agent = session.agent or self.config.default_agent
        
        # Only add --model if using kiro_default agent
        if agent == "kiro_default":
            cmd.extend(["--model", self.config.default_model])
        
        if agent:
            cmd.extend(["--agent", agent])

        # ✅ Enable session persistence via --resume
        cmd.append("--resume")

        # Run in non-interactive mode with auto-approve tools (required for MCP)
        cmd.extend(["--no-interactive", "--trust-all-tools"])

        try:
            logger.info(f"🚀 Executing kiro-cli chat (streaming)")
            if agent == "kiro_default":
                logger.info(f"   Model: {self.config.default_model}")
            logger.info(f"   Agent: {agent or 'None'}")
            logger.info(f"   Working directory: {cwd}")

            # Create process with process group for proper cleanup
            if IS_UNIX:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    preexec_fn=os.setpgrp,
                )
            else:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    creationflags=0x00000200 if sys.platform == 'win32' else 0,
                )

            register_process(process)
            
            # Send message
            if process.stdin:
                process.stdin.write(message.encode())
                await process.stdin.drain()
                process.stdin.close()
            
            full_response = []
            
            # Stream stdout
            timeout = self.default_timeout if self.default_timeout > 0 else None
            if process.stdout:
                while True:
                    try:
                        if timeout:
                            chunk = await asyncio.wait_for(
                                process.stdout.read(1024),
                                timeout=timeout,
                            )
                        else:
                            chunk = await process.stdout.read(1024)
                        if not chunk:
                            break
                        decoded = chunk.decode()
                        full_response.append(decoded)
                        yield decoded
                    except asyncio.TimeoutError:
                        break
            
            await process.wait()
            unregister_process(process)
            
            # Log full response if enabled (for debugging)
            complete_response = "".join(full_response)
            if self.config.log_response:
                clean_response = strip_ansi_codes(complete_response)
                logger.info(f"📝 CLI Response (streaming):\n{'='*60}\n{clean_response}\n{'='*60}")
            
            # Add complete response to history
            session.add_message("assistant", complete_response)
            
        except FileNotFoundError:
            if process:
                unregister_process(process)
            raise ExecutionError(
                code=ErrorCode.KIRO_CLI_NOT_FOUND,
                details={"path": kiro_cli},
            )
    
    async def execute_command(
        self,
        session: Session,
        command: str,
        timeout: float | None = None,
    ) -> CommandResult:
        """Execute a kiro-cli command.
        
        Args:
            session: The session to use
            command: The command to execute (e.g., '/mcp', '/help')
            timeout: Optional timeout override
            
        Returns:
            CommandResult with output
            
        Raises:
            ValidationError: If command is invalid
            ExecutionError: If execution fails
            TimeoutError: If execution times out
        """
        self._validate_command(command)

        kiro_cli = self._find_kiro_cli()
        effective_timeout = timeout or self.default_timeout

        # Determine and validate working directory
        cwd = session.working_directory or os.getcwd()
        if not os.path.isdir(cwd):
            logger.warning(f"Working directory does not exist: {cwd}, falling back to current directory")
            cwd = os.getcwd()

        cmd = [kiro_cli, "chat"]
        
        # Use session agent or fallback to default agent from config
        agent = session.agent or self.config.default_agent
        
        # Only add --model if using kiro_default agent
        if agent == "kiro_default":
            cmd.extend(["--model", self.config.default_model])
        
        if agent:
            cmd.extend(["--agent", agent])

        # ✅ Enable session persistence via --resume
        cmd.append("--resume")

        # Run in non-interactive mode with auto-approve tools (required for MCP)
        cmd.extend(["--no-interactive", "--trust-all-tools"])

        process = None
        try:
            logger.info(f"🚀 Executing kiro-cli command")
            logger.info(f"   Command: {' '.join(cmd)}")
            logger.info(f"   Model: {self.config.default_model}")
            logger.info(f"   Agent: {agent or 'None'}")
            logger.info(f"   Working directory: {cwd}")
            logger.info(f"   Input: {command[:100]}{'...' if len(command) > 100 else ''}")

            # Create process with process group for proper cleanup
            if IS_UNIX:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    preexec_fn=os.setpgrp,
                )
            else:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    creationflags=0x00000200 if sys.platform == 'win32' else 0,
                )

            register_process(process)
            logger.info(f"   Process started: pid={process.pid}")

            # Send command
            timeout = effective_timeout if effective_timeout > 0 else None
            logger.debug(f"Waiting for response (timeout={timeout or 'unlimited'})...")
            if timeout:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(input=command.encode()),
                    timeout=timeout,
                )
            else:
                stdout, stderr = await process.communicate(input=command.encode())

            unregister_process(process)
            logger.info(f"   Process completed: returncode={process.returncode}")

            output = stdout.decode().strip()
            error = stderr.decode().strip() if stderr else None

            if process.returncode == 0:
                logger.info(f"✅ Command completed successfully")
                logger.info(f"   Output length: {len(output)} chars")
            else:
                logger.warning(f"⚠️  Command failed with exit code {process.returncode}")
                if error:
                    logger.warning(f"   Error: {error[:200]}{'...' if len(error) > 200 else ''}")

            return CommandResult(
                success=process.returncode == 0,
                output=output,
                error=error,
                exit_code=process.returncode or 0,
            )

        except asyncio.TimeoutError:
            # Kill the process if it's still running
            if process and process.returncode is None:
                logger.error(f"⏱️  Timeout after {effective_timeout}s - killing process {process.pid}")
                try:
                    await self._terminate_process_tree(process)
                    unregister_process(process)
                except Exception as e:
                    logger.error(f"Failed to kill process: {e}")

            raise MCPTimeoutError(
                code=ErrorCode.COMMAND_TIMEOUT,
                details={"timeout": effective_timeout, "command": command},
            )
        except FileNotFoundError:
            if process:
                unregister_process(process)
            raise ExecutionError(
                code=ErrorCode.KIRO_CLI_NOT_FOUND,
                details={"path": kiro_cli},
            )
    
    async def list_agents(self) -> list[AgentInfo]:
        """List available custom agents.

        Returns:
            List of AgentInfo
        """
        # Check if kiro-cli is available
        is_available = await self._check_kiro_cli_available()

        if not is_available or self._mock_mode:
            # Return mock agents
            return [
                AgentInfo(
                    name="default",
                    description="Default AI assistant (mock)",
                    config_path=None,
                ),
                AgentInfo(
                    name="code-reviewer",
                    description="Code review specialist (mock)",
                    config_path=None,
                ),
            ]

        # Try to get agents from kiro-cli
        try:
            kiro_cli = self._find_kiro_cli()

            # Try to run kiro-cli agents list (if such command exists)
            process = await asyncio.create_subprocess_exec(
                kiro_cli,
                "agents",
                "list",
                "--json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=10.0,
            )

            if process.returncode == 0:
                import json
                agents_data = json.loads(stdout.decode())
                return [AgentInfo.from_dict(a) for a in agents_data]
            else:
                logger.warning(f"Failed to list agents: {stderr.decode()}")
                return []

        except Exception as e:
            logger.warning(f"Error listing agents: {e}")
            return []
    
    async def get_agent(self, name: str) -> AgentInfo | None:
        """Get agent by name.
        
        Args:
            name: Agent name
            
        Returns:
            AgentInfo or None if not found
        """
        agents = await self.list_agents()
        for agent in agents:
            if agent.name == name:
                return agent
        return None
