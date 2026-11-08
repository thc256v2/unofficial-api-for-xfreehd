from __future__ import annotations

import logging
import re
from typing import Any, AsyncIterator

from empflix_api import Client, Sort, SortDate

from app.schemas import FilterField, FilterOption, MediaItem

logger = logging.getLogger("xfreehd.web.providers.empflix")

_ISO_DUR = re.compile(
    r"^PT(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+)S)?$",
    re.IGNORECASE,
)

SORT_MAP = {
    "relevance": Sort.Sort_relevance,
    "recent": Sort.Sort_recent,
    "views": Sort.Sort_most_viewed,
    "rating": Sort.Sort_top_rated,
    "duration": Sort.Sort_longest,
}

DATE_MAP = {
    "all": SortDate.Sort_all,
    "today": SortDate.Sort_today,
    "week": SortDate.Sort_week,
    "month": SortDate.Sort_month,
    "year": SortDate.Sort_year,
}


def _format_length(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if ":" in text and not text.upper().startswith("PT"):
        return text
    match = _ISO_DUR.match(text)
    if match:
        h = int(match.group("h") or 0)
        m = int(match.group("m") or 0)
        s = int(match.group("s") or 0)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"
    try:
        total = int(float(text))
    except ValueError:
        return text
    if total <= 0:
        return None
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _category_labels(raw: Any) -> list[str]:
    if not raw:
        return []
    out: list[str] = []
    for entry in raw:
        if isinstance(entry, dict):
            name = entry.get("name") or entry.get("title") or entry.get("label")
            if name:
                out.append(str(name))
        else:
            text = str(entry).strip()
            if text:
                out.append(text)
    return out


def _pick_stream_url(cdn_urls: dict[int, str], quality: str = "best") -> str | None:
    if not cdn_urls:
        return None
    heights = sorted(cdn_urls.keys())
    q = (quality or "best").lower().strip()
    if q in ("worst", "low"):
        height = heights[0]
    elif q in ("half", "mid", "middle"):
        height = heights[len(heights) // 2]
    elif q.endswith("p") and q[:-1].isdigit():
        want = int(q[:-1])
        height = min(heights, key=lambda h: abs(h - want))
    elif q.isdigit():
        want = int(q)
        height = min(heights, key=lambda h: abs(h - want))
    else:
        height = heights[-1]
    return cdn_urls.get(height)


def _to_item(video: Any) -> MediaItem:
    thumb = getattr(video, "thumbnail_url", None) or getattr(video, "thumbnail", None)
    tags = getattr(video, "tags", None) or []
    if isinstance(tags, str):
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    else:
        tag_list = [str(t).strip() for t in tags if str(t).strip()]

    cdn = getattr(video, "direct_download_urls", None) or {}
    stream_urls = [cdn[h] for h in sorted(cdn.keys())] if isinstance(cdn, dict) else []

    return MediaItem(
        provider="empflix",
        url=getattr(video, "url", None) or "",
        id=getattr(video, "video_id", None),
        title=getattr(video, "title", None),
        thumbnail=thumb,
        length=_format_length(getattr(video, "length", None) or getattr(video, "duration", None)),
        views=str(getattr(video, "views", None)) if getattr(video, "views", None) is not None else None,
        rating=getattr(video, "rating", None) or getattr(video, "rating_percent", None),
        author=getattr(video, "author_name", None) or getattr(video, "author", None),
        publish_date=getattr(video, "publish_date", None),
        tags=tag_list,
        categories=_category_labels(getattr(video, "categories", None)),
        stream_urls=stream_urls,
        embed_url=getattr(video, "embed_url", None),
        is_private=None,
        extras={
            "stream_type": "raw",
            "qualities": list(getattr(video, "video_qualities", None) or []),
        }
        if stream_urls
        else {},
    )


class EMPFlixProvider:
    """Provider wrapping https://github.com/EchterAlsFake/unofficial-api-for-empflix"""

    id = "empflix"
    name = "EMPFlix"
    description = "Unofficial async scraper for empflix.com (RAW / MP4)"

    def __init__(self) -> None:
        self._client: Client | None = None

    @property
    def capabilities(self) -> list[str]:
        return ["search", "detail", "resolve_stream"]

    def filters(self) -> list[FilterField]:
        return [
            FilterField(
                key="sort_by",
                label="Sortering",
                type="select",
                default="relevance",
                options=[
                    FilterOption(value="relevance", label="Relevantie"),
                    FilterOption(value="recent", label="Nieuwste"),
                    FilterOption(value="views", label="Meest bekeken"),
                    FilterOption(value="rating", label="Best beoordeeld"),
                    FilterOption(value="duration", label="Langste"),
                ],
            ),
            FilterField(
                key="time_frame",
                label="Periode",
                type="select",
                default="all",
                options=[
                    FilterOption(value="all", label="Alle tijd"),
                    FilterOption(value="today", label="Vandaag"),
                    FilterOption(value="week", label="Week"),
                    FilterOption(value="month", label="Maand"),
                    FilterOption(value="year", label="Jaar"),
                ],
            ),
            FilterField(
                key="pages",
                label="Pagina’s",
                type="number",
                default=1,
                min=1,
                max=5,
            ),
        ]

    async def startup(self) -> None:
        self._client = Client()

    async def shutdown(self) -> None:
        if self._client is not None:
            await self._client.core.close()
            self._client = None

    @property
    def client(self) -> Client:
        if self._client is None:
            raise RuntimeError("EMPFlixProvider is not started")
        return self._client

    async def search(
        self,
        query: str,
        *,
        filters: dict[str, Any] | None = None,
    ) -> AsyncIterator[MediaItem]:
        f = filters or {}
        sort_by = str(f.get("sort_by", "relevance"))
        time_frame = str(f.get("time_frame", "all"))
        try:
            pages = int(f.get("pages", 1))
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid pages") from exc
        pages = max(1, min(pages, 5))

        if sort_by not in SORT_MAP:
            raise ValueError(f"Invalid sort_by '{sort_by}'")
        if time_frame not in DATE_MAP:
            raise ValueError(f"Invalid time_frame '{time_frame}'")

        seen: set[str] = set()
        async for result in self.client.search(
            query=query,
            sorting_sort=SORT_MAP[sort_by],
            sorting_date=DATE_MAP[time_frame],
            pages=pages,
        ):
            video = getattr(result, "item", None)
            if video is None:
                continue
            item = _to_item(video)
            key = item.url or item.id
            if not key or key in seen:
                continue
            seen.add(key)
            yield item

    async def get_media(self, url: str) -> MediaItem:
        video = await self.client.get_video(url, load_html=True)
        return _to_item(video)

    async def resolve_stream(self, url: str, *, quality: str = "best") -> tuple[str, str | None]:
        video = await self.client.get_video(url, load_html=True)
        await video.load_fields("direct_download_urls", "video_qualities", "title")
        stream = _pick_stream_url(dict(video.direct_download_urls or {}), quality)
        if not stream:
            raise ValueError(f"No stream URL for {url}")
        return stream, video.title

    def playback_headers(self, stream_url: str | None = None) -> dict[str, str]:
        _ = stream_url
        return {}
