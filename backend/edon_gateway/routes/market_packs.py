"""Versioned market pack registry routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..market_packs import get_market_pack, list_market_packs, normalize_market_pack_slug


router = APIRouter(prefix="/v1/governance/market-packs", tags=["market-packs"])


@router.get("")
async def get_market_packs():
    packs = list_market_packs()
    return {
        "packs": packs,
        "count": len(packs),
        "tenant_pinning": True,
        "versioned": True,
    }


@router.get("/{slug}")
async def get_market_pack_by_slug(slug: str):
    try:
        canonical = normalize_market_pack_slug(slug)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return get_market_pack(canonical)

