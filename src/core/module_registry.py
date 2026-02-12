"""Module registry for managing feature modules."""

from typing import ClassVar

from src.core.module import Module


class _RegistryState:
    """Singleton state for module registry."""

    modules: ClassVar[dict[str, Module]] = {}


_registry = _RegistryState()


def register_module(module: Module) -> None:
    """Register a module in the registry.

    Args:
        module: Module instance to register

    Raises:
        ValueError: If a module with the same name is already registered
    """
    if module.name in _registry.modules:
        msg = f"Module '{module.name}' is already registered"
        raise ValueError(msg)
    _registry.modules[module.name] = module


def get_modules() -> dict[str, Module]:
    """Get all registered modules.

    Returns:
        Dictionary mapping module names to Module instances
    """
    return dict(_registry.modules)


def get_module(name: str) -> Module | None:
    """Get a specific module by name.

    Args:
        name: Module name to retrieve

    Returns:
        Module instance if found, None otherwise
    """
    return _registry.modules.get(name)


def get_all_table_schemas() -> dict[str, str]:
    """Get all table schemas from registered modules.

    Returns:
        Dictionary mapping table names to CREATE TABLE SQL statements
    """
    all_schemas: dict[str, str] = {}
    for module in _registry.modules.values():
        for table_name, schema in module.get_table_schemas().items():
            if table_name in all_schemas:
                msg = f"Duplicate table schema '{table_name}' from module '{module.name}'"
                raise ValueError(msg)
            all_schemas[table_name] = schema
    return all_schemas


def get_all_indexes() -> list[str]:
    """Get all indexes from registered modules.

    Returns:
        List of CREATE INDEX SQL statements
    """
    all_indexes: list[str] = []
    for module in _registry.modules.values():
        all_indexes.extend(module.get_indexes())
    return all_indexes
