"""
Custom Exceptions for PlanCraft
"""

class PlanCraftError(Exception):
    """Base exception for PlanCraft application."""
    pass

class LLMGenerationError(PlanCraftError):
    """Raised when LLM API call fails or refusal occurs."""
    pass

class ParsingError(PlanCraftError):
    """Raised when AI output cannot be parsed into desired JSON structure."""
    pass

class ResourceError(PlanCraftError):
    """Raised when external resources (Search, DB, Tools) are unavailable or fail."""
    pass
