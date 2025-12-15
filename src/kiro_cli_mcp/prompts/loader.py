"""Prompt loader for loading and parsing prompt files."""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PromptInfo:
    """Information about a prompt."""
    name: str  # filename without extension
    description: str  # from frontmatter
    trigger: str  # extracted trigger command like /code, /plan
    content: str  # full content of the prompt (with frontmatter)
    body: str  # content without frontmatter (for execution)
    always_apply: bool = False
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "trigger": self.trigger,
            "always_apply": self.always_apply,
        }


class PromptLoader:
    """Load and parse prompt files from a directory."""
    
    def __init__(self, prompts_dir: Optional[Path] = None):
        """Initialize loader with prompts directory.
        
        Args:
            prompts_dir: Path to prompts directory. If None, uses default data/ dir.
        """
        if prompts_dir is None:
            prompts_dir = Path(__file__).parent / "data"
        self.prompts_dir = Path(prompts_dir)
        self._prompts: dict[str, PromptInfo] = {}
        self._loaded = False
    
    def load_all(self) -> dict[str, PromptInfo]:
        """Load all prompts from the directory.
        
        Returns:
            Dictionary mapping prompt name to PromptInfo
        """
        if self._loaded:
            return self._prompts
        
        if not self.prompts_dir.exists():
            logger.warning(f"Prompts directory not found: {self.prompts_dir}")
            return {}
        
        for file_path in self.prompts_dir.glob("*.md"):
            try:
                prompt = self._parse_prompt_file(file_path)
                if prompt:
                    self._prompts[prompt.name] = prompt
                    logger.debug(f"Loaded prompt: {prompt.name} ({prompt.trigger})")
            except Exception as e:
                logger.error(f"Failed to load prompt {file_path}: {e}")
        
        self._loaded = True
        logger.info(f"Loaded {len(self._prompts)} prompts from {self.prompts_dir}")
        return self._prompts
    
    def _parse_prompt_file(self, file_path: Path) -> Optional[PromptInfo]:
        """Parse a single prompt file.
        
        Args:
            file_path: Path to the .md file
            
        Returns:
            PromptInfo or None if parsing fails
        """
        content = file_path.read_text(encoding="utf-8")
        name = file_path.stem
        
        # Parse frontmatter (YAML between ---)
        frontmatter = {}
        body = content
        
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter_text = parts[1].strip()
                body = parts[2].strip()
                frontmatter = self._parse_frontmatter(frontmatter_text)
        
        # Extract description and trigger from frontmatter
        description = frontmatter.get("description", "")
        always_apply = frontmatter.get("alwaysApply", False)
        
        # Extract trigger command from description (e.g., "/code [request]" -> "/code")
        trigger = self._extract_trigger(description)
        
        return PromptInfo(
            name=name,
            description=description,
            trigger=trigger,
            content=content,  # Full content with frontmatter (for reference)
            body=body,  # Content without frontmatter (for execution)
            always_apply=always_apply,
        )
    
    def _parse_frontmatter(self, text: str) -> dict:
        """Parse simple YAML frontmatter."""
        result = {}
        for line in text.split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                # Handle boolean
                if value.lower() == "true":
                    value = True
                elif value.lower() == "false":
                    value = False
                result[key] = value
        return result
    
    def _extract_trigger(self, description: str) -> str:
        """Extract trigger command from description.
        
        Examples:
            "/code [request]" -> "/code"
            "/plan [request to make a plan]" -> "/plan"
            "/commit" -> "/commit"
        """
        if not description:
            return ""
        
        # Match /command pattern
        match = re.match(r'^(/\w+)', description)
        if match:
            return match.group(1)
        return ""
    
    def get_prompt(self, name: str) -> Optional[PromptInfo]:
        """Get a specific prompt by name."""
        if not self._loaded:
            self.load_all()
        return self._prompts.get(name)
    
    def get_prompt_by_trigger(self, trigger: str) -> Optional[PromptInfo]:
        """Get a prompt by its trigger command."""
        if not self._loaded:
            self.load_all()
        
        for prompt in self._prompts.values():
            if prompt.trigger == trigger:
                return prompt
        return None
    
    def list_prompts(self) -> list[PromptInfo]:
        """List all available prompts."""
        if not self._loaded:
            self.load_all()
        return list(self._prompts.values())
    
    def get_prompts_summary(self) -> str:
        """Get a summary of all prompts for AI selection.
        
        Returns:
            Formatted string listing all prompts with name and description
        """
        if not self._loaded:
            self.load_all()
        
        lines = ["Available prompts:"]
        for prompt in self._prompts.values():
            lines.append(f"- {prompt.name}: {prompt.description}")
        
        return "\n".join(lines)
    
    def get_prompts_categorized(self) -> str:
        """Get categorized prompts summary for better AI selection.
        
        Returns:
            Formatted string with prompts organized by category
        """
        if not self._loaded:
            self.load_all()
        
        # Build categorized list from actual loaded prompts
        lines = []
        for prompt in sorted(self._prompts.values(), key=lambda p: p.name):
            # Extract short description (first part before [)
            desc = prompt.description
            if "[" in desc:
                desc = desc.split("[")[0].strip()
            lines.append(f"- {prompt.name}: {desc}")
        
        return "\n".join(lines)
