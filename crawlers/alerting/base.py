"""
Base class for alerting plugins.
"""

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class BaseAlertingPlugin(ABC):
    """
    Abstract base class for alerting plugins.
    Plugins should inherit from this and implement the send_alert method.
    """

    def __init__(self, config=None):
        self.config = config or {}
        self.name = self.config.get('name', self.__class__.__name__)

    @abstractmethod
    def send_alert(self, finding):
        """
        Send an alert for the given finding.
        """
        raise NotImplementedError("Subclasses must implement the send_alert method")