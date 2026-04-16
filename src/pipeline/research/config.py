from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class OpenAlexConfig(BaseModel):
    enabled: bool = True
    mailto: str = "creditcardtim@gmail.com"
    from_publication_date: str = "2018-01-01"
    sort: str = "cited_by_count:desc"


class AAPConfig(BaseModel):
    enabled: bool = True
    rate_limit_rps: float = 1.0
    max_result_pages: int = 2
    user_agent: str = (
        "content-creation-research-bot (contact: creditcardtim@gmail.com)"
    )


class ResearchSources(BaseModel):
    openalex: OpenAlexConfig = Field(default_factory=OpenAlexConfig)
    aap: AAPConfig = Field(default_factory=AAPConfig)


class ResearchConfig(BaseSettings):
    """Config for the local research corpus subsystem."""

    model_config = SettingsConfigDict(
        env_prefix="RESEARCH_",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
    )

    data_dir: Path = Path("./research")
    default_limit_per_topic: int = 10
    topics: list[str] = Field(
        default_factory=lambda: [
            "sleep",
            "screen_time",
            "tantrums",
            "discipline",
            "parenting_styles",
            "adhd",
            "anxiety",
            "early_literacy",
        ]
    )
    sources: ResearchSources = Field(default_factory=ResearchSources)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "research.db"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"
