"""
PlanCraft Agents Package

기존 파이프라인 에이전트:
    - analyzer, structurer, writer, reviewer, refiner, formatter

Multi-Agent 확장:
    - supervisor: 전문 에이전트 오케스트레이터
    - specialists: 전문 에이전트 패키지
        - MarketAgent, BMAgent, FinancialAgent, RiskAgent

Note: 순환 import 방지를 위해 lazy import 사용
"""

from typing import TYPE_CHECKING

# Type checking 시에만 import (IDE 지원용)
if TYPE_CHECKING:
    from agents import analyzer as _analyzer
    from agents import structurer as _structurer
    from agents import writer as _writer
    from agents import reviewer as _reviewer
    from agents import refiner as _refiner
    from agents import formatter as _formatter
    from agents.supervisor import PlanSupervisor as _PlanSupervisor
    from agents.specialists import (
        MarketAgent as _MarketAgent,
        BMAgent as _BMAgent,
        FinancialAgent as _FinancialAgent,
        RiskAgent as _RiskAgent,
    )


__all__ = [
    # Core Agents
    "analyzer",
    "structurer",
    "writer",
    "reviewer",
    "refiner",
    "formatter",

    # Supervisor
    "PlanSupervisor",

    # Specialists
    "MarketAgent",
    "BMAgent",
    "FinancialAgent",
    "RiskAgent",
]


# Module cache to avoid repeated imports
_module_cache = {}


def __getattr__(name: str):
    """Lazy import for avoiding circular imports"""
    global _module_cache

    if name in _module_cache:
        return _module_cache[name]

    import importlib

    if name in ("analyzer", "structurer", "writer", "reviewer", "refiner", "formatter"):
        module = importlib.import_module(f"agents.{name}")
        _module_cache[name] = module
        return module
    elif name == "PlanSupervisor":
        from agents.supervisor import PlanSupervisor
        _module_cache[name] = PlanSupervisor
        return PlanSupervisor
    elif name == "MarketAgent":
        from agents.specialists import MarketAgent
        _module_cache[name] = MarketAgent
        return MarketAgent
    elif name == "BMAgent":
        from agents.specialists import BMAgent
        _module_cache[name] = BMAgent
        return BMAgent
    elif name == "FinancialAgent":
        from agents.specialists import FinancialAgent
        _module_cache[name] = FinancialAgent
        return FinancialAgent
    elif name == "RiskAgent":
        from agents.specialists import RiskAgent
        _module_cache[name] = RiskAgent
        return RiskAgent

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
