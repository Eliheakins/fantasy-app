"""What every route needs to know about the request: where the data is and whose team is viewed.

`create_app` sets `app.state.data_dir` once; a route asks for `Ctx` (data directory and the `?team=`
roster id) or `DataDir` (routes with no team) and passes the values down explicitly, so a test can
build an app on a temporary directory.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Query, Request

Team = Annotated[
    int | None, Query(description="Roster id to view as; omitted means my team (Sleeper is_me)")
]


@dataclass(frozen=True)
class RequestContext:
    data_dir: Path
    team: int | None = None  # None: my team, as Sleeper's is_me marks it


def get_data_dir(request: Request) -> Path:
    data_dir: Path = request.app.state.data_dir
    return data_dir


DataDir = Annotated[Path, Depends(get_data_dir)]


def get_context(data_dir: DataDir, team: Team = None) -> RequestContext:
    return RequestContext(data_dir, team)


Ctx = Annotated[RequestContext, Depends(get_context)]
