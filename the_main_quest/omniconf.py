from pathlib import Path
from datetime import datetime
import os
import pytz
import logging
from dynaconf import Dynaconf


_NOW = datetime.now()
_BASE_DIR = Path(__file__).resolve().parent


def _get_start_ts(tz: str) -> datetime:
    return _NOW.astimezone(pytz.timezone(tz))


def _get_now_iso(tz: str) -> str:
    return datetime.now().astimezone(pytz.timezone(tz)).isoformat()


def _get_now_ts(tz: str) -> str:
    return datetime.now().astimezone(pytz.timezone(tz))


###################
# Create Settings #
###################
secrets_dir = os.environ.get("SECRETS_DIRECTORY") or ""

# Automatically detect .toml config files (excluding settings.toml)
settings_files = [
    path.as_posix()
    for path in _BASE_DIR.joinpath("settings_file").glob("*.toml")
    if path.stem != "settings"
]

config = Dynaconf(
    preload=[_BASE_DIR.joinpath("settings_file", "settings.toml").as_posix()],
    settings_files=settings_files,
    secrets=[] if not secrets_dir else list(Path(secrets_dir).glob("*.toml")),
    environments=True,
    envvar_prefix="THE_MAIN_QUEST",
    load_dotenv=True,
    _get_now_ts=_get_now_ts,
    _get_now_iso=_get_now_iso,
    _get_start_ts=_get_start_ts,
    now=_NOW,
    partition_date=_NOW.strftime("%Y/%m/%d"),
    root_dir=_BASE_DIR.as_posix(),
    home_dir=Path.home().as_posix(),
    merge_enabled=True,
)


#########################
# Logger Initialization #
#########################
class DefaultFormatter(logging.Formatter):
    def __init__(self, fmt=None, datefmt=None):
        super().__init__(fmt=fmt, datefmt=datefmt)

    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, pytz.timezone(config.get("tz")))
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()

    def format(self, record):
        record.full_path = record.pathname
        return super().format(record)


logger = logging.getLogger(config.logger_name)
logger.setLevel(logging.INFO)

fmt = "[%(asctime)s] %(levelname)s [%(full_path)s]: %(message)s"
formatter = DefaultFormatter(fmt=fmt)

stream_handler = logging.StreamHandler()
stream_handler.setLevel(logger.level)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)


#########################
# Optional Loki Handler #
#########################
def add_loki_handler(suffix: str | None = None):
    """
    Attach a JSON FileHandler for Loki ingestion.
    Loki is NOT enabled by default.
    """

    from pythonjsonlogger import jsonlogger

    project_name = config.logger_name

    if suffix:
        job = f"{project_name}__{suffix}"
        filename = f"loki_{project_name}__{suffix}.log"
    else:
        job = f"{project_name}"
        filename = f"loki_{project_name}.log"

    base_path = Path(config.loki_log_path)
    log_dir = base_path.parent
    log_dir.mkdir(parents=True, exist_ok=True)

    final_path = log_dir / filename

    # Prevent duplicate Loki handlers
    for handler in logger.handlers:
        if (
            isinstance(handler, logging.FileHandler)
            and Path(handler.baseFilename) == final_path
        ):
            return

    file_handler = logging.FileHandler(final_path)
    file_handler.setLevel(logger.level)

    json_formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )

    file_handler.setFormatter(json_formatter)
    logger.addHandler(file_handler)
