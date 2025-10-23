from dataclasses import dataclass
from typing import Optional, Any

@dataclass
class Context:
    request: Optional[Any] = None

    @property
    def user(self):
        return getattr(self.request, "user", None)
