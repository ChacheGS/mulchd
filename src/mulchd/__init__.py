from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("mulchd")
except PackageNotFoundError:
    __version__ = "0.0.0"
