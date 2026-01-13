from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.core.tags import ALLOWED_SEASONS, normalize_tag
from app.schemas.schemas import TagSuggestOut
from app.core.tags import ALLOWED_EVENTS

router = APIRouter(prefix="/tags", tags=["tags"])

BUILTIN_STYLE = [
    "minimal",
    "classic",
    "preppy",
    "streetwear",
    "athleisure",
    "boho",
    "vintage",
    "edgy",
    "maximalist",
    "utilitarian",
    "techwear",
    "romantic",
]
BUILTIN_EVENT = sorted(list(ALLOWED_EVENTS))

def _labelize(x: str) -> str:
    return " ".join(part.capitalize() for part in x.split("-"))

@router.get("/suggest", response_model=TagSuggestOut)
async def suggest(
    category: str = Query(..., pattern="^(style|event|season)$"),
    q: str = Query("", min_length=0),
    limit: int = 10,
    session: AsyncSession = Depends(get_session),
):
    qn = normalize_tag(q) if q else ""
    base = (
        sorted(ALLOWED_SEASONS)
        if category == "season"
        else (BUILTIN_STYLE if category == "style" else BUILTIN_EVENT)
    )

    def match(xs: list[str]) -> list[str]:
        return [x for x in xs if (not qn) or x.startswith(qn)]

    suggestions = [
        {"key": x, "label": _labelize(x), "category": category, "source": "builtin"}
        for x in match(base)
    ]

    if category != "season":
        sql = f"""
        SELECT t as key, COUNT(*) as c
        FROM (SELECT unnest({category}_tags) as t FROM item) s
        WHERE t IS NOT NULL
        GROUP BY t
        ORDER BY c DESC
        LIMIT 50;
        """
        rows = (await session.execute(text(sql))).mappings().all()
        hist = [r["key"] for r in rows if (not qn) or r["key"].startswith(qn)]
        for x in hist:
            if not any(s["key"] == x for s in suggestions):
                suggestions.append(
                    {"key": x, "label": _labelize(x), "category": category, "source": "user-history"}
                )

    return {"suggestions": suggestions[:limit]}
