"""base class every model adapter inherits from to keep outputs in the same format"""

from abc import ABC, abstractmethod


class BaseModelAdapter(ABC):

    @abstractmethod
    def load_model(self):
        pass

    @abstractmethod
    def run(self, bgr_frame):
        pass

    def get_name(self):
        return self.__class__.__name__
