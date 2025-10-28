# PagerDuty Team Incident Exporter

This script leverages the PagerDuty API to export incidents for a specified team over a defined lookback window into a CSV file. This can help teams during incident reviews, retrospectives, reporting or to adjust alerts and on-call policies to reduce alert fatigue, burnout, and toil.

> [!TIP]
> Defaults to pulling the maximum allowed 180 days of incidents if the `--days` argument is not passed.

## Overview

>[!IMPORTANT]
> For security reasons, this script **does not** hardcode your API Token, instead, it reads it from an environment variable named `PAGERDUTY_API_TOKEN`.

On **macOS** / **Linux**, for a single session use, run the following command in your terminal, or, for persistence, add it to your `~/.bashrc` or `~/.zshrc` file.:

```
export PAGERDUTY_API_TOKEN="YOUR_API_KEY_HERE"
```

## CLI Usage

```
./pd_team_incident_exporter.py -h
usage: pd_team_incident_exporter [-h] [-t TEAM] [-d DAYS] [-o OUTPUT]

Export PagerDuty incidents for a team to CSV.

options:
  -h, --help           show this help message and exit
  -t, --team TEAM      PagerDuty "team_name" (exact) (default: None)
  -d, --days DAYS      Lookback window in days (default: 180)
  -o, --output OUTPUT  Output CSV filename (defaults to pagerduty_incidents_<team_name>.csv) (default: None)
```

### Examples
- ```
  ./pd_team_incident_exporter.py --team "team_name"
  ```
- ```
  ./pd_team_incident_exporter.py -t <team_name> -d 30 -o <file_name>.csv
  ```

### Example run

```
./pd_team_incident_exporter.py -t <team_name>
[INFO] Fetching incidents for team '<team_name>' from 2025-04-30 to 2025-10-27 (last 180 days)...
Fetching incidents: [██████████████████████████████] 86/86
Exporting incidents: [██████████████████████████████] 86/86
[INFO] 86 incidents exported to pagerduty_incidents_<team_name>.csv
```

## Troubleshooting

- No API Key:
    - Head to `https://<your_domain>.pagerduty.com/api_keys` and click **Create New API Key**

> [!IMPORTANT]
> - This key is only only ever shown **once** so please record it for future use.
> - **ENSURE YOU ARE SAFELY STORING YOUR API KEY**
> - **NEVER SHARE YOUR API KEY WITH ANYONE**
> - **NEVER POST YOUR API KEY TO GITHUB**

