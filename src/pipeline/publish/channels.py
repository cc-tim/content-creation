from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ChannelProfile:
    name: str
    niche: str
    locale: str
    channel_id: str
    voice_guide: str
    default_tags: list[str]
    category_id: int


@dataclass(frozen=True)
class ChannelConfig:
    profiles: dict[str, ChannelProfile]
    routing: dict[str, str]  # "niche/locale" -> profile name


def load_channel_config(path: Path) -> ChannelConfig:
    """Load YouTube channel config from a TOML file."""
    if not path.exists():
        raise FileNotFoundError(f"channel config not found at {path}")
    data = tomllib.loads(path.read_text(encoding="utf-8"))

    profiles: dict[str, ChannelProfile] = {}
    for name, raw in (data.get("profiles") or {}).items():
        profiles[name] = ChannelProfile(
            name=name,
            niche=raw["niche"],
            locale=raw["locale"],
            channel_id=raw.get("channel_id", ""),
            voice_guide=raw.get("voice_guide", ""),
            default_tags=list(raw.get("default_tags", [])),
            category_id=int(raw["category_id"]),
        )

    routing = dict(data.get("routing") or {})
    for key, profile_name in routing.items():
        if profile_name not in profiles:
            raise ValueError(
                f"routing references unknown profile: {profile_name} (from key '{key}')"
            )

    return ChannelConfig(profiles=profiles, routing=routing)


def resolve_profile(
    cfg: ChannelConfig,
    *,
    niche: str | None,
    locale: str,
    override: str | None,
) -> ChannelProfile:
    """Resolve to a ChannelProfile. Priority: override > routing > error."""
    if override is not None:
        if override not in cfg.profiles:
            raise ValueError(
                f"profile '{override}' not found in config. Available: {sorted(cfg.profiles)}"
            )
        return cfg.profiles[override]

    if niche is None:
        raise ValueError(
            "No niche set on context and no --profile override. "
            "Pass --niche NAME on produce or --profile NAME on publish."
        )

    key = f"{niche}/{locale}"
    profile_name = cfg.routing.get(key)
    if profile_name is None:
        raise ValueError(
            f"No channel configured for (niche={niche}, locale={locale}). "
            f"Add a [routing] entry in configs/youtube_channels.toml "
            f"or pass --profile NAME."
        )
    return cfg.profiles[profile_name]


def auto_detect_niche(cfg: ChannelConfig, *, locale: str) -> str:
    """Return the single niche configured for this locale.

    Errors cleanly when zero or multiple niches exist.
    """
    candidates: list[str] = []
    for key in cfg.routing:
        try:
            niche, loc = key.split("/", 1)
        except ValueError:
            continue
        if loc == locale:
            candidates.append(niche)

    unique = sorted(set(candidates))
    if len(unique) == 0:
        raise ValueError(
            f"No channel configured for locale={locale}. "
            f"Add a [routing] entry in configs/youtube_channels.toml "
            f"or pass --niche NAME / --niche none."
        )
    if len(unique) > 1:
        raise ValueError(
            f"Ambiguous: locale={locale} maps to niches: {', '.join(unique)}. Specify --niche NAME."
        )
    return unique[0]
