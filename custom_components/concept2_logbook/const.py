"""Constants for the Concept2 Logbook integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "concept2_logbook"

OAUTH2_AUTHORIZE: Final = "https://log.concept2.com/oauth/authorize"
OAUTH2_TOKEN: Final = "https://log.concept2.com/oauth/access_token"
API_BASE: Final = "https://log.concept2.com/api"

# Concept2 wants multiple scopes comma separated, and wants the same scope
# re-sent on every token request, including refreshes.
OAUTH_SCOPE: Final = "user:read,results:read"

ACCEPT_HEADER: Final = "application/vnd.c2logbook.v1+json"
PAGE_SIZE: Final = 250  # API maximum

UPDATE_INTERVAL: Final = timedelta(minutes=30)
FULL_SYNC_INTERVAL: Final = timedelta(hours=24)
# Overlap on incremental syncs so clock skew never drops a result.
INCREMENTAL_OVERLAP: Final = timedelta(hours=2)

STORAGE_VERSION: Final = 1

# Machine types the API can return. Display names for entity naming.
MACHINE_TYPES: Final = {
    "rower": "RowErg",
    "skierg": "SkiErg",
    "bike": "BikeErg",
    "dynamic": "Dynamic RowErg",
    "slides": "RowErg on slides",
    "paddle": "Paddle adapter",
    "water": "On water",
    "snow": "On snow",
    "rollerski": "Rollerski",
    "multierg": "MultiErg",
}
# Standard Concept2 ranked events, across all machines. A PB sensor is only
# created for an event once there is a qualifying result for it, so events a
# machine doesn't use never show up.
PB_DISTANCES: Final = (
    100,
    500,
    1000,
    2000,
    4000,
    5000,
    6000,
    10000,
    20000,
    21097,
    42195,
    100000,
)
PB_TIMES_MIN: Final = (1, 4, 30, 60)
# Only pieces set up as a single fixed distance or time count towards PBs.
PB_DISTANCE_WORKOUT_TYPE: Final = "FixedDistanceSplits"
PB_TIME_WORKOUT_TYPE: Final = "FixedTimeSplits"

# Bike pace is conventionally quoted per 1000m, everything else per 500m.
PACE_1000M_TYPES: Final = {"bike"}
