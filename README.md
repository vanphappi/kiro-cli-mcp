# Kiro CLI MCP Server

A Model Context Protocol (MCP) server that enables IDE agents like Cursor and Windsurf to orchestrate kiro-cli with advanced session management, process pooling, and robust error handling.

## Overview

Kiro CLI MCP Server bridges the gap between IDE agents and kiro-cli by providing a standardized MCP interface with enterprise-grade features:

- **10x Performance Improvement**: Process pooling reduces response time from ~500ms to ~50ms
- **Multi-Session Management**: Isolated contexts for different projects/workflows
- **Production-Ready Reliability**: Comprehensive error handling, timeout management, and process cleanup
- **Mock Mode**: Development and testing without kiro-cli dependency

## Features

### Core Capabilities
- **Chat Integration**: Send messages to kiro-cli and receive AI responses
- **Session Management**: Create, switch, and manage multiple isolated sessions
- **Command Execution**: Execute kiro-cli commands (`/help`, `/mcp`, etc.)
- **Custom Agents**: Use and list available custom agents
- **History Management**: Store and retrieve conversation history per session
- **Async Operations**: Background task execution with progress polling

### Performance & Reliability
- **Process Pooling**: Reuse warm kiro-cli processes for 10x faster responses
- **Process Tree Cleanup**: Prevent orphaned processes across platforms
- **Automatic Fallback**: Mock mode when kiro-cli unavailable
- **Timeout Handling**: Configurable timeouts with graceful cleanup
- **Session Isolation**: Per-project working directories and conversation state

## Installation

### Prerequisites
- Python 3.10+
- kiro-cli installed and available in PATH (for full functionality - uses mock mode if unavailable)

### From Source (Current Method)
```bash
git clone https://github.com/your-org/kiro-cli-mcp.git
cd kiro-cli-mcp
pip install -e .
```

### Via pip (After PyPI Publication)
```bash
# Will be available after publishing to PyPI
pip install kiro-cli-mcp
```

### Via uvx (After PyPI Publication)
```bash
# Will be available after publishing to PyPI
uvx install kiro-cli-mcp
```

## Configuration

### IDE Integration

Add to your IDE's MCP configuration file:

**Cursor/Claude Desktop** (`~/.config/claude-desktop/mcp.json`):
```json
{
  "mcpServers": {
    "kiro-cli-mcp": {
      "command": "uvx",
      "args": ["kiro-cli-mcp"],
      "env": {
        "KIRO_MCP_LOG_LEVEL": "INFO"
      }
    }
  }
}
```

**Windsurf** (`.windsurf/mcp.json`):
```json
{
  "mcpServers": {
    "kiro-cli-mcp": {
      "command": "python",
      "args": ["-m", "kiro_cli_mcp"],
      "env": {
        "KIRO_MCP_CLI_PATH": "/usr/local/bin/kiro-cli",
        "KIRO_MCP_POOL_SIZE": "5"
      },
      "autoApprove": [
        "kiro_session_list",
        "kiro_agents_list",
        "kiro_history"
      ]
    }
  }
}
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `KIRO_MCP_CLI_PATH` | Path to kiro-cli executable | `kiro-cli` |
| `KIRO_MCP_COMMAND_TIMEOUT` | Command timeout (seconds) - IDE-optimized | `30` |
| `KIRO_MCP_MAX_SESSIONS` | Maximum concurrent sessions | `10` |
| `KIRO_MCP_SESSION_TIMEOUT` | Session idle timeout (seconds) | `300` |
| `KIRO_MCP_CLEANUP_INTERVAL` | Session cleanup check interval (seconds) | `30` |
| `KIRO_MCP_LOG_LEVEL` | Logging level | `INFO` |
| `KIRO_MCP_DEFAULT_MODEL` | Default AI model for kiro-cli | `claude-opus-4.5` |
| `KIRO_MCP_DEFAULT_AGENT` | Default agent to use | `kiro_default` |
| `KIRO_MCP_LOG_RESPONSE` | Log full CLI responses for debugging | `true` |
| `KIRO_MCP_POOL_SIZE` | Process pool size | `5` |
| `KIRO_MCP_POOL_ENABLED` | Enable process pooling | `true` |
| `KIRO_MCP_POOL_IDLE_TIME` | Process idle time before recycling (seconds) | `300` |
| `KIRO_MCP_POOL_MAX_USES` | Max uses per process before recycling | `100` |
| `KIRO_MCP_MAX_ASYNC_TASKS` | Maximum concurrent async tasks | `100` |
| `KIRO_MCP_TASK_TTL` | Task result TTL (seconds) | `3600` |

## Available MCP Tools

### Session Management
- **`kiro_session_create`** - Create new session with optional agent and working directory
- **`kiro_session_list`** - List all active sessions
- **`kiro_session_switch`** - Switch to specific session
- **`kiro_session_end`** - End a session
- **`kiro_session_clear`** - Clear session history files
- **`kiro_session_save`** - Save session to file

### Chat & Commands
- **`kiro_chat`** - Send chat message and get AI response
- **`kiro_command`** - Execute kiro-cli commands (`/help`, `/mcp`, etc.)
- **`kiro_agents_list`** - List available custom agents

### History Management
- **`kiro_history`** - Get conversation history for session
- **`kiro_history_clear`** - Clear conversation history

### Async Operations
- **`kiro_chat_async`** - Start background chat task
- **`kiro_task_status`** - Poll task progress and results
- **`kiro_task_cancel`** - Cancel running task
- **`kiro_task_list`** - List active tasks

### Monitoring
- **`kiro_pool_stats`** - Get process pool performance statistics

## Usage Examples

### Basic Chat
```python
# Create session for project
await mcp_client.call_tool("kiro_session_create", {
    "working_directory": "/path/to/project",
    "agent": "code-reviewer"
})

# Send message
response = await mcp_client.call_tool("kiro_chat", {
    "message": "Analyze this codebase and suggest improvements"
})
```

### Multi-Project Workflow
```python
# Project A
session_a = await mcp_client.call_tool("kiro_session_create", {
    "working_directory": "/projects/frontend",
    "agent": "react-expert"
})

# Project B  
session_b = await mcp_client.call_tool("kiro_session_create", {
    "working_directory": "/projects/backend", 
    "agent": "python-expert"
})

# Switch between projects
await mcp_client.call_tool("kiro_session_switch", {
    "session_id": session_a["session_id"]
})
```

### Async Operations
```python
# Start long-running task
task = await mcp_client.call_tool("kiro_chat_async", {
    "message": "Generate comprehensive test suite"
})

# Poll for progress
while True:
    status = await mcp_client.call_tool("kiro_task_status", {
        "task_id": task["task_id"]
    })
    if status["status"] == "completed":
        break
    await asyncio.sleep(1)
```

## Architecture

### MCP Protocol Integration
- **Server**: Built on official MCP SDK (`mcp.server.Server`)
- **Transport**: JSON-RPC 2.0 over stdio
- **Tools**: 16 registered tools with schema validation
- **Resources**: Minimal resource handling for extensibility

### Process Management
```
IDE Agent → MCP Server → Process Pool → kiro-cli instances
                    ↓
              Session Manager → Isolated contexts per project
```

### Key Components
- **SessionManager**: Multi-session isolation and lifecycle management
- **ProcessPool**: Warm process reuse for 10x performance improvement  
- **CommandExecutor**: Robust command execution with timeout handling
- **StreamingTaskManager**: Async task execution with progress polling

### Performance Optimizations
1. **Process Pooling**: Reuse warm kiro-cli processes
2. **Session Affinity**: Route requests to appropriate process
3. **Intelligent Cleanup**: Remove idle/unhealthy processes
4. **Mock Mode**: Fast responses during development

## Development

### Setup
```bash
git clone https://github.com/your-org/kiro-cli-mcp.git
cd kiro-cli-mcp
pip install -e ".[dev]"
```

### Testing
```bash
# Run all tests
pytest

# With coverage
pytest --cov=kiro_cli_mcp --cov-report=html

# Property-based tests
pytest tests/test_config.py -v
```

### Code Quality
```bash
# Format code
ruff format .

# Lint
ruff check .

# Type checking
mypy src/
```

### Running Server
```bash
# Development mode with debug logging
python -m kiro_cli_mcp --log-level DEBUG

# With custom config
python -m kiro_cli_mcp --config config.json
```

### Contributing
1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## Troubleshooting

### kiro-cli Not Found
Server automatically enables **mock mode** if kiro-cli is unavailable:

```bash
# Check kiro-cli availability
which kiro-cli

# Set custom path
export KIRO_MCP_CLI_PATH=/custom/path/to/kiro-cli

# Verify server mode
python -m kiro_cli_mcp --log-level DEBUG
# Look for: "✅ kiro-cli is available" or "❌ kiro-cli not available: enabling mock mode"
```

### Performance Issues
```bash
# Verify process pooling is enabled
python -m kiro_cli_mcp --log-level DEBUG
# Look for: "🔄 Using pooled process execution"

# Check pool statistics
# Use kiro_pool_stats tool to monitor performance
```

### Session Management
```bash
# Increase session limits
export KIRO_MCP_MAX_SESSIONS=20
export KIRO_MCP_SESSION_TIMEOUT=7200  # 2 hours

# Clear stuck sessions
# Sessions auto-cleanup after timeout
```

### Process Cleanup
If you encounter orphaned processes:

```bash
# Unix/Linux/macOS
pkill -f kiro-cli

# Windows  
taskkill /F /IM kiro-cli.exe

# Check process groups (Unix)
ps -eo pid,pgid,cmd | grep kiro
```

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Support

- **Issues**: [GitHub Issues](https://github.com/your-org/kiro-cli-mcp/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-org/kiro-cli-mcp/discussions)
- **Documentation**: [Wiki](https://github.com/your-org/kiro-cli-mcp/wiki)
