# ha-c2-stats

A Home Assistant custom integration that pulls your workouts from the [Concept2 Logbook](https://log.concept2.com) and exposes them as sensors and long-term statistics.

## What you get

One device per Logbook account with these sensors:

| Sensor | Notes |
| --- | --- |
| Lifetime distance | metres, all machines |
| Season / year / month / week distance | reset at the start of each period (Concept2 seasons run May 1 to April 30, weeks start Monday) |
| Today distance | disabled by default |
| Workouts | lifetime count |
| Lifetime time | total work time |
| Last workout | timestamp, with machine, workout type, time, pace, drag factor and comments as attributes |
| Last workout distance, time, pace, average power, stroke rate, calories | time and pace shown as M:SS.t, pace per 500m (per 1000m on the BikeErg) |
| Last workout average heart rate | disabled by default, only populated if the result has HR data |
| Workouts this week | resets Monday |
| Daily streak / Longest daily streak | consecutive days with at least one workout |
| Weekly streak / Longest weekly streak | consecutive Monday to Sunday weeks with at least one workout |
| Days since last workout | 0 if you've trained today |

Streaks count every machine together and use Home Assistant's timezone for the calendar day. A current streak isn't broken until a whole day (or week) passes with nothing logged, so a daily streak still shows on a morning before you've trained, as long as you trained yesterday.

For each machine type in your Logbook (RowErg, SkiErg, BikeErg and so on) you also get lifetime, season, year, month and week distance plus a workout count. New machine types get sensors automatically when they first show up.

The integration also writes your full Logbook history into Home Assistant's long-term statistics as `concept2_logbook:distance_<user id>` (all machines) and `concept2_logbook:<machine>_distance_<user id>`. That means the built-in **Statistics graph** card can chart metres per day, week or month going back to your first workout, not just from the day you installed the integration. See [`examples/dashboard.yaml`](examples/dashboard.yaml) for a ready-made dashboard.

### Personal bests

For each machine you get a PB sensor for every standard Concept2 event you have done: 100m, 500m, 1k, 2k, 5k, 6k, 10k, half marathon and marathon (plus 4k, 20k and 100k), and 1, 4, 30 and 60 minutes. A sensor only appears once you have a qualifying result, so you won't see a 100k PB unless you've rowed one.

Only pieces set up on the monitor as that exact distance or time count: a "Single Distance" 2000m piece counts towards the 2k PB, but a 2k inside a 5k, a 2000m Just Row, an interval workout or a manually entered result with no workout type does not. Distance events show your best time as M:SS.t (or H:MM:SS.t), time events show your best distance in metres. Attributes give the time in seconds, pace, date, and your best for the current season.

## How syncing works

Every 30 minutes the integration asks the Logbook only for results created or updated since the last check. Once a day it pulls the full list so deleted results drop out. Results are cached in `.storage/concept2_logbook.<entry id>`, so a Concept2 outage leaves the last known values in place instead of making everything unavailable.

To change how often it checks, open the integration and click **Configure** (anywhere from 5 minutes to once a day). The device also has two buttons: **Sync now** fetches new and changed results straight away, and **Full resync** pulls every result again, which is useful after deleting or editing workouts on the Logbook website.

## Setup

### 1. Register an API application with Concept2

1. Sign in at <https://log.concept2.com/developers/keys> and create a new application.
2. Set the redirect URI to `https://my.home-assistant.io/redirect/oauth`. That works as long as your [My Home Assistant](https://my.home-assistant.io) link points at your instance. If you have disabled My Home Assistant, use `<your HA external URL>/auth/external/callback` instead.
3. Note the Client ID and Client Secret.

The integration only asks for `user:read,results:read`. Concept2's docs say applications requesting *write* scopes must be built against the dev server (log-dev.concept2.com) and validated by Concept2 before going live. They don't say read-only applications need that, but I have not registered one myself, so if your new key is refused on the live server, email ranking@concept2.com about approval.

### 2. Install the integration

**HACS:** add `https://github.com/ChaoticOrb/ha-c2-stats` as a custom repository (category: Integration), install **Concept2 Logbook**, restart Home Assistant.

**Manual:** copy `custom_components/concept2_logbook` into your Home Assistant `config/custom_components/` folder and restart.

### 3. Add it

Settings > Devices and services > Add integration > **Concept2 Logbook**. Enter the Client ID and Client Secret when asked, then sign in to the Logbook and approve access.

Concept2 refresh tokens last a year and are rotated on every refresh, so you should not need to sign in again unless Home Assistant is off for over a year or you revoke access.

## Things to know

- All distance totals and the long-term statistics include rest metres from interval workouts, which matches the Logbook website's lifetime total. The Lifetime distance sensor has `work_distance` and `rest_distance` attributes if you want them separately. The Last workout distance sensor is work distance only.
- Average power uses Concept2's pace-to-watts formula (2.80 / pace³) and is only reported for RowErg and SkiErg family machines.
- Times and paces are shown as text (M:SS.t) so they read the way the monitor shows them. That means Home Assistant draws their history as a timeline rather than a line graph. The raw number is kept in a `seconds` attribute (`seconds_per_500m` for pace) for templates and automations.
- Results with no timezone recorded are treated as being in Home Assistant's timezone.

## Development

Tests run against a real Home Assistant core via `pytest-homeassistant-custom-component` (needs Python 3.14):

```bash
pip install -r requirements_test.txt
```

```bash
pytest
```
