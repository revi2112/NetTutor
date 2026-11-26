"""The list of RFCs to ingest (`data/rfc_list.yaml`), loaded and validated."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_RFC_LIST = Path("data/rfc_list.yaml")
RFC_BASE_URL = "https://www.rfc-editor.org/rfc"


class RfcEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    number: int = Field(gt=0)
    title: str = Field(min_length=1)

    @property
    def filename(self) -> str:
        return f"rfc{self.number}.txt"

    @property
    def txt_url(self) -> str:
        return f"{RFC_BASE_URL}/rfc{self.number}.txt"

    @property
    def html_url(self) -> str:
        return f"{RFC_BASE_URL}/rfc{self.number}"


def load_rfc_list(path: Path = DEFAULT_RFC_LIST) -> list[RfcEntry]:
    data = yaml.safe_load(path.read_text())
    entries = [RfcEntry.model_validate(item) for item in data["rfcs"]]
    seen: set[int] = set()
    for entry in entries:
        if entry.number in seen:
            raise ValueError(f"duplicate RFC number: {entry.number}")
        seen.add(entry.number)
    return entries
