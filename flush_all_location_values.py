#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import logging
import requests
import yaml
from logging.handlers import RotatingFileHandler
from rich.logging import RichHandler
from rich import print as rprint  # use rich.print for beautiful console output

# =====================================
# Configuration and Logging Setup
# =====================================

# Determine paths
script_path = os.path.abspath(__file__)
script_dir  = os.path.dirname(script_path)
config_path = os.path.join(script_dir, "config.yaml")

# Load config.yaml
try:
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
except Exception as e:
    rprint(f"[red]Failed to load configuration from {config_path}: {e}[/red]")
    sys.exit(1)

# Validate required Infoblox settings
required = ["INFOBLOX_API_ENDPOINT", "INFOBLOX_API_USERNAME", "INFOBLOX_API_PASSWORD"]
missing = [k for k in required if not config.get(k)]
if missing:
    rprint(f"[red]Missing required configuration keys: {missing}[/red]")
    sys.exit(1)

# Logging settings
log_dir       = config.get("LOG_DIR", "./")
log_level_str = config.get("LOG_LEVEL", "INFO").upper()
log_level     = getattr(logging, log_level_str, logging.INFO)
log_file      = os.path.join(log_dir, "flush-infoblox.log")

logging.basicConfig(
    level=log_level,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        RichHandler(),
        RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=2),
    ]
)
logger = logging.getLogger("ServiceNowInfobloxSyncFlush")

# =====================================
# Global Settings from Config
# =====================================

INFOBLOX_API_ENDPOINT = config["INFOBLOX_API_ENDPOINT"].rstrip("/")
INFOBLOX_API_USERNAME = config["INFOBLOX_API_USERNAME"]
INFOBLOX_API_PASSWORD = config["INFOBLOX_API_PASSWORD"]
VERIFY_SSL            = False   # match your importer
EXT_ATTR_NAME         = "Location"

# =====================================
# Proxy Setup (reuse SERVICENOW_PROXY key)
# =====================================

servicenow_proxy = config.get("SERVICENOW_PROXY")
if servicenow_proxy:
    proxies = {"http": servicenow_proxy, "https": servicenow_proxy}
    logger.info("Using proxy for Infoblox connection: %s", servicenow_proxy)
else:
    proxies = None
    logger.info("No proxy defined for Infoblox connection, connecting directly.")

# =====================================
# Helpers
# =====================================

def sanitize_value(value, max_len=64):
    if len(value) > max_len:
        logger.warning("Value '%s' exceeds %d chars, truncating.", value, max_len)
        return value[:max_len]
    return value

# =====================================
# Infoblox API Functions
# =====================================

def get_infoblox_ea_definition(ea_name):
    """
    Fetch the EA definition (including list_values) for the given name.
    """
    url = f"{INFOBLOX_API_ENDPOINT}/extensibleattributedef"
    params = {"name": ea_name, "_return_fields": "list_values"}
    logger.info("GET EA definition '%s' -> %s", ea_name, url)
    try:
        resp = requests.get(
            url,
            params=params,
            auth=(INFOBLOX_API_USERNAME, INFOBLOX_API_PASSWORD),
            verify=VERIFY_SSL,
            timeout=30,
            proxies=proxies
        )
    except Exception as e:
        logger.error("Error fetching EA definition: %s", e)
        sys.exit(1)

    if resp.status_code != 200:
        logger.error("GET EA failed (%s): %s", resp.status_code, resp.text)
        sys.exit(1)

    try:
        data = resp.json()
    except Exception as e:
        logger.error("Invalid JSON from Infoblox: %s", e)
        sys.exit(1)

    if not data:
        logger.error("EA '%s' not found.", ea_name)
        sys.exit(1)

    ea_def = data[0]
    ea_ref = ea_def.get("_ref")
    logger.info("Found EA _ref=%s with %d values",
                ea_ref, len(ea_def.get("list_values", [])))
    return ea_def, ea_ref

def update_infoblox_ea_values(ea_ref):
    """
    Flush all list_values by setting a single dummy 'CLEARED' entry.
    """
    url = f"{INFOBLOX_API_ENDPOINT}/{ea_ref}"
    payload = {"list_values": [{"value": "CLEARED"}]}
    logger.info("PUT flush EA at %s  payload=%s", url, json.dumps(payload))

    try:
        resp = requests.put(
            url,
            auth=(INFOBLOX_API_USERNAME, INFOBLOX_API_PASSWORD),
            json=payload,
            verify=VERIFY_SSL,
            timeout=30,
            proxies=proxies
        )
    except Exception as e:
        logger.error("Error flushing EA values: %s", e)
        sys.exit(1)

    if resp.status_code not in (200, 201):
        logger.error("Flush failed (%s): %s", resp.status_code, resp.text)
        sys.exit(1)

    logger.info("Flush successful—EA now has zero allowed values.")

# =====================================
# Main
# =====================================

if __name__ == "__main__":
    logger.info("Starting one-time flush of EA '%s'", EXT_ATTR_NAME)
    _, ea_ref = get_infoblox_ea_definition(EXT_ATTR_NAME)
    update_infoblox_ea_values(ea_ref)
    rprint(f"[green]Done: all list_values for EA '{EXT_ATTR_NAME}' have been cleared.[/green]")
