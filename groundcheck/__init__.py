__version__ = "1.0.0"

from .checker import check  # noqa: E402
from .model import ClaimResult, Finding, Report, Severity  # noqa: E402

__all__ = ["check", "Report", "Finding", "ClaimResult", "Severity", "__version__"]
