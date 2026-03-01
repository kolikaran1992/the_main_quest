# Project Overview

This project is an auto-initialized Python template managed by Poetry.
It provides a clean structure for configuration management using Dynaconf, along with support libraries like Jinja2 and pytz.

## 📁 Project Structure

```
project_root/
│
├── pyproject.toml # Poetry configuration & dependencies
├── README.md # Project documentation
│
├── the_main_quest/ # Main Python package
│ ├── init.py
│ ├── agent.md # instructions for agents to augment the project
│ ├── omniconf.py # Base configuration loader using Dynaconf
│ └── settings_file/ # Dynaconf settings directory
│     └── settings.toml # Default configuration
│
└── tests/ # Unit tests directory
```

## ✅ What Each File Does

### `the_main_quest/omniconf.py`
- Central config loader for the entire project
- Loads `settings.toml`
- Injects useful Jinja variables (`now`, timezone helpers)
- Sets base paths and timestamp values
- ✅ Initializes a global logger available across the project

To log messages:

```python
from the_main_quest.omniconf import logger
logger.info("This is a log message")
```

### `the_main_quest/settings_file/settings.toml`
- Contains default configuration values
- Uses Jinja2 templating inside Dynaconf
- Includes `logger_name` which is set to the project root name

Example:
```
[default]
now_iso = "@jinja {{this._get_now_iso(this.tz)}}"
start_ts = "@jinja {{this._get_start_ts(this.tz)}}"
tz = "Asia/Kolkata"
logger_name = "the_main_quest"
base_data_path = "@jinja {{this.home_dir}}/Data/THE_MAIN_QUEST"
```

If an AI agent needs to modify configuration behavior, it should edit:
- `the_main_quest/omniconf.py` for logic or environment variable handling
- `the_main_quest/settings_file/settings.toml` for changing configuration defaults

## 🔧 Extending the Project
- Add new settings in `the_main_quest/settings_file/settings.toml`
- Add new Python modules inside `the_main_quest/`
- Add tests inside `tests/`

---

## 🧾 Optional Loki Logging

Loki logging is **disabled by default**.

To enable Loki logging, call:

```python
from the_main_quest.omniconf import add_loki_handler
add_loki_handler()
```

### ✅ Without suffix

```python
add_loki_handler()
```

- Job name becomes: `the_main_quest`
- File created:
  `<base_data_path>/logs/loki_the_main_quest.log`

### ✅ With suffix

```python
add_loki_handler("ingestion")
```

- Job name becomes:
  ``
- File created:
  `<base_data_path>/logs/loki_.log`

### 📂 Log Location

Log files are written to:

```
{{base_data_path}}/logs/
```

The base path is controlled by:

```
loki_log_path
```

inside `settings.toml`.

The console logger remains unchanged.
