
# Infoblox GPON EA Importer from ServiceNow

This script synchronizes location data from **ServiceNow** into an **Infoblox Extensible Attribute (EA)**. It's designed to update the allowed values of the "Location" EA in Infoblox based on `cmn_location` entries from ServiceNow, using secure API requests.

## 🧰 Features

- Pulls `cmn_location` records from ServiceNow using REST API.
- Retrieves and updates allowed values in a specific Infoblox Extensible Attribute (EA).
- Automatically sanitizes values to respect Infoblox enum length limits.
- Logs activity to both console and a rotating file.
- Detects and logs sanitized duplicates.

---

## 📦 Requirements

- Python 3.6+
- External Python libraries:
  - `requests`
  - `pyyaml`
  - `rich`

Install dependencies with:

```bash
pip install -r requirements.txt
```

> Example `requirements.txt`:

```bash
requests
pyyaml
rich
```

---

## ⚙️ Configuration

Create a file called `config.yaml` in the same directory as the script:

```yaml
---
# Logging
LOG_DIR: "./"
LOG_LEVEL: INFO  # Options: DEBUG, INFO, WARNING, ERROR, CRITICAL

# Infoblox settings
INFOBLOX_API_ENDPOINT: "https://infoblox.local/wapi/v2.12"
INFOBLOX_API_USERNAME: "admin"
INFOBLOX_API_PASSWORD: "your-infoblox-password"

# ServiceNow settings
SERVICENOW_API_USERNAME: "admin"
SERVICENOW_API_TOKEN: "your-servicenow-api-token"
SERVICENOW_API_ENDPOINT: "https://servicenow.com"
SERVICE_NOW_API_LIMIT: 10000

# Proxy settings (if needed)
SERVICENOW_PROXY: "http://proxy.local:8080" # Leave empty if not using proxy
```

> ⚠️ Make sure your Infoblox and ServiceNow credentials are properly secured. Avoid committing secrets to version control.

---

## 🚀 Running the Script

```bash
python3 infoblox_gpon_import.py
```

On execution, the script will:

1. Load and validate configuration from `config.yaml`.
2. Fetch locations from ServiceNow's `cmn_location` table.
3. Retrieve the current "Location" EA from Infoblox.
4. Compare values and update Infoblox if needed.
5. Log the entire operation.

---

## 📄 Log Files

Logs are written to:

```bash
<LOG_DIR>/infoblox-gpon-import.log
```

Console output uses [Rich](https://github.com/Textualize/rich) for better readability.

---

## 🧪 Key Functions

### `get_snow_locations()`

Fetches and returns a set of location names from ServiceNow's `cmn_location` table.

### `get_infoblox_ea_definition(ea_name)`

Fetches the current EA definition (name and reference) from Infoblox.

### `update_infoblox_ea_values(ea_ref, new_values)`

Updates the list of allowed values in Infoblox's EA with the sanitized ServiceNow values.

### `sanitize_value(value)`

Ensures strings don't exceed Infoblox's enum length limit (`64` characters).

---

## ⏰ Scheduling the Script with Cron

You can run the infoblox_gpon_import.py script automatically on a regular schedule using Cron on Unix/Linux systems. Follow these steps to set up the Cron job:

1. Verify Your Environment
    Python & Dependencies:
    Ensure that Python 3.6+ and all required libraries are installed.
    If you’re using a virtual environment, make sure to reference the full path to your environment's Python executable.

    Absolute Paths:
    Cron jobs use a limited environment, so always use absolute paths for both the Python interpreter and the script.

2. (Optional) Make the Script Executable
    If you prefer running the script directly (without prefixing with python3), add a shebang at the top of your script:

    ```python
    #!/usr/bin/env python3
    ```

    Then, change its permissions to make it executable:

    ```bash
    chmod +x /path/to/infoblox_gpon_import.py
    ```

3. Open the Crontab Editor
    To add a new cron job, open your crontab configuration file using:

    ```bash
    crontab -e
    ```

4. Add the Cron Job
    Add a line in the editor with your desired schedule. For example, to run the script every day at 2:00 AM, you can add:

    ```bash
    0 2 * * * /usr/bin/python3 /path/to/infoblox_gpon_import.py >> /var/log/infoblox-gpon-import.log 2>&1
    ```

    Explanation of the Cron Fields:

    0: Minute (0th minute of the hour)

    2: Hour (2 AM)

    *: Every day of the month

    *: Every month

    *: Every day of the week

    If you are using a virtual environment, ensure that you use the Python interpreter from that environment:

    ```bash
    0 2 * * * /path/to/venv/bin/python /path/to/infoblox_gpon_import.py >> /var/log/infoblox-gpon-import.log 2>&1
    ```

5. Save and Exit
    After adding your cron entry, save the file and exit the editor. Cron will automatically pick up the changes, and your script will run at the scheduled times.

6. Verify the Cron Job
    You can verify your cron jobs by listing them:

    ```bash
    crontab -l
    ```

---

## 🛡️ Notes on Security

- SSL verification is **disabled by default** (`VERIFY_SSL = False`) to allow self-signed certificates. You should enable verification in production environments.
- Ensure credentials and tokens are stored securely and not hard-coded or exposed in public repositories.

---

## ✅ Example Output

```bash
[INFO] Fetching locations from ServiceNow: https://servicenow.com/api/now/table/cmn_location...
[INFO] Current Infoblox EA 'Location' allowed values: {'NYC', 'LON'}
[INFO] Updating Infoblox EA allowed values to match ServiceNow data.
[INFO] Infoblox EA update successful.
```

---

## ℹ️ How Infoblox EA Updates Work

### Important behavior when updating the `Extensible Attribute` (EA)

- **Preserving existing values**: If a value already exists in Infoblox and is still included in the updated list, nothing changes — the value remains active and in place.
- **Adding new values**: New values from ServiceNow not yet present in Infoblox will be added to the EA's allowed list.
- **Removing missing values**: If a value is **missing** from the new list, it will be **removed** from the EA in Infoblox. This has a critical effect:
  - The value will be **deleted from all Infoblox objects** that currently use it.
  - This process is **not reversible** unless you have a backup of the previous EA values.

> ⚠️ It is highly recommended to test in a staging environment first and back up your EA configuration before running the script in production.

---

## 🔁 Script Workflow

1. **Load configuration** from `config.yaml`.
2. **Validate configuration keys** to ensure all required fields are present.
3. **Fetch locations** from the ServiceNow `cmn_location` table.
4. **Fetch the current values** of the EA (`Location`) from Infoblox.
5. **Compare values** between ServiceNow and Infoblox.
6. If differences are found:
   - Update the Infoblox EA so its values **exactly match** the ServiceNow data.
   - Detect and log **duplicates caused by sanitization** (e.g., truncation).
7. **Re-fetch and verify** updated values from Infoblox.
8. **Log completion** of synchronization with detailed status.

---

## 🧠 Troubleshooting

- **Missing Configuration Keys**: Ensure all required keys are in `config.yaml`.
- **API Errors**: Check your endpoint URLs and credentials.
- **No Locations Found**: Validate your ServiceNow query and access rights.

---

## 📁 File Structure

```bash
.
├── infoblox_gpon_import.py
├── config.yaml
├── requirements.txt
└── README.md
```

---

## ✍️ License

MIT License (or your preferred license here)
