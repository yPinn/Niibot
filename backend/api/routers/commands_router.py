"""Bot commands and components API routes"""

import ast
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.dependencies import get_current_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/commands", tags=["commands"])


class CommandInfo(BaseModel):
    name: str
    aliases: list[str]
    description: str | None
    platform: str  # "discord" or "twitch"


class ComponentInfo(BaseModel):
    name: str
    description: str | None
    file_path: str
    platform: str
    commands: list[CommandInfo]


def extract_docstring(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> str | None:
    """Extract docstring from function or class node"""
    if (
        node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    ):
        # 只取第一行作為簡短描述
        return node.body[0].value.value.split("\n")[0].strip()
    return None


def extract_decorator_arg(decorator: ast.Call, arg_name: str) -> Any:
    """Extract argument value from decorator call"""
    for keyword in decorator.keywords:
        if keyword.arg == arg_name:
            if isinstance(keyword.value, ast.Constant):
                return keyword.value.value
            elif isinstance(keyword.value, ast.List):
                return [elt.value for elt in keyword.value.elts if isinstance(elt, ast.Constant)]
    return None


def parse_python_file(file_path: Path, platform: str) -> ComponentInfo | None:
    """Parse Python file to extract component and command information"""
    try:
        with open(file_path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(file_path))

        # Find the component/cog class
        component_class = None
        component_name = None
        component_desc = None

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Check if it inherits from commands.Cog or commands.Component
                for base in node.bases:
                    base_name = ""
                    if isinstance(base, ast.Attribute):
                        base_name = base.attr
                    elif isinstance(base, ast.Name):
                        base_name = base.id

                    if base_name in ("Cog", "Component"):
                        component_class = node
                        component_name = node.name
                        component_desc = extract_docstring(node)
                        break

        if not component_class:
            return None

        # Extract commands from the class
        commands_list: list[CommandInfo] = []

        for node in component_class.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Check for @commands.command or @commands.slash_command decorator
                for decorator in node.decorator_list:
                    cmd_name = None
                    aliases: list[str] = []

                    if isinstance(decorator, ast.Call):
                        # Get decorator function name
                        decorator_name = ""
                        if isinstance(decorator.func, ast.Attribute):
                            decorator_name = decorator.func.attr
                        elif isinstance(decorator.func, ast.Name):
                            decorator_name = decorator.func.id

                        if decorator_name in ("command", "slash_command"):
                            # Extract command name
                            cmd_name = extract_decorator_arg(decorator, "name")
                            if not cmd_name:
                                cmd_name = node.name

                            # Extract aliases
                            aliases = extract_decorator_arg(decorator, "aliases") or []

                            # Extract description from docstring
                            description = extract_docstring(node)

                            commands_list.append(
                                CommandInfo(
                                    name=cmd_name,
                                    aliases=aliases,
                                    description=description,
                                    platform=platform,
                                )
                            )
                            break

        return ComponentInfo(
            name=component_name or file_path.stem,
            description=component_desc,
            file_path=str(file_path.relative_to(file_path.parent.parent.parent)),
            platform=platform,
            commands=commands_list,
        )

    except Exception as e:
        logger.error(f"Error parsing {file_path}: {e}")
        return None


def get_discord_components() -> list[ComponentInfo]:
    """Get all Discord cogs"""
    cogs_dir = Path(__file__).parent.parent.parent / "discord" / "cogs"
    components = []

    if not cogs_dir.exists():
        logger.warning(f"Discord cogs directory not found: {cogs_dir}")
        return []

    for py_file in cogs_dir.glob("*.py"):
        if py_file.name.startswith("_"):
            continue

        component = parse_python_file(py_file, "discord")
        if component:
            components.append(component)

    return components


def get_twitch_components() -> list[ComponentInfo]:
    """Get all Twitch components"""
    components_dir = Path(__file__).parent.parent.parent / "twitch" / "components"
    components = []

    if not components_dir.exists():
        logger.warning(f"Twitch components directory not found: {components_dir}")
        return []

    for py_file in components_dir.glob("*.py"):
        if py_file.name.startswith("_"):
            continue

        component = parse_python_file(py_file, "twitch")
        if component:
            components.append(component)

    return components


@router.get("/components")
async def get_all_components(user_id: str = Depends(get_current_user_id)):
    """Get all bot components (Discord cogs and Twitch components)"""
    try:
        discord_components = get_discord_components()
        twitch_components = get_twitch_components()

        return {
            "discord": discord_components,
            "twitch": twitch_components,
            "total": len(discord_components) + len(twitch_components),
        }

    except Exception as e:
        logger.exception(f"Failed to get components: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch components") from None
