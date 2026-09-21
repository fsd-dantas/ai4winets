"""ECoRA contract foundation; no network simulator or decision method is implemented."""

from .contracts import ContractError, Record

__all__ = ["ContractError", "Record"]
__version__ = "0.1.0"
