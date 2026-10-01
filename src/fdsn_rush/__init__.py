from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("fdsn-rush")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "unknown"
