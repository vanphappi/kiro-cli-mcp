"""AI-powered prompt matcher using kiro-cli."""

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Optional, Callable, Awaitable

from .loader import PromptLoader, PromptInfo

logger = logging.getLogger(__name__)

# Regex to strip ANSI escape codes (colors, cursor movement, etc.)
# Handles both real escape codes (\x1b[...m) and text representations ([...m)
ANSI_ESCAPE_PATTERN = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
ANSI_TEXT_PATTERN = re.compile(r'\[[\d;]*m')  # Matches [38;5;141m, [0m, etc.


def strip_ansi_codes(text: str) -> str:
    """Remove ANSI escape codes from text."""
    # First strip real ANSI codes
    text = ANSI_ESCAPE_PATTERN.sub('', text)
    # Then strip text representations of ANSI codes
    text = ANSI_TEXT_PATTERN.sub('', text)
    return text

# Selection prompt template - optimized for accurate prompt matching
SELECTION_PROMPT = """You are a prompt routing system. Your ONLY job is to output a single word.

## Available Prompts (name: when to use)
{prompts_categorized}

## User Message
"{message}"

## Rules
1. Output ONLY the prompt name (lowercase, no quotes, no explanation)
2. Match based on PRIMARY intent, not keywords
3. Output "none" if:
   - Message is a simple question/greeting
   - Message doesn't fit any prompt's purpose
   - Unclear intent

## Quick Reference
- Writing/implementing code → code
- Planning/designing before coding → plan  
- Reviewing code changes → review
- Committing changes → commit
- Finding bugs/errors → bugfinder
- Deep analysis/research → analyze, research, deepdive
- Documentation questions → docs
- General questions/how-to → how

Output:"""

# Categorized prompts for better AI understanding
PROMPTS_CATEGORIES = {
    "code_writing": {
        "code": "Write/implement code based on requirements",
        "deepcode": "Complex code implementation with deep analysis first",
        "taskcode": "Implement code for a specific task",
        "plancode": "Plan then implement code",
        "copycode": "Copy/adapt code from one file to another",
    },
    "planning_design": {
        "plan": "Create detailed implementation plan before coding",
        "uidesign": "Design UI/interface layouts",
        "prisma": "Design database schema with Prisma",
        "setup": "Setup new project structure",
    },
    "code_review_quality": {
        "review": "Review uncommitted code changes",
        "commit": "Commit code changes with proper message",
        "recheck": "Re-verify/validate previous work",
        "gitmerge": "Handle git merge operations",
        "gitlabreview": "Review GitLab merge requests",
    },
    "debugging_analysis": {
        "bugfinder": "Find and identify bugs/errors",
        "analyze": "Deep analysis of code/project (read-only)",
        "sophia": "Troubleshoot problems/issues",
    },
    "research_learning": {
        "research": "Deep internet research on topics",
        "docs": "Search and learn from documentation",
        "searchlib": "Find libraries for specific tasks",
        "search": "General search queries",
        "deepdive": "Deep exploration of features/concepts",
        "deepthink": "Complex problem solving with deep thinking",
    },
    "task_management": {
        "addtask": "Add tasks to task list",
        "exec": "Execute commands in loop with feedback",
        "guide": "Follow specific guidelines",
        "how": "Answer how-to questions",
        "story": "Convert content to user stories",
    },
}


class PromptMatcher:
    """AI-powered prompt matcher that uses kiro-cli to select appropriate prompts."""
    
    def __init__(
        self,
        prompts_dir: Optional[Path] = None,
        kiro_cli_executor: Optional[Callable[[str, str], Awaitable[str]]] = None,
    ):
        """Initialize matcher.
        
        Args:
            prompts_dir: Path to prompts directory
            kiro_cli_executor: Async function to execute kiro-cli chat.
                              Signature: (message, working_dir) -> response
        """
        self.loader = PromptLoader(prompts_dir)
        self._executor = kiro_cli_executor
        self._enabled = True
    
    def set_executor(self, executor: Callable[[str, str], Awaitable[str]]) -> None:
        """Set the kiro-cli executor function."""
        self._executor = executor
    
    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable prompt matching."""
        self._enabled = enabled
    
    def _build_categorized_summary(self) -> str:
        """Build categorized prompt summary for AI selection."""
        lines = []
        
        # Use predefined categories for better organization
        for category, prompts_in_cat in PROMPTS_CATEGORIES.items():
            category_name = category.replace("_", " ").title()
            lines.append(f"\n### {category_name}")
            for name, desc in prompts_in_cat.items():
                # Only include if prompt exists
                if self.loader.get_prompt(name):
                    lines.append(f"- {name}: {desc}")
        
        # Add any prompts not in categories
        categorized_names = set()
        for prompts_in_cat in PROMPTS_CATEGORIES.values():
            categorized_names.update(prompts_in_cat.keys())
        
        uncategorized = []
        for prompt in self.loader.list_prompts():
            if prompt.name not in categorized_names:
                uncategorized.append(f"- {prompt.name}: {prompt.description}")
        
        if uncategorized:
            lines.append("\n### Other")
            lines.extend(uncategorized)
        
        return "\n".join(lines)
    
    def _check_explicit_trigger(self, message: str) -> Optional[PromptInfo]:
        """Check if message starts with an explicit trigger command.
        
        Args:
            message: User message
            
        Returns:
            PromptInfo if explicit trigger found, None otherwise
        """
        message = message.strip()
        
        # Check for explicit trigger at start of message
        match = re.match(r'^(/\w+)', message)
        if match:
            trigger = match.group(1)
            prompt = self.loader.get_prompt_by_trigger(trigger)
            if prompt:
                logger.info(f"Found explicit trigger: {trigger} -> {prompt.name}")
                return prompt
        
        return None
    
    async def select_prompt(
        self,
        message: str,
        working_dir: Optional[str] = None,
    ) -> Optional[PromptInfo]:
        """Select the most appropriate prompt for a message using AI.
        
        Args:
            message: User message to analyze
            working_dir: Working directory for kiro-cli execution
            
        Returns:
            Selected PromptInfo or None if no suitable prompt
        """
        if not self._enabled:
            return None
        
        # First check for explicit trigger
        explicit = self._check_explicit_trigger(message)
        if explicit:
            return explicit
        
        # Use AI to select prompt
        if not self._executor:
            logger.warning("No kiro-cli executor configured, skipping AI selection")
            return None
        
        prompts_categorized = self._build_categorized_summary()
        if not prompts_categorized:
            logger.warning("No prompts available for selection")
            return None
        
        selection_message = SELECTION_PROMPT.format(
            prompts_categorized=prompts_categorized,
            message=message[:300],  # Limit message length for faster processing
        )
        
        try:
            logger.info("🤖 Using AI to select appropriate prompt...")
            response = await self._executor(selection_message, working_dir or os.getcwd())
            
            # Strip ANSI escape codes from response (kiro-cli may include colors)
            response = strip_ansi_codes(response)
            logger.debug(f"AI response (cleaned): {response[:200]}")
            
            # Parse response - kiro-cli may include tool calls and verbose output
            # Look for the final prompt name which typically appears after "> " at the end
            selected_name = None
            
            # Strategy 1: Look for "> promptname" pattern at end of response
            final_line_match = re.search(r'>\s*(\w+)\s*$', response)
            if final_line_match:
                selected_name = final_line_match.group(1).lower()
                logger.debug(f"Extracted prompt from '> name' pattern: {selected_name}")
            
            # Strategy 2: If response is short and clean, use it directly
            if not selected_name:
                clean_response = response.strip().lower()
                # Remove common prefixes/suffixes
                clean_response = re.sub(r'^(output:|selected:|prompt:)\s*', '', clean_response)
                clean_response = re.sub(r'["\'\s>]', '', clean_response)
                
                # If it's a single word matching a known prompt, use it
                first_word = clean_response.split('\n')[0].split()[0] if clean_response.split() else ''
                if first_word and len(first_word) < 30 and self.loader.get_prompt(first_word):
                    selected_name = first_word
                    logger.debug(f"Extracted prompt from clean response: {selected_name}")
            
            # Strategy 3: Search for any known prompt name in the response
            if not selected_name:
                for prompt_info in self.loader.list_prompts():
                    # Look for the prompt name as a standalone word near the end
                    pattern = rf'\b{re.escape(prompt_info.name)}\b'
                    matches = list(re.finditer(pattern, response.lower()))
                    if matches:
                        # Take the last occurrence (most likely the final answer)
                        selected_name = prompt_info.name
                        logger.debug(f"Found prompt name in response: {selected_name}")
                        break
            
            if not selected_name:
                selected_name = ""
            
            if selected_name == "none" or not selected_name:
                logger.info("AI selected: none (no suitable prompt)")
                return None
            
            prompt = self.loader.get_prompt(selected_name)
            if prompt:
                logger.info(f"AI selected prompt: {selected_name}")
                return prompt
            else:
                logger.warning(f"AI selected unknown prompt: {selected_name}")
                return None
                
        except Exception as e:
            logger.error(f"Error during AI prompt selection: {e}")
            return None
    
    def enhance_message(
        self,
        message: str,
        prompt: PromptInfo,
    ) -> str:
        """Enhance a message with prompt content.
        
        Args:
            message: Original user message
            prompt: Selected prompt to apply
            
        Returns:
            Enhanced message with prompt content prepended
        """
        # Remove the trigger command from message if present
        clean_message = message.strip()
        if prompt.trigger and clean_message.startswith(prompt.trigger):
            clean_message = clean_message[len(prompt.trigger):].strip()
        
        # Combine prompt body (without frontmatter) with user message - raw format
        enhanced = f"""{prompt.body}

{clean_message}"""
        
        logger.info(f"✨ Enhanced message with prompt: {prompt.name}")
        logger.info(f"📝 Final message to execute ({len(enhanced)} chars)")
        
        # Log full message at DEBUG level, preview at INFO level
        logger.debug("=" * 60)
        logger.debug(f"FULL ENHANCED MESSAGE:\n{enhanced}")
        logger.debug("=" * 60)
        
        # Log structure summary at INFO level
        logger.info(f"   Prompt body: {len(prompt.body)} chars")
        logger.info(f"   User request: {len(clean_message)} chars")
        logger.info(f"   User request preview: {clean_message[:100]}{'...' if len(clean_message) > 100 else ''}")
        
        return enhanced
    
    async def process_message(
        self,
        message: str,
        working_dir: Optional[str] = None,
    ) -> tuple[str, Optional[PromptInfo]]:
        """Process a message: select prompt and enhance if applicable.
        
        Args:
            message: Original user message
            working_dir: Working directory for kiro-cli
            
        Returns:
            Tuple of (processed_message, selected_prompt)
            If no prompt selected, returns (original_message, None)
        """
        prompt = await self.select_prompt(message, working_dir)
        
        if prompt:
            enhanced = self.enhance_message(message, prompt)
            return enhanced, prompt
        
        return message, None
