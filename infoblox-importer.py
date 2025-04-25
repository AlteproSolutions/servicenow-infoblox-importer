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

# Get the absolute path of the script and load config.yaml from the same directory.
script_path = os.path.abspath(__file__)
script_dir = os.path.dirname(script_path)
config_path = os.path.join(script_dir, "config.yaml")
try:
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
except Exception as e:
    rprint(f"[red]Failed to load configuration from {config_path}: {e}[/red]")
    sys.exit(1)

# Read log settings from config
log_dir = config.get("LOG_DIR", "./")
log_level_str = config.get("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_str, logging.INFO)
log_file = os.path.join(log_dir, "infoblox-gpon-import.log")

# Set up logging with RichHandler for console output and a RotatingFileHandler for file logging.
logging.basicConfig(
    level=log_level,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        RichHandler(),
        RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=2)
    ]
)
logger = logging.getLogger("ServiceNowInfobloxSync")

# =====================================
# Configuration Validation
# =====================================
def validate_config(config):
    """ Validate required configuration keys and their values. """
    required_keys = [
        "INFOBLOX_API_ENDPOINT",
        "INFOBLOX_API_USERNAME",
        "INFOBLOX_API_PASSWORD",
        "SERVICENOW_API_USERNAME",
        "SERVICENOW_API_TOKEN",
        "SERVICENOW_API_ENDPOINT",
        "SERVICE_NOW_API_LIMIT"
    ]
    missing = [key for key in required_keys if not config.get(key)]
    if missing:
        logger.error("Missing required configuration keys: %s", missing)
        sys.exit(1)
    
    # Ensure that SERVICE_NOW_API_LIMIT is an integer
    try:
        int(config.get("SERVICE_NOW_API_LIMIT"))
    except Exception:
        logger.error("SERVICE_NOW_API_LIMIT must be an integer. Found: %s", config.get("SERVICE_NOW_API_LIMIT"))
        sys.exit(1)

validate_config(config)

# =====================================
# Global Settings from Config
# =====================================

# ServiceNow settings
SERVICENOW_API_ENDPOINT = config.get("SERVICENOW_API_ENDPOINT")
if not SERVICENOW_API_ENDPOINT.startswith("http"):
    SNOW_INSTANCE_URL = f"https://{SERVICENOW_API_ENDPOINT}"
else:
    SNOW_INSTANCE_URL = SERVICENOW_API_ENDPOINT
SNOW_API_USERNAME = config.get("SERVICENOW_API_USERNAME")
SNOW_API_TOKEN = config.get("SERVICENOW_API_TOKEN")
SNOW_CMN_LOCATION_ENDPOINT = f"/api/now/table/cmn_location?sysparm_query=cmn_location_typeINcountry,city,campus&sysparm_limit={config.get('SERVICE_NOW_API_LIMIT')}&sysparm_fields=name"

# Infoblox settings
INFOBLOX_API_ENDPOINT = config.get("INFOBLOX_API_ENDPOINT")
INFOBLOX_API_USERNAME = config.get("INFOBLOX_API_USERNAME")
INFOBLOX_API_PASSWORD = config.get("INFOBLOX_API_PASSWORD")
EXT_ATTR_NAME = "Location"  # Extensible attribute name

# SSL Verification flag (set to False for self-signed certs – not recommended in production)
VERIFY_SSL = False

# Maximum allowed length for enum values in Infoblox
ENUM_MAX_LENGTH = 64

# =====================================
# Helper Function to Sanitize Values
# =====================================
def sanitize_value(value):
    """
    Ensure the provided value does not exceed ENUM_MAX_LENGTH.
    If it does, truncate and log a warning.
    """
    if len(value) > ENUM_MAX_LENGTH:
        logger.warning("Value '%s' exceeds %d characters and will be truncated.", value, ENUM_MAX_LENGTH)
        return value[:ENUM_MAX_LENGTH]
    return value

# =====================================
# Infoblox Functions with Duplicate Logging
# =====================================
def get_infoblox_ea_definition(ea_name):
    """
    Retrieves the Infoblox Extensible Attribute definition by name.
    Returns a tuple (ea_def, ea_ref).
    """
    url = f"{INFOBLOX_API_ENDPOINT}/extensibleattributedef?name={ea_name}&_return_fields=list_values"
    logger.info("Fetching Infoblox EA definition for '%s': %s", ea_name, url)
    try:
        response = requests.get(url, auth=(INFOBLOX_API_USERNAME, INFOBLOX_API_PASSWORD),
                                verify=VERIFY_SSL, timeout=30)
    except Exception as e:
        logger.error("Exception during Infoblox EA GET request: %s", str(e))
        sys.exit(1)
    if response.status_code != 200:
        logger.error("Infoblox API GET failed for EA '%s'. Status: %s, Response: %s",
                     ea_name, response.status_code, response.text)
        sys.exit(1)
    try:
        data = response.json()
    except Exception as e:
        logger.error("Error parsing Infoblox JSON: %s", str(e))
        sys.exit(1)
    if not data:
        logger.error("EA '%s' not found in Infoblox.", ea_name)
        sys.exit(1)
    ea_def = data[0]
    ea_ref = ea_def.get("_ref")
    logger.info("Obtained EA definition with reference: %s", ea_ref)
    return ea_def, ea_ref

def update_infoblox_ea_values(ea_ref, new_values):
    """
    Updates the Infoblox EA's allowed values (list_values) with new_values.
    Logs duplicate sanitized values.
    """
    url = f"{INFOBLOX_API_ENDPOINT}/{ea_ref}"
    
    # Create a mapping from sanitized value to list of original values.
    sanitized_mapping = {}
    for value in new_values:
        sanitized = sanitize_value(value)
        sanitized_mapping.setdefault(sanitized, []).append(value)
    
    # Log duplicates: if a sanitized value has more than one original value.
    for sanitized, originals in sanitized_mapping.items():
        if len(originals) > 1:
            logger.warning("Duplicate sanitized value '%s' from original values: %s", sanitized, originals)
    
    sanitized_values = sorted(sanitized_mapping.keys())
    # split each location string into its components, then sort by (country, city, campus)
        
    payload = {
        "list_values": [{"value": value} for value in sanitized_values]
    }
    logger.info("Updating Infoblox EA values with payload: %s", json.dumps(payload))
    try:
        response = requests.put(url, auth=(INFOBLOX_API_USERNAME, INFOBLOX_API_PASSWORD),
                                json=payload, verify=VERIFY_SSL, timeout=30)
    except Exception as e:
        logger.error("Exception during Infoblox EA update: %s", str(e))
        sys.exit(1)
    if response.status_code not in [200, 201]:
        logger.error("Infoblox EA update failed. Status: %s, Response: %s",
                     response.status_code, response.text)
        sys.exit(1)
    logger.info("Infoblox EA update successful.")

# =====================================
# ServiceNow Functions
# =====================================
def get_snow_locations():
    """
    Fetches location names from ServiceNow.
    Returns a set of names.
    """
    url = SNOW_INSTANCE_URL + SNOW_CMN_LOCATION_ENDPOINT
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    # Nastavení proxy pouze pokud je definována v configu
    servicenow_proxy = config.get("SERVICENOW_PROXY")
    proxies = None
    if servicenow_proxy:
        proxies = {
            "http": servicenow_proxy,
            "https": servicenow_proxy
        }
        logger.info("Using proxy for ServiceNow connection: %s", servicenow_proxy)
    else:
        logger.info("No proxy defined for ServiceNow connection, connecting directly.")

    logger.info("Fetching locations from ServiceNow: %s", url)
    try:
        response = requests.get(
            url,
            auth=(SNOW_API_USERNAME, SNOW_API_TOKEN),
            headers=headers,
            verify=VERIFY_SSL,
            timeout=30,
            proxies=proxies  # None pokud není proxy
        )
    except Exception as e:
        logger.error("Exception during ServiceNow API request: %s", str(e))
        sys.exit(1)

    if response.status_code != 200:
        logger.error("ServiceNow API error. Status: %s, Response: %s", response.status_code, response.text)
        sys.exit(1)

    try:
        data = response.json()
    except Exception as e:
        logger.error("Error parsing ServiceNow JSON: %s", str(e))
        sys.exit(1)

    results = data.get("result", [])
    locations = {item["name"].strip() for item in results if "name" in item and item["name"]}
    logger.info("Fetched %d locations from ServiceNow.", len(locations))
    return locations

# =====================================
# Main Synchronization Logic
# =====================================
def main():
    logger.info("Starting ServiceNow -> Infoblox synchronization for EA '%s'", EXT_ATTR_NAME)
    
    # Retrieve locations from ServiceNow
    snow_locations = get_snow_locations()
    
    # Retrieve the current EA definition from Infoblox
    ea_def, ea_ref = get_infoblox_ea_definition(EXT_ATTR_NAME)
    current_list = ea_def.get("list_values", [])
    current_values = {entry["value"] for entry in current_list if "value" in entry}
    logger.info("Current Infoblox EA '%s' allowed values: %s", EXT_ATTR_NAME, current_values)
    
    # Determine new allowed values based solely on ServiceNow data
    # split each location string into its components, then sort by (country, city, campus)
    new_values = sorted(snow_locations, key=lambda loc: tuple(loc.split("/")))
    logger.info("ServiceNow provided %d allowed values: %s", len(new_values), new_values)
    
    # Update Infoblox if values differ
    if new_values == current_values:
        logger.info("No changes required. Infoblox EA allowed values are up-to-date.")
    else:
        logger.info("Updating Infoblox EA allowed values to match ServiceNow data.")
        update_infoblox_ea_values(ea_ref, new_values)
        
        # Verify the update
        ea_def_after, _ = get_infoblox_ea_definition(EXT_ATTR_NAME)
        updated_list = ea_def_after.get("list_values", [])
        updated_values = {entry["value"] for entry in updated_list if "value" in entry}
        logger.info("After update, Infoblox EA '%s' allowed values: %s", EXT_ATTR_NAME, updated_values)
    
    logger.info("Synchronization completed successfully.")

# =====================================
# Entry Point
# =====================================
if __name__ == "__main__":
    main()
