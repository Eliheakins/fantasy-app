"""Routes under /api, one module per area. Instant reads and league-build reads run inline;
simulations are jobs (`jobs.py`).

`router` includes the area routers in a fixed order: the OpenAPI path order is the registration
order, and `web/openapi.json` is pinned to it. Add a route inside the area run that matches where
it should appear, or add a router at the right place in the list below."""

from fastapi import APIRouter

from fantasy.api_routes import (
    jobs,
    league,
    lineup,
    live,
    players,
    scores,
    season,
    status,
    trade,
    week,
)

AREA_ROUTERS = (
    status.router,
    league.router,
    week.router,
    season.router,
    lineup.router,
    scores.router,
    trade.router,
    players.router,
    jobs.router,
    live.router,
)

router = APIRouter(prefix="/api")
for area_router in AREA_ROUTERS:
    router.include_router(area_router)
