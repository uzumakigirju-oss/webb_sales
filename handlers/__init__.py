from .common import router as common_router
from .shifts import router as shift_router
from .sales import router as sales_router
from .stats import router as stats_router
from .files import router as files_router

__all__ = [
    "common_router",
    "shift_router",
    "sales_router",
    "stats_router",
    "files_router",
]
