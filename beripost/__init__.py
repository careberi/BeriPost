"""BeriPost - an autonomous Facebook content engine for Careberi."""

# Use the operating system's certificate store for HTTPS. This fixes SSL
# "certificate verify failed" errors on networks (antivirus, corporate proxies)
# that intercept traffic with their own trusted certificate. Safe no-op if the
# library is unavailable.
try:  # noqa: SIM105
    import truststore

    truststore.inject_into_ssl()
except Exception:  # noqa: BLE001
    pass

__version__ = "0.1.0"
