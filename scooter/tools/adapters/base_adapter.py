"""abstract interface every model adapter has to implement"""

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
