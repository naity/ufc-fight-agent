import inspect
import json
from dataclasses import dataclass, field
from typing import Callable, Dict, Any, Optional, List, get_type_hints, Union
from ufc_fight_agent.ufc_data import *


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, dict[str, Any]]
    func: Callable[..., Any]

    def __call__(self, **kwargs):
        return self.func(**kwargs)

    def to_claude_format(self):
        """Convert to Claude's expected format"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": self.parameters,
                "required": [
                    k
                    for k, v in self.parameters.items()
                    if not v.get("optional", False)
                ],
            },
        }


def parse_docstring_params(docstring):
    """
    Extract parameter descriptions from a function's docstring.
    """
    params = {}
    lines = docstring.split("\n")

    # locate the 'Parameters:' line
    for i, line in enumerate(lines):
        if line.strip() == "Parameters:":
            break
    else:
        return params

    current_param = None
    for line in lines[i + 1 :]:
        line = line.strip()
        if not line:
            break

        if line.startswith("-"):
            line = line.lstrip("- ")
            key, value = line.split(":", 1)
            current_param = key.strip()
            params[current_param] = value.strip()
        elif current_param and line:
            # Continuation of previous parameter description
            params[current_param] = params[current_param] + " " + line

    return params


def python_type_to_json_schema(type_str):
    """
    Convert Python type string to JSON schema type.
    """
    type_map = {
        "str": "string",
        "int": "integer",
        "float": "number",
        "bool": "boolean",
        "list": "array",
        "dict": "object",
        "None": "null",
    }

    for py_type, json_type in type_map.items():
        if py_type in type_str:
            return json_type

    return "string"


def tool(func):
    """
    Decorator to convert a function into a Tool.
    """
    name = func.__name__
    docstring = inspect.getdoc(func) or ""

    description = (
        docstring.split("Parameters:")[0].strip()
        if "Parameters:" in docstring
        else docstring
    )

    param_descriptions = parse_docstring_params(docstring)

    # Get type annotations
    type_hints = get_type_hints(func)
    sig = inspect.signature(func)

    # Build parameter schema
    parameters = {}
    for param_name, param in sig.parameters.items():
        param_type = type_hints.get(param_name, Any)
        is_optional = "Optional" in str(param_type)

        if is_optional:
            # Extract inner type from Optional[X]
            inner_type = str(param_type).split("[")[1].split("]")[0]
            json_type = python_type_to_json_schema(inner_type)
        else:
            json_type = python_type_to_json_schema(str(param_type))

        param_info = {
            "type": json_type,
            "description": param_descriptions.get(param_name, ""),
        }

        if param.default is not param.empty and param.default is not None:
            param_info["default"] = param.default

        if param.default is not param.empty or is_optional:
            param_info["optional"] = True

        parameters[param_name] = param_info

    return Tool(name=name, description=description, parameters=parameters, func=func)
