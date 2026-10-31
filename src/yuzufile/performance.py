"""Resource budgets independent of recognition and compression quality."""
from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Performance:
    code: str
    title: str
    hint: str
    workers: int
    cpu_percent: int
    memory_mb: int

    def page_workers(self) -> int:
        # Leave headroom on small computers as well as enforcing the preset cap.
        return min(self.workers, max(1, (os.cpu_count() or 2) // 2))

    def environment(self) -> dict[str, str]:
        threads = str(self.page_workers())
        return {"OMP_NUM_THREADS": threads, "OPENBLAS_NUM_THREADS": threads,
                "MKL_NUM_THREADS": threads, "NUMEXPR_NUM_THREADS": threads,
                "OMP_THREAD_LIMIT": threads}


PROFILES = {
    "low": Performance("low", "Low usage", "Lighter on your computer; takes longer", 1, 25, 2048),
    "balanced": Performance("balanced", "Balanced", "A balance of speed and resource use", 2, 50, 3072),
    "high": Performance("high", "High performance", "More resources for faster processing", 4, 85, 4096),
}


def performance_profile(code: str = "balanced") -> Performance:
    try:
        return PROFILES[code]
    except (KeyError, TypeError):
        raise ValueError("Choose a valid performance level.") from None
