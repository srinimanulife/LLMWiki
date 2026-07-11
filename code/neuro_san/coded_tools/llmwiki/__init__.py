# LLMWiki domain coded tools
#
# Provide a minimal CodedTool stub when neuro-san is not installed
# (e.g. Streamlit container, unit-test runner without the full Neuro SAN wheel).
# When neuro-san IS installed the real CodedTool is imported instead.
import sys

try:
    from neuro_san.interfaces.coded_tool import CodedTool  # noqa: F401
except ImportError:
    from abc import ABC, abstractmethod

    class CodedTool(ABC):  # type: ignore[no-redef]
        """Minimal stub — real implementation provided by the neuro-san package."""

        @abstractmethod
        async def async_invoke(self, args: dict, sly_data: dict) -> dict: ...

    # Inject into sys.modules so `from neuro_san.interfaces.coded_tool import CodedTool` works
    import types
    _pkg  = types.ModuleType("neuro_san")
    _ifc  = types.ModuleType("neuro_san.interfaces")
    _ct   = types.ModuleType("neuro_san.interfaces.coded_tool")
    _ct.CodedTool = CodedTool
    _ifc.coded_tool = _ct
    _pkg.interfaces = _ifc
    sys.modules.setdefault("neuro_san",                    _pkg)
    sys.modules.setdefault("neuro_san.interfaces",         _ifc)
    sys.modules.setdefault("neuro_san.interfaces.coded_tool", _ct)
