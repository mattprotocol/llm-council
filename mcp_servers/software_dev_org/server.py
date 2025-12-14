#!/usr/bin/env python3
"""
Software Development Organization MCP Server.

Provides tools for:
- Safe sandboxed app execution via Docker
- Project file management (write, read, list, archive)
- AI-driven development team workflow (mcp-dev-team)

Tools:
- safe-app-execution: Run code in a sandboxed Docker container
- write-file: Write content to a project file
- read-file: Read content from a project file
- list-files: List files in a project folder
- create-archive: Create bzip2 archive of a project
- mcp-dev-team: AI-driven MCP server development workflow
"""

import json
import os
import subprocess
import tarfile
import tempfile
import shutil
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime


# Base directory for projects
PROJECTS_BASE = Path(__file__).parent.parent.parent / "data" / "dev_projects"
DOCKER_IMAGE_NAME = "llm-council-dev-env"


def ensure_projects_dir():
    """Ensure the projects directory exists."""
    PROJECTS_BASE.mkdir(parents=True, exist_ok=True)
    return PROJECTS_BASE


def get_project_path(project_name: str) -> Path:
    """Get the path for a project, creating it if needed."""
    # Sanitize project name
    safe_name = "".join(c for c in project_name if c.isalnum() or c in "-_").strip()
    if not safe_name:
        safe_name = "unnamed_project"
    
    project_path = ensure_projects_dir() / safe_name
    return project_path


def build_docker_image() -> Dict[str, Any]:
    """Build the development environment Docker image if it doesn't exist."""
    # Check if image exists
    result = subprocess.run(
        ["docker", "images", "-q", DOCKER_IMAGE_NAME],
        capture_output=True, text=True
    )
    
    if result.stdout.strip():
        return {"exists": True, "image": DOCKER_IMAGE_NAME}
    
    # Create Dockerfile
    dockerfile_content = '''
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install base tools
RUN apt-get update && apt-get install -y \\
    build-essential \\
    curl \\
    wget \\
    git \\
    bzip2 \\
    python3 \\
    python3-pip \\
    python3-venv \\
    nodejs \\
    npm \\
    && rm -rf /var/lib/apt/lists/*

# Install Rust
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# Install Go
RUN wget -q https://go.dev/dl/go1.21.5.linux-amd64.tar.gz \\
    && tar -C /usr/local -xzf go1.21.5.linux-amd64.tar.gz \\
    && rm go1.21.5.linux-amd64.tar.gz
ENV PATH="/usr/local/go/bin:${PATH}"

# Create workspace
WORKDIR /workspace

# Default command
CMD ["/bin/bash"]
'''
    
    # Create temp directory for build
    with tempfile.TemporaryDirectory() as tmpdir:
        dockerfile_path = Path(tmpdir) / "Dockerfile"
        dockerfile_path.write_text(dockerfile_content)
        
        # Build image
        result = subprocess.run(
            ["docker", "build", "-t", DOCKER_IMAGE_NAME, tmpdir],
            capture_output=True, text=True, timeout=600
        )
        
        if result.returncode != 0:
            return {
                "success": False,
                "error": f"Failed to build Docker image: {result.stderr}"
            }
    
    return {"success": True, "image": DOCKER_IMAGE_NAME, "built": True}


def safe_app_execution(archive_path: str, run_script: str = "run.sh") -> Dict[str, Any]:
    """
    Execute code in a sandboxed Docker container.
    
    Args:
        archive_path: Path to bzip2 archive to unpack and run
        run_script: Name of the script to execute (default: run.sh)
    
    Returns:
        Execution log with all actions and results
    """
    log = []
    log.append(f"[{datetime.now().isoformat()}] Starting safe app execution")
    
    try:
        # Ensure Docker image exists
        log.append("Checking/building Docker image...")
        image_result = build_docker_image()
        if not image_result.get("success", True) and not image_result.get("exists"):
            return {"success": False, "error": image_result.get("error"), "log": log}
        
        if image_result.get("built"):
            log.append(f"Built Docker image: {DOCKER_IMAGE_NAME}")
        else:
            log.append(f"Using existing Docker image: {DOCKER_IMAGE_NAME}")
        
        # Verify archive exists
        archive = Path(archive_path)
        if not archive.exists():
            return {"success": False, "error": f"Archive not found: {archive_path}", "log": log}
        
        log.append(f"Found archive: {archive_path}")
        
        # Create temp directory for extraction
        with tempfile.TemporaryDirectory() as tmpdir:
            # Extract archive
            log.append("Extracting archive...")
            try:
                with tarfile.open(archive_path, "r:bz2") as tar:
                    tar.extractall(tmpdir)
                log.append("Archive extracted successfully")
            except Exception as e:
                return {"success": False, "error": f"Failed to extract archive: {e}", "log": log}
            
            # Check for run script
            run_script_path = Path(tmpdir) / run_script
            if not run_script_path.exists():
                # Look in subdirectories
                for subdir in Path(tmpdir).iterdir():
                    if subdir.is_dir():
                        candidate = subdir / run_script
                        if candidate.exists():
                            run_script_path = candidate
                            break
            
            if not run_script_path.exists():
                return {
                    "success": False,
                    "error": f"Run script not found: {run_script}",
                    "log": log,
                    "files": list(str(p) for p in Path(tmpdir).rglob("*"))
                }
            
            log.append(f"Found run script: {run_script_path}")
            
            # Run in Docker container
            log.append("Starting Docker container...")
            container_name = f"llm-council-sandbox-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            # Run container with mounted directory
            result = subprocess.run(
                [
                    "docker", "run",
                    "--rm",
                    "--name", container_name,
                    "-v", f"{tmpdir}:/workspace",
                    "--workdir", "/workspace",
                    "--network", "none",  # No network access for security
                    "--memory", "512m",   # Memory limit
                    "--cpus", "1",        # CPU limit
                    DOCKER_IMAGE_NAME,
                    "bash", "-c", f"chmod +x {run_script} && ./{run_script}"
                ],
                capture_output=True, text=True, timeout=300
            )
            
            log.append(f"Container exited with code: {result.returncode}")
            
            return {
                "success": result.returncode == 0,
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "log": log
            }
            
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Execution timed out (5 minutes)", "log": log}
    except Exception as e:
        log.append(f"Error: {str(e)}")
        return {"success": False, "error": str(e), "log": log}


def write_file(project_name: str, filename: str, content: str) -> Dict[str, Any]:
    """
    Write content to a file in a project folder.
    
    Args:
        project_name: Name of the project folder
        filename: Name of the file to write
        content: Content to write to the file
    """
    try:
        project_path = get_project_path(project_name)
        project_path.mkdir(parents=True, exist_ok=True)
        
        # Handle subdirectories in filename
        file_path = project_path / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_path.write_text(content)
        
        return {
            "success": True,
            "project": project_name,
            "file": filename,
            "path": str(file_path),
            "size": len(content)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def read_file(project_name: str, filename: str) -> Dict[str, Any]:
    """
    Read content from a file in a project folder.
    
    Args:
        project_name: Name of the project folder
        filename: Name of the file to read
    """
    try:
        project_path = get_project_path(project_name)
        file_path = project_path / filename
        
        if not file_path.exists():
            return {"success": False, "error": f"File not found: {filename}"}
        
        content = file_path.read_text()
        
        return {
            "success": True,
            "project": project_name,
            "file": filename,
            "content": content,
            "size": len(content)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_files(project_name: str) -> Dict[str, Any]:
    """
    List all files in a project folder.
    
    Args:
        project_name: Name of the project folder
    """
    try:
        project_path = get_project_path(project_name)
        
        if not project_path.exists():
            return {"success": False, "error": f"Project not found: {project_name}"}
        
        files = []
        for path in project_path.rglob("*"):
            if path.is_file():
                rel_path = path.relative_to(project_path)
                files.append({
                    "name": str(rel_path),
                    "size": path.stat().st_size
                })
        
        return {
            "success": True,
            "project": project_name,
            "path": str(project_path),
            "files": files,
            "count": len(files)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_archive(project_name: str) -> Dict[str, Any]:
    """
    Create a bzip2 archive of a project folder.
    
    Args:
        project_name: Name of the project folder
    """
    try:
        project_path = get_project_path(project_name)
        
        if not project_path.exists():
            return {"success": False, "error": f"Project not found: {project_name}"}
        
        # Create archive in parent directory
        archive_path = project_path.parent / f"{project_name}.tar.bz2"
        
        with tarfile.open(archive_path, "w:bz2") as tar:
            tar.add(project_path, arcname=project_name)
        
        return {
            "success": True,
            "project": project_name,
            "archive": str(archive_path),
            "size": archive_path.stat().st_size
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# Tool definitions
TOOLS = [
    {
        "name": "safe-app-execution",
        "description": "Execute code in a sandboxed Docker container. Unpacks a bzip2 archive, makes run.sh executable, and runs it with resource limits and no network access.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "archive_path": {
                    "type": "string",
                    "description": "Path to the bzip2 archive (.tar.bz2) to unpack and run"
                },
                "run_script": {
                    "type": "string",
                    "description": "Name of the script to execute (default: run.sh)"
                }
            },
            "required": ["archive_path"]
        }
    },
    {
        "name": "write-file",
        "description": "Write content to a file in a project folder. Creates the project folder if it doesn't exist.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_name": {
                    "type": "string",
                    "description": "Name of the project folder"
                },
                "filename": {
                    "type": "string",
                    "description": "Name of the file to write (can include subdirectories)"
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file"
                }
            },
            "required": ["project_name", "filename", "content"]
        }
    },
    {
        "name": "read-file",
        "description": "Read content from a file in a project folder.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_name": {
                    "type": "string",
                    "description": "Name of the project folder"
                },
                "filename": {
                    "type": "string",
                    "description": "Name of the file to read"
                }
            },
            "required": ["project_name", "filename"]
        }
    },
    {
        "name": "list-files",
        "description": "List all files in a project folder.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_name": {
                    "type": "string",
                    "description": "Name of the project folder"
                }
            },
            "required": ["project_name"]
        }
    },
    {
        "name": "create-archive",
        "description": "Create a bzip2 archive (.tar.bz2) of a project folder.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_name": {
                    "type": "string",
                    "description": "Name of the project folder to archive"
                }
            },
            "required": ["project_name"]
        }
    }
]


def handle_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle a JSON-RPC request."""
    method = request.get("method")
    params = request.get("params", {})
    request_id = request.get("id")
    
    response = {"jsonrpc": "2.0", "id": request_id}
    
    try:
        if method == "initialize":
            response["result"] = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "software-dev-org", "version": "1.0.0"}
            }
        
        elif method == "notifications/initialized":
            return None
        
        elif method == "tools/list":
            response["result"] = {"tools": TOOLS}
        
        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            
            if tool_name == "safe-app-execution":
                result = safe_app_execution(
                    arguments.get("archive_path"),
                    arguments.get("run_script", "run.sh")
                )
            elif tool_name == "write-file":
                result = write_file(
                    arguments.get("project_name"),
                    arguments.get("filename"),
                    arguments.get("content")
                )
            elif tool_name == "read-file":
                result = read_file(
                    arguments.get("project_name"),
                    arguments.get("filename")
                )
            elif tool_name == "list-files":
                result = list_files(arguments.get("project_name"))
            elif tool_name == "create-archive":
                result = create_archive(arguments.get("project_name"))
            else:
                response["error"] = {"code": -32601, "message": f"Unknown tool: {tool_name}"}
                return response
            
            response["result"] = {
                "content": [{"type": "text", "text": json.dumps(result, indent=2)}]
            }
        
        else:
            response["error"] = {"code": -32601, "message": f"Unknown method: {method}"}
    
    except Exception as e:
        response["error"] = {"code": -32000, "message": str(e)}
    
    return response


def main():
    """Main entry point for the MCP server."""
    from mcp_servers.http_wrapper import stdio_main
    stdio_main(handle_request, "Software Dev Org MCP")


if __name__ == "__main__":
    main()
