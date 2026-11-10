"""Trade-partner, trade-asset and market-value reads."""

from typing import Annotated, Any

import polars as pl
from fastapi import APIRouter, Query

from fantasy import _view as view
from fantasy import data_api
from fantasy.api_deps import Ctx, DataDir
from fantasy.api_envelope import guarded, rows
from fantasy.api_models import (
    AssetRow,
    Envelope,
    MarketValueRow,
    PartnerRow,
)

router = APIRouter()
MAX_IDS_LENGTH = 4000


@router.get("/leagues/{league}/trade-partners", response_model=Envelope[list[PartnerRow]])
def trade_partners(league: str, ctx: Ctx) -> Any:
    return guarded(lambda: rows(data_api.trade_partners(league, ctx.data_dir, ctx.team)))


@router.get("/leagues/{league}/trade-assets", response_model=Envelope[list[AssetRow]])
def trade_assets(league: str, ctx: Ctx, roster_id: int | None = None) -> Any:
    def build() -> list[dict[str, Any]]:
        assets = data_api.trade_assets(league, roster_id, ctx.data_dir, ctx.team)
        labels = view.asset_labels(assets)
        label = pl.Series("label", [labels[g] for g in assets["gsis_id"]], dtype=pl.String)
        return rows(assets.with_columns(label))

    return guarded(build)


@router.get("/leagues/{league}/market-values", response_model=Envelope[list[MarketValueRow]])
def market_values(
    league: str,
    data_dir: DataDir,
    ids: Annotated[str, Query(max_length=MAX_IDS_LENGTH, description="comma-separated gsis ids")],
) -> Any:
    wanted = [i for i in ids.split(",") if i]
    return guarded(lambda: rows(data_api.market_values(league, wanted, data_dir)))
