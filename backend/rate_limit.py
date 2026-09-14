"""
backend/rate_limit.py
Shared slowapi Limiter instance.

Defined here (instead of backend/main.py) so routers can apply per-route
limits without creating a circular import: main imports routers, routers
import this module. main.py attaches this same instance to the app.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])
