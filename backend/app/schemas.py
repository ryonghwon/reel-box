from typing import Literal

from pydantic import BaseModel, Field, field_validator

from . import storage


class Registration(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=100)
    mode: Literal["video", "audio"] = "video"
    collections: bool = False
    collection_limit: int = Field(default=25, ge=1, le=100)
    auto_download: bool = False
    source: Literal["links", "instagram_saved"] = "links"
    output_format: Literal["mp4", "original"] = "mp4"


class Selection(BaseModel):
    ids: list[str] = Field(default_factory=list, max_length=100000)


class ImportProgress(BaseModel):
    draft_id: str = Field(max_length=32)
    cursor: int = Field(ge=0, le=20000)
    added: int = Field(ge=0, le=20000)
    duplicates: int = Field(ge=0, le=20000)
    auto: bool = True


class DownloadPreferences(BaseModel):
    output_format: Literal["mp4", "original"] = "mp4"
    height: int | None = Field(default=None, ge=144, le=16384)


class Preferences(BaseModel):
    folder: str = "Reelbox"
    retention_days: int = Field(default=0, ge=0, le=365)
    filename_template: str = "{date}_{platform}_{title}_{id}"

    @field_validator("folder")
    @classmethod
    def folder_valid(cls, v):
        storage.folder_path(v)
        return v

    @field_validator("filename_template")
    @classmethod
    def template_valid(cls, v):
        return storage.validate_template(v)


class StorageLocation(BaseModel):
    path: str = Field(min_length=1, max_length=4096)


class BrowserOutcome(BaseModel):
    ids: list[str] = Field(max_length=500)
    message: str = Field(max_length=400)
    code: Literal[
        "BROWSER_LOGIN_REQUIRED",
        "BROWSER_ACCESS_RESTRICTED",
        "BROWSER_MEDIA_UNAVAILABLE",
        "BROWSER_REVIEW_REQUIRED",
        "BROWSER_SAVE_FAILED",
    ]


class BrowserPostComplete(BaseModel):
    target_id: str = Field(max_length=64)
    saved_ids: list[str] = Field(min_length=1, max_length=20)


class BrowserMetadata(BaseModel):
    source: str = Field(max_length=2048)
    title: str = Field(max_length=200)
    uploader: str = Field(max_length=100)
