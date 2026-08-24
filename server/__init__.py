"""Transport layer.

Two interchangeable front ends sit on top of the same route table:
  * LocalServer - stdlib HTTP + SSE, used for browser / development mode.
  * Bridge      - pywebview js_api, used by the packaged desktop app because
                  it needs no listening socket.
"""

from .api import Api
from .bridge import Bridge
from .http_server import LocalServer

__all__ = ["Api", "Bridge", "LocalServer"]
