import logging
import os

DEFAULT_DB_PATH = os.path.join(os.path.expanduser("~"), ".mediavault", "media_data.json")


def setup_logging():
    """Konfiguriert das Root-Logging einmalig mit Zeitstempel und Level."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
