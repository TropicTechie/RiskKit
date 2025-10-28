#!/usr/bin/env python3

import argparse
import csv
import datetime
import os
import re
import requests
import sys
from requests.exceptions import RequestException
from typing import List, Dict, Any, Optional

# ===================================================
# CONFIGURATIONS
# ===================================================

PAGERDUTY_API_TOKEN = os.getenv("PAGERDUTY_API_TOKEN")
PD_BASE_URL = "https://api.pagerduty.com"
REQUEST_TIMEOUT = 20 # seconds

PD_API_HEADERS = {
    "Accept": "application/vnd.pagerduty+json;version=2",
    "Authorization": f"Token token={PAGERDUTY_API_TOKEN}",
}

# ===================================================
# FUNCTIONS
# ===================================================

PAGERDUTY_TEAM_ID_PATTERN = re.compile(r"^[A-Z0-9]{7,}$")

def sanitize_filename_component(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", name.strip().lower()).strip("_")
    return s or "team"

def is_pagerduty_team_id(value: str) -> bool:
    return bool(PAGERDUTY_TEAM_ID_PATTERN.match(value))

def validate_team_id(team_id: str) -> str:
    if not team_id or not isinstance(team_id, str) or not is_pagerduty_team_id(team_id):
        print(f"[ERROR]: Resolved team id '{team_id}' is invalid.")
        sys.exit(1)
    return team_id

def get_team_id_by_name(team_name: str) -> str:
    """Search PagerDuty for a team by name (case-insensitive exact match)."""
    url = f"{PD_BASE_URL}/teams"
    params = {"query": team_name, "limit": 100}
    try:
        response = requests.get(url, headers=PD_API_HEADERS, params=params, timeout=REQUEST_TIMEOUT)
        if response.status_code != 200:
            print(f"[ERROR]: Failed to retrieve teams: {response.text}")
            sys.exit(1)
    except RequestException as e:
        print(f"[ERROR]: Request to PagerDuty failed while fetching teams: {e}")
        sys.exit(1)

    data = response.json() or {}

    for team in data.get("teams", []):
        if str(team.get("name", "")).lower() == team_name.lower():
            return validate_team_id(str(team.get("id") or ""))
    print(f"[ERROR]: Team '{team_name}' not found.")
    sys.exit(1)

def get_incidents_for_team(team_id: str, since: str, until: str) -> List[Dict[str, Any]]:
    """Fetch incidents for the team between 'since' and 'until'."""
    incidents: List[Dict[str, Any]] = []
    url = f"{PD_BASE_URL}/incidents"
    limit = 100
    offset = 0

    validate_team_id(team_id)

    total_count: Optional[int] = None
    fetched_count = 0
    printed_progress = False

    while True:
        params = {
            "team_ids[]": [team_id],
            "since": since,
            "until": until,
            "limit": limit,
            "offset": offset,
            "total": "true",
        }
        try:
            response = requests.get(url, headers=PD_API_HEADERS, params=params, timeout=REQUEST_TIMEOUT)
            if response.status_code != 200:
                print(f"[ERROR]: Failed to retrieve incidents: {response.text}")
                sys.exit(1)
        except RequestException as e:
            print(f"[ERROR]: Request to PagerDuty failed while fetching incidents: {e}")
            sys.exit(1)
        data = response.json() or {}
        page_incidents = data.get("incidents", [])
        incidents.extend(page_incidents)

        if total_count is None:
            try:
                total_count = int(data.get("total")) if data.get("total") is not None else None
            except (ValueError, TypeError):
                total_count = None

        fetched_count += len(page_incidents)
        if total_count:
            print_progress_bar("Fetching incidents: ", fetched_count, total_count)
            printed_progress = True

        if not data.get("more", False):
            break
        offset += limit

    if printed_progress:
        sys.stdout.write("\n")
    return incidents


def get_incident_resolve_metadata(incident_id: str) -> Dict[str, Optional[str]]:
    """Return resolver and reason from the incident's resolve log entry."""
    url = f"{PD_BASE_URL}/incidents/{incident_id}/log_entries"
    params = {"limit": 100, "is_overview": "false", "include[]": "users"}
    try:
        response = requests.get(url, headers=PD_API_HEADERS, params=params, timeout=REQUEST_TIMEOUT)
        if response.status_code != 200:
            return {"resolved_by": None}
    except RequestException:
        return {"resolved_by": None}

    data = response.json() or {}
    for entry in data.get("log_entries", []):
        if entry.get("type") == "resolve_log_entry":
            agent = entry.get("agent") or {}
            resolved_by = agent.get("summary") or agent.get("name")
            channel = entry.get("channel") or {}
            reason = channel.get("summary") or channel.get("type") or entry.get("summary")
            return {
                "resolved_by": str(resolved_by) if resolved_by else None,
            }
    return {"resolved_by": None}


def write_incidents_to_csv(incidents: List[Dict[str, Any]], team_name: str, filename: Optional[str] = None) -> None:
    """Write the incident data to CSV with selected fields."""
    if not filename:
        team = sanitize_filename_component(team_name)
        filename = f"pagerduty_incidents_{team}.csv"
    headers = [
        "HTML URL",
        "Incident Number",
        "Title",
        "Status",
        "Service Name",
        "Created",
        "Urgency",
        "Resolved By",
    ]
    with open(filename, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)

        total_items = len(incidents)
        processed = 0
        printed_progress = False

        for inc in incidents:
            service = inc.get("service") or {}
            service_name = service.get("summary") or service.get("name") or "N/A"

            resolved_by = ""
            if inc.get("status") == "resolved":
                meta = get_incident_resolve_metadata(str(inc.get("id", "")))
                resolved_by = meta.get("resolved_by") or ((inc.get("last_status_change_by") or {}).get("summary")) or "Unknown"

            writer.writerow([
                inc.get("html_url", ""),
                inc.get("incident_number", "N/A"),
                inc.get("title", "N/A"),
                inc.get("status", "N/A"),
                service_name,
                inc.get("created_at", "N/A"),
                inc.get("urgency", "N/A"),
                resolved_by,
            ])

            processed += 1
            if total_items:
                print_progress_bar("Exporting incidents:", processed, total_items)
                printed_progress = True

    if printed_progress:
        sys.stdout.write("\n")
    print(f"[INFO] {len(incidents)} incidents exported to {filename}")

def to_iso8601_utc(dt: datetime.datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def print_progress_bar(prefix: str, current: int, total: Optional[int]) -> None:
    """Render a simple inline progress bar using ▁ (empty), ▄ (current), █ (completed)."""
    bar_len = 30 # Sets the bar length to 30 characters
    if total and total > 0: # Check for valid total and if bar should be rendered
        ratio = 0 if total == 0 else max(0.0, min(1.0, current / total)) # Calculate progress ratio between 0 and 1
        pos = int(bar_len * ratio) # Use ratio int to determine position within the bar
        if pos >= bar_len: # Detects completion status based on the bar length
            bar = "█" * bar_len # Render completed bar if task is done
        else: # Build the bar to show progress
            completed = "█" * max(0, pos) # Defines completed indicator.
            current_block = "▄" # Defines in progress indicator
            empty = "▁" * max(0, bar_len - pos - 1) # Defines empty/to-do indicator
            bar = f"{completed}{current_block}{empty}" # Assemble the three-part bar to show progression
        sys.stdout.write(f"\r{prefix} [{bar}] {current}/{total}") # Render the bar in terminal with numeric status
    else:
        sys.stdout.write(f"\r{prefix} {current}") # Print the current count if no total is provided
    sys.stdout.flush() # Display progression as soon as possible

def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pd_team_incident_exporter",
        description="Export PagerDuty incidents for a team to CSV.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog=(
            "Examples:\n"
            "  pd_team_incident_exporter.py --team <team_name>\n"
            "  pd_team_incident_exporter.py -t <team_name> --days 90 -o <file_name>.csv\n"
        ),
    )
    parser.add_argument(
        "-t", "--team",
        dest="team_name",
        help="PagerDuty team name (exact)",
    )
    parser.add_argument(
        "-d", "--days",
        type=int,
        default=180,
        help="Lookback window in days",
    )
    parser.add_argument(
        "-o", "--output",
        help="Output CSV filename (defaults to pagerduty_incidents_<team_name>.csv)",
    )
    return parser.parse_args()

# ===================================================
# MAIN LOGIC
# ===================================================

def main() -> None:
    if not PAGERDUTY_API_TOKEN:
        print("[ERROR]: Please set the PAGERDUTY_API_TOKEN environment variable.")
        sys.exit(1)

    args = parse_arguments()

    team_name = (args.team_name or input("Enter the PagerDuty team name: ").strip())
    if not team_name:
        print("[ERROR]: Team name cannot be empty.")
        sys.exit(1)

    team_id = team_name if is_pagerduty_team_id(team_name) else get_team_id_by_name(team_name)

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    lookback_days = max(1, int(args.days))
    lookback_utc = now_utc - datetime.timedelta(days=lookback_days)

    since = to_iso8601_utc(lookback_utc)
    until = to_iso8601_utc(now_utc)

    # Displays the date range (start and end, formatted as YYYY-MM-DD)
    print(f"[INFO]: Fetching incidents for team '{team_name}' from {since[:10]} to {until[:10]} (last {lookback_days} days)...")

    incidents = get_incidents_for_team(team_id, since, until)

    if incidents:
        write_incidents_to_csv(incidents, team_name, args.output)
    else:
        print(f"[INFO]: No incidents found for team '{team_name}' in the last {lookback_days} days.")

if __name__ == "__main__":
    main()
