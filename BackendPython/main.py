"""Vercel entry point (the root vercel.json builds this file). The application lives in app/."""
import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

import _socket
import socket

# In serverless environments (e.g. AWS Lambda / Vercel), dual-stack AF_UNSPEC lookups
# can raise OSError [Errno 16] Device or resource busy when IPv6 is unavailable.
# Fallback to AF_INET so IPv4 address resolution succeeds.
_orig_c_gai = _socket.getaddrinfo

def _safe_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    flags = flags & ~getattr(socket, "AI_ADDRCONFIG", 0)
    if family == 0 or family == socket.AF_UNSPEC:
        family = socket.AF_INET
    try:
        return _orig_c_gai(host, port, family, type, proto, flags)
    except OSError:
        return _orig_c_gai(host, port, socket.AF_INET, socket.SOCK_STREAM, 0, 0)

socket.getaddrinfo = _safe_getaddrinfo
_socket.getaddrinfo = _safe_getaddrinfo

from app.main import app

__all__ = ["app"]

