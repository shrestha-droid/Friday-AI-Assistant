import contextvars
import logging
from logging.handlers import RotatingFileHandler

from . import config

request_id = contextvars.ContextVar("request_id", default="SYSTEM")


class _RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id.get()
        return True


def setup():
    config.ROOT.joinpath("logs").mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] [%(request_id)s] %(message)s")
    handlers = [
        RotatingFileHandler(config.ROOT / "logs" / "friday.log", maxBytes=1_000_000, backupCount=3),
        logging.StreamHandler(),
    ]
    root = logging.getLogger()
    root.handlers.clear()
    for h in handlers:
        h.setFormatter(fmt)
        h.addFilter(_RequestIdFilter())
        root.addHandler(h)
    root.setLevel(logging.DEBUG if config.DEBUG else logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
