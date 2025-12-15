"""Session management for Kiro CLI MCP Server."""

import asyncio
import atexit
import logging
import os
import signal
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import psutil

from .config import ServerConfig
from .errors import SessionError, ErrorCode, ConcurrencyError
from .models import SessionInfo, HistoryMessage

logger = logging.getLogger(__name__)

# Check if we're on Unix-like system (for process group support)
IS_UNIX = sys.platform != 'win32'

# MCP tool patterns for orphan detection
MCP_TOOL_PATTERNS = [
    'auggie --mcp',
    'node.*--mcp',
    'python.*--mcp',
    '--mcp',  # Generic MCP flag
]

# Global registry to track all running processes for cleanup
_active_processes: set[asyncio.subprocess.Process] = set()
_session_managers: list["SessionManager"] = []
_cleanup_tasks: list[asyncio.Task] = []


def _is_descendant_of(child_pid: int, ancestor_pid: int) -> bool:
    """Check if child_pid is a descendant of ancestor_pid."""
    try:
        child = psutil.Process(child_pid)
        for parent in child.parents():
            if parent.pid == ancestor_pid:
                return True
        return False
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def _kill_orphaned_mcp_processes_shell(verbose: bool = False) -> int:
    """Shell-based orphan cleanup as additional safety layer.
    
    Args:
        verbose: If True, log even when no orphans found
        
    Returns:
        Number of orphaned processes killed
    """
    if not IS_UNIX:
        return 0  # Only run on Unix systems
    
    if verbose:
        logger.info("🔍 Shell cleanup: Checking for orphaned MCP processes...")
    
    try:
        import subprocess
        
        # Find orphaned MCP processes using shell command
        cmd = "ps -eo pid,ppid,command | awk '$2==1 && /auggie --mcp|node.*--mcp/ {print $1}'"
        result = subprocess.run(
            cmd, 
            shell=True, 
            capture_output=True, 
            text=True, 
            timeout=10.0
        )
        
        if result.returncode == 0 and result.stdout.strip():
            pids = result.stdout.strip().split('\n')
            killed_count = 0
            
            for pid_str in pids:
                try:
                    pid = int(pid_str.strip())
                    os.kill(pid, signal.SIGKILL)
                    killed_count += 1
                    logger.info(f"🧹 Shell cleanup killed orphaned MCP process: {pid}")
                except (ValueError, ProcessLookupError, PermissionError):
                    pass
            
            if killed_count > 0:
                logger.info(f"✅ Shell cleanup killed {killed_count} orphaned MCP processes")
            
            return killed_count
        
        return 0  # No orphans found
                
    except Exception as e:
        logger.debug(f"Shell-based orphan cleanup failed: {e}")
        return 0


def _cleanup_all_processes():
    """Enhanced cleanup for all processes including orphaned MCP subprocesses.

    This function ensures all kiro-cli processes and their descendants
    (including MCP servers like auggie) are properly terminated.
    """
    logger.info("🧹 Enhanced cleanup: discovering all descendant processes...")

    # Cancel all cleanup tasks
    for task in _cleanup_tasks:
        try:
            task.cancel()
        except Exception:
            pass
    _cleanup_tasks.clear()

    # Cleanup all session managers
    for manager in _session_managers:
        try:
            manager._sync_cleanup_all_sessions()
        except Exception as e:
            logger.warning(f"   Failed to cleanup session manager: {e}")
    _session_managers.clear()

    # Step 1: Terminate registered processes with their full process trees
    for proc in list(_active_processes):
        try:
            if proc.returncode is None:
                pid = proc.pid
                logger.info(f"   Terminating registered process {pid}")
                
                # Use psutil to kill entire process tree
                try:
                    parent = psutil.Process(pid)
                    children = parent.children(recursive=True)
                    all_procs = children + [parent]
                    
                    # Graceful termination
                    for p in all_procs:
                        try:
                            p.terminate()
                        except psutil.NoSuchProcess:
                            pass
                    
                    # Wait and force kill if needed
                    gone, alive = psutil.wait_procs(all_procs, timeout=2.0)
                    for p in alive:
                        try:
                            p.kill()
                        except psutil.NoSuchProcess:
                            pass
                            
                except psutil.NoSuchProcess:
                    pass
                except Exception as e:
                    logger.warning(f"   psutil cleanup failed for {pid}: {e}")
                    # Fallback to original method
                    if IS_UNIX:
                        try:
                            pgid = os.getpgid(pid)
                            os.killpg(pgid, signal.SIGKILL)
                        except (ProcessLookupError, PermissionError):
                            proc.kill()
                    else:
                        proc.kill()
        except Exception as e:
            logger.warning(f"   Failed to terminate registered process: {e}")

    # Step 2: CRITICAL - Find and kill orphaned MCP processes
    try:
        current_pid = os.getpid()
        logger.info("🔍 Scanning for orphaned MCP processes...")
        
        orphaned_count = 0
        for proc in psutil.process_iter(['pid', 'ppid', 'cmdline']):
            try:
                cmdline = ' '.join(proc.info['cmdline'] or [])
                
                # Check if this is an MCP tool process
                is_mcp_tool = any(pattern in cmdline for pattern in MCP_TOOL_PATTERNS)
                
                if is_mcp_tool:
                    pid = proc.info['pid']
                    ppid = proc.info['ppid']
                    
                    # Kill if orphaned (ppid=1) or descendant of current process
                    if ppid == 1 or _is_descendant_of(pid, current_pid):
                        logger.info(f"🧹 Killing orphaned MCP process: {pid} {cmdline[:100]}")
                        try:
                            proc.terminate()
                            orphaned_count += 1
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                            
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
                
        if orphaned_count > 0:
            logger.info(f"✅ Cleaned up {orphaned_count} orphaned MCP processes")
            
    except Exception as e:
        logger.error(f"Error during orphan cleanup: {e}")

    # Final safety layer: shell-based cleanup
    _kill_orphaned_mcp_processes_shell()

    _active_processes.clear()
    logger.info("✅ Enhanced cleanup complete")


def _register_session_manager(manager: "SessionManager") -> None:
    """Register a session manager for global cleanup."""
    if manager not in _session_managers:
        _session_managers.append(manager)


def _unregister_session_manager(manager: "SessionManager") -> None:
    """Unregister a session manager."""
    if manager in _session_managers:
        _session_managers.remove(manager)


# Register cleanup on exit
atexit.register(_cleanup_all_processes)


def register_process(proc: asyncio.subprocess.Process) -> None:
    """Register a process for tracking."""
    _active_processes.add(proc)
    logger.debug(f"Registered process {proc.pid} (total: {len(_active_processes)})")


def unregister_process(proc: asyncio.subprocess.Process) -> None:
    """Unregister a completed process."""
    _active_processes.discard(proc)
    logger.debug(f"Unregistered process {proc.pid} (total: {len(_active_processes)})")


@dataclass
class Session:
    """Represents a kiro-cli session."""
    
    id: str
    created_at: datetime
    last_active: datetime
    agent: str | None = None
    working_directory: str | None = None
    process: Any | None = None  # asyncio.subprocess.Process
    history: list[HistoryMessage] = field(default_factory=list)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    
    def update_activity(self) -> None:
        """Update the last_active timestamp."""
        self.last_active = datetime.now()
    
    def add_message(self, role: str, content: str) -> None:
        """Add a message to conversation history."""
        self.history.append(HistoryMessage(role=role, content=content))
        self.update_activity()
    
    def get_history(self, limit: int | None = None) -> list[HistoryMessage]:
        """Get conversation history, optionally limited."""
        if limit is None:
            return list(self.history)
        return list(self.history[-limit:])
    
    def clear_history(self) -> None:
        """Clear conversation history."""
        self.history.clear()
        self.update_activity()
    
    def to_info(self) -> SessionInfo:
        """Convert to SessionInfo for external representation."""
        return SessionInfo(
            id=self.id,
            agent=self.agent,
            working_directory=self.working_directory or "",
            created_at=self.created_at.isoformat(),
            last_active=self.last_active.isoformat(),
            is_active=self.process is not None,
        )
    
    async def acquire_lock(self, timeout: float = 30.0) -> bool:
        """Acquire session lock with timeout."""
        try:
            await asyncio.wait_for(self._lock.acquire(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
    
    def release_lock(self) -> None:
        """Release session lock."""
        if self._lock.locked():
            self._lock.release()


class SessionManager:
    """Manages kiro-cli sessions."""
    
    def __init__(self, config: ServerConfig) -> None:
        self.config = config
        self.sessions: dict[str, Session] = {}
        self.active_session_id: str | None = None
        self._lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task | None = None
        self._orphan_monitor_task: asyncio.Task | None = None
        self._shell_cleanup_task: asyncio.Task | None = None
        self._heartbeat_times: dict[str, datetime] = {}
        self._shutdown = False
        
        # Register for global cleanup
        _register_session_manager(self)
    
    async def start_background_cleanup(self, interval: float = 30.0) -> None:
        """Start background task to cleanup inactive sessions.
        
        Args:
            interval: Seconds between cleanup checks (default: 30)
        """
        if self._cleanup_task is not None:
            return
        
        async def cleanup_loop():
            while not self._shutdown:
                try:
                    await asyncio.sleep(interval)
                    cleaned = await self.cleanup_inactive_sessions()
                    if cleaned > 0:
                        logger.info(f"🧹 Auto-cleaned {cleaned} inactive sessions")
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.warning(f"Cleanup task error: {e}")
        
        self._cleanup_task = asyncio.create_task(cleanup_loop())
        _cleanup_tasks.append(self._cleanup_task)
        
        # Start orphan monitoring task
        async def orphan_monitor_loop():
            while not self._shutdown:
                try:
                    await asyncio.sleep(300)  # Check every 5 minutes (less aggressive)
                    await self._monitor_orphaned_processes()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.warning(f"Orphan monitor error: {e}")
        
        self._orphan_monitor_task = asyncio.create_task(orphan_monitor_loop())
        _cleanup_tasks.append(self._orphan_monitor_task)
        
        # Start shell cleanup task (runs every 1 second)
        async def shell_cleanup_loop():
            logger.info("🚀 Shell cleanup task started - checking every 1 second")
            check_count = 0
            total_killed = 0
            while not self._shutdown:
                try:
                    await asyncio.sleep(1)  # Check every second
                    killed = _kill_orphaned_mcp_processes_shell(verbose=False)
                    total_killed += killed
                    check_count += 1
                    
                    # Log status every 60 seconds
                    if check_count % 60 == 0:
                        logger.info(f"🔄 Shell cleanup: {check_count} checks, {total_killed} total killed")
                except asyncio.CancelledError:
                    logger.info(f"🛑 Shell cleanup task cancelled after {check_count} checks, {total_killed} killed")
                    break
                except Exception as e:
                    logger.warning(f"Shell cleanup task error: {e}")
        
        self._shell_cleanup_task = asyncio.create_task(shell_cleanup_loop())
        _cleanup_tasks.append(self._shell_cleanup_task)
        logger.info("✅ Started background tasks: session cleanup, orphan monitoring, shell cleanup (1s interval)")
    
    async def stop_background_cleanup(self) -> None:
        """Stop the background cleanup and orphan monitoring tasks."""
        self._shutdown = True
        
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            if self._cleanup_task in _cleanup_tasks:
                _cleanup_tasks.remove(self._cleanup_task)
            self._cleanup_task = None
            
        if self._orphan_monitor_task is not None:
            self._orphan_monitor_task.cancel()
            try:
                await self._orphan_monitor_task
            except asyncio.CancelledError:
                pass
            if self._orphan_monitor_task in _cleanup_tasks:
                _cleanup_tasks.remove(self._orphan_monitor_task)
            self._orphan_monitor_task = None
            
        if self._shell_cleanup_task is not None:
            self._shell_cleanup_task.cancel()
            try:
                await self._shell_cleanup_task
            except asyncio.CancelledError:
                pass
            if self._shell_cleanup_task in _cleanup_tasks:
                _cleanup_tasks.remove(self._shell_cleanup_task)
            self._shell_cleanup_task = None
    
    def heartbeat(self, session_id: str) -> None:
        """Update heartbeat for a session (call this on each tool call).
        
        Args:
            session_id: The session to update
        """
        self._heartbeat_times[session_id] = datetime.now()
        if session_id in self.sessions:
            self.sessions[session_id].update_activity()
    
    def _sync_cleanup_all_sessions(self) -> None:
        """Synchronous cleanup of all sessions (for atexit handler)."""
        self._shutdown = True
        for session_id, session in list(self.sessions.items()):
            if session.process is not None:
                try:
                    if session.process.returncode is None:
                        session.process.terminate()
                except Exception:
                    pass
        self.sessions.clear()
        self._heartbeat_times.clear()
        _unregister_session_manager(self)
    
    async def cleanup_all_sessions(self) -> int:
        """Cleanup all sessions (async version).
        
        Returns:
            Number of sessions cleaned up
        """
        await self.stop_background_cleanup()
        
        async with self._lock:
            count = len(self.sessions)
            for session_id, session in list(self.sessions.items()):
                if session.process is not None:
                    try:
                        session.process.terminate()
                        await asyncio.wait_for(session.process.wait(), timeout=2.0)
                    except Exception:
                        try:
                            session.process.kill()
                        except Exception:
                            pass
            self.sessions.clear()
            self._heartbeat_times.clear()
            self.active_session_id = None
            
        _unregister_session_manager(self)
        return count
    
    async def _monitor_orphaned_processes(self) -> None:
        """Monitor and clean up orphaned MCP processes."""
        try:
            # Early exit: skip scan if no active sessions
            if not self.sessions:
                logger.debug("No active sessions, skipping orphan scan")
                return
                
            orphaned_count = 0
            current_pid = os.getpid()
            
            # Process name filter for performance - only check potential MCP processes
            mcp_process_names = {'node', 'python', 'python3', 'auggie'}
            
            for proc in psutil.process_iter(['pid', 'ppid', 'name']):
                try:
                    # Filter by process name first (much faster than cmdline)
                    if proc.info['name'] not in mcp_process_names:
                        continue
                        
                    # Only get cmdline for potential matches
                    cmdline = ' '.join(proc.cmdline())
                    
                    # Check if this is an orphaned MCP tool process
                    is_mcp_tool = any(pattern in cmdline for pattern in MCP_TOOL_PATTERNS)
                    
                    if is_mcp_tool and proc.info['ppid'] == 1:  # Orphaned (parent = init)
                        logger.warning(f"🧹 Found orphaned MCP process: {proc.info['pid']} {cmdline[:100]}")
                        try:
                            psutil.Process(proc.info['pid']).terminate()
                            orphaned_count += 1
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                            
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
                    
            if orphaned_count > 0:
                logger.info(f"🧹 Cleaned up {orphaned_count} orphaned MCP processes during monitoring")
                
            # Additional safety layer: shell-based cleanup
            _kill_orphaned_mcp_processes_shell()
                
        except Exception as e:
            logger.error(f"Error during orphan monitoring: {e}")
    
    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        return f"session-{uuid.uuid4().hex[:12]}"
    
    async def create_session(
        self,
        agent: str | None = None,
        working_directory: str | None = None,
    ) -> Session:
        """Create a new kiro-cli session.

        Args:
            agent: Optional agent name to use
            working_directory: Working directory for the session

        Returns:
            The created Session

        Raises:
            SessionError: If maximum sessions reached
        """
        async with self._lock:
            # 0 means unlimited sessions
            if self.config.max_sessions > 0 and len(self.sessions) >= self.config.max_sessions:
                raise SessionError(
                    code=ErrorCode.SESSION_LIMIT_REACHED,
                    details={"max_sessions": self.config.max_sessions},
                )

            session_id = self._generate_session_id()
            while session_id in self.sessions:
                session_id = self._generate_session_id()

            # Determine and validate working directory
            wd = working_directory or self.config.working_directory
            if wd and not os.path.isdir(wd):
                current_dir = os.getcwd()
                logger.warning(
                    f"Working directory does not exist: {wd}"
                )
                logger.info(
                    f"Using current directory instead: {current_dir}"
                )
                wd = current_dir
            elif not wd:
                wd = os.getcwd()
                logger.debug(f"No working directory specified, using current: {wd}")

            now = datetime.now()
            session = Session(
                id=session_id,
                created_at=now,
                last_active=now,
                agent=agent,
                working_directory=wd,
            )

            self.sessions[session_id] = session

            # Set as active if no active session
            if self.active_session_id is None:
                self.active_session_id = session_id

            return session
    
    async def get_session(self, session_id: str) -> Session:
        """Get a session by ID.
        
        Args:
            session_id: The session ID
            
        Returns:
            The Session
            
        Raises:
            SessionError: If session not found
        """
        session = self.sessions.get(session_id)
        if session is None:
            raise SessionError(
                code=ErrorCode.SESSION_NOT_FOUND,
                details={"session_id": session_id},
            )
        return session
    
    async def get_active_session(self) -> Session | None:
        """Get the currently active session."""
        if self.active_session_id is None:
            return None
        return self.sessions.get(self.active_session_id)
    
    async def list_sessions(self) -> list[Session]:
        """List all active sessions."""
        return list(self.sessions.values())
    
    async def switch_session(self, session_id: str) -> Session:
        """Switch to a specific session.
        
        Args:
            session_id: The session ID to switch to
            
        Returns:
            The switched-to Session
            
        Raises:
            SessionError: If session not found
        """
        session = await self.get_session(session_id)
        self.active_session_id = session_id
        session.update_activity()
        return session
    
    async def end_session(self, session_id: str) -> bool:
        """End and cleanup a session.
        
        Args:
            session_id: The session ID to end
            
        Returns:
            True if session was ended
            
        Raises:
            SessionError: If session not found
        """
        async with self._lock:
            session = self.sessions.get(session_id)
            if session is None:
                raise SessionError(
                    code=ErrorCode.SESSION_NOT_FOUND,
                    details={"session_id": session_id},
                )
            
            # Terminate process if running
            if session.process is not None:
                try:
                    session.process.terminate()
                    await asyncio.wait_for(
                        session.process.wait(),
                        timeout=5.0,
                    )
                except asyncio.TimeoutError:
                    session.process.kill()
                except Exception:
                    pass
            
            # Remove from sessions
            del self.sessions[session_id]
            
            # Update active session if needed
            if self.active_session_id == session_id:
                if self.sessions:
                    self.active_session_id = next(iter(self.sessions.keys()))
                else:
                    self.active_session_id = None
            
            return True
    
    async def get_or_create_session(
        self,
        session_id: str | None = None,
        agent: str | None = None,
    ) -> Session:
        """Get existing session or create new one.
        
        Args:
            session_id: Optional session ID to get
            agent: Agent to use if creating new session
            
        Returns:
            The Session
        """
        if session_id:
            return await self.get_session(session_id)
        
        active = await self.get_active_session()
        if active:
            return active
        
        return await self.create_session(agent=agent)
    
    async def cleanup_inactive_sessions(self) -> int:
        """Clean up sessions that have been inactive too long.
        
        Returns:
            Number of sessions cleaned up
        """
        now = datetime.now()
        timeout_seconds = self.config.session_timeout
        cleaned = 0
        
        async with self._lock:
            to_remove = []
            for session_id, session in self.sessions.items():
                elapsed = (now - session.last_active).total_seconds()
                if elapsed > timeout_seconds:
                    to_remove.append(session_id)
            
            for session_id in to_remove:
                session = self.sessions[session_id]
                if session.process is not None:
                    try:
                        session.process.terminate()
                    except Exception:
                        pass
                del self.sessions[session_id]
                cleaned += 1
            
            # Update active session if needed
            if self.active_session_id not in self.sessions:
                if self.sessions:
                    self.active_session_id = next(iter(self.sessions.keys()))
                else:
                    self.active_session_id = None
        
        return cleaned
