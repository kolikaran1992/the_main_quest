#!/usr/bin/env bash
set -e

# -----------------------------------------
# Auto-initialize a Python project using Poetry
# Author: kolikaran
# -----------------------------------------

# STEP 0 — Get project name from current folder
PROJECT_NAME=$(basename "$PWD")
ENV_PREFIX=$(echo "$PROJECT_NAME" | tr '[:lower:]' '[:upper:]')
echo "Initializing project: $PROJECT_NAME (ENV prefix: $ENV_PREFIX)"

# STEP 1 — Initialize Poetry project
echo "Running poetry init..."
poetry init --name "$PROJECT_NAME" --author "kolikaran" --python ">=3.10,<3.15" --no-interaction

# STEP 2 — Create basic structure
echo "Creating $PROJECT_NAME and tests..."
mkdir -p "$PROJECT_NAME"
mkdir -p "tests"
touch "$PROJECT_NAME/__init__.py"

# STEP 3 — Create README.md
echo "Creating README.md..."
cat <<EOF > README.md
# $PROJECT_NAME

Generated Python project managed by Poetry.
EOF

# STEP 4 — Install dependencies
echo "Installing main dependencies..."
poetry add dynaconf jinja2 pytz
poetry add python-json-logger

echo "Installing development tools (pytest, black, isort, ipykernel, ipywidgets)..."

poetry add --group dev pytest
poetry add --group dev black
poetry add --group dev isort
poetry add --group dev ipykernel
poetry add --group dev ipywidgets


# STEP 5 — Create omniconf.py inside the project folder
echo "Creating $PROJECT_NAME/omniconf.py..."
cat <<EOF > "$PROJECT_NAME/omniconf.py"
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
    path.as_posix() for path in _BASE_DIR.joinpath('settings_file').glob("*.toml") if path.stem != "settings"
]

config = Dynaconf(
    preload=[_BASE_DIR.joinpath("settings_file", "settings.toml").as_posix()],
    settings_files=settings_files,
    secrets=[] if not secrets_dir else list(Path(secrets_dir).glob("*.toml")),
    environments=True,
    envvar_prefix="${ENV_PREFIX}",
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
        if isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) == final_path:
            return

    file_handler = logging.FileHandler(final_path)
    file_handler.setLevel(logger.level)

    json_formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )

    file_handler.setFormatter(json_formatter)
    logger.addHandler(file_handler)
EOF

# STEP 6 — Create settings_file inside project directory
echo "Creating $PROJECT_NAME/settings_file/settings.toml..."
mkdir -p "$PROJECT_NAME/settings_file"
cat <<EOF > "$PROJECT_NAME/settings_file/settings.toml"
[default]
now_iso = "@jinja {{this._get_now_iso(this.tz)}}"
start_ts = "@jinja {{this._get_start_ts(this.tz)}}"
tz = "Asia/Kolkata"
logger_name = "$PROJECT_NAME"
base_data_path = "@jinja {{this.home_dir}}/Data/$ENV_PREFIX"
loki_log_path = "@jinja {{this.base_data_path}}/logs/loki_${PROJECT_NAME}.log"
EOF


# STEP 7 — Create agent.md inside project directory
echo "Creating $PROJECT_NAME/agent.md..."
cat <<EOF > "$PROJECT_NAME/agent.md"
# Project Overview

This project is an auto-initialized Python template managed by Poetry.
It provides a clean structure for configuration management using Dynaconf, along with support libraries like Jinja2 and pytz.

## 📁 Project Structure

\`\`\`
project_root/
│
├── pyproject.toml # Poetry configuration & dependencies
├── README.md # Project documentation
│
├── $PROJECT_NAME/ # Main Python package
│ ├── init.py
│ ├── agent.md # instructions for agents to augment the project
│ ├── omniconf.py # Base configuration loader using Dynaconf
│ └── settings_file/ # Dynaconf settings directory
│     └── settings.toml # Default configuration
│
└── tests/ # Unit tests directory
\`\`\`

## ✅ What Each File Does

### \`$PROJECT_NAME/omniconf.py\`
- Central config loader for the entire project
- Loads \`settings.toml\`
- Injects useful Jinja variables (\`now\`, timezone helpers)
- Sets base paths and timestamp values
- ✅ Initializes a global logger available across the project

To log messages:

\`\`\`python
from $PROJECT_NAME.omniconf import logger
logger.info("This is a log message")
\`\`\`

### \`$PROJECT_NAME/settings_file/settings.toml\`
- Contains default configuration values
- Uses Jinja2 templating inside Dynaconf
- Includes \`logger_name\` which is set to the project root name

Example:
\`\`\`
[default]
now_iso = "@jinja {{this._get_now_iso(this.tz)}}"
start_ts = "@jinja {{this._get_start_ts(this.tz)}}"
tz = "Asia/Kolkata"
logger_name = "$PROJECT_NAME"
base_data_path = "@jinja {{this.home_dir}}/Data/$ENV_PREFIX"
\`\`\`

If an AI agent needs to modify configuration behavior, it should edit:
- \`$PROJECT_NAME/omniconf.py\` for logic or environment variable handling
- \`$PROJECT_NAME/settings_file/settings.toml\` for changing configuration defaults

## 🔧 Extending the Project
- Add new settings in \`$PROJECT_NAME/settings_file/settings.toml\`
- Add new Python modules inside \`$PROJECT_NAME/\`
- Add tests inside \`tests/\`

---

## 🧾 Optional Loki Logging

Loki logging is **disabled by default**.

To enable Loki logging, call:

\`\`\`python
from $PROJECT_NAME.omniconf import add_loki_handler
add_loki_handler()
\`\`\`

### ✅ Without suffix

\`\`\`python
add_loki_handler()
\`\`\`

- Job name becomes: \`$PROJECT_NAME\`
- File created:
  \`<base_data_path>/logs/loki_$PROJECT_NAME.log\`

### ✅ With suffix

\`\`\`python
add_loki_handler("ingestion")
\`\`\`

- Job name becomes:
  \`$PROJECT_NAME__ingestion\`
- File created:
  \`<base_data_path>/logs/loki_$PROJECT_NAME__ingestion.log\`

### 📂 Log Location

Log files are written to:

\`\`\`
{{base_data_path}}/logs/
\`\`\`

The base path is controlled by:

\`\`\`
loki_log_path
\`\`\`

inside \`settings.toml\`.

The console logger remains unchanged.
EOF


echo
echo "✅ Project initialized successfully!"
echo "Files generated:"
echo "- pyproject.toml"
echo "- README.md"
echo "- $PROJECT_NAME/__init__.py"
echo "- $PROJECT_NAME/omniconf.py"
echo "- $PROJECT_NAME/settings_file/settings.toml"
echo "- agent.md"