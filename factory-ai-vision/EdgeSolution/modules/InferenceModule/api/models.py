"""API models
"""

from enum import Enum
from typing import List, Literal

from pydantic import BaseModel


class CameraModel(BaseModel):
    id: str
    type: str
    source: str
    lines: str
    zones: str
    aoi: str = None


class CamerasModel(BaseModel):
    lva_mode: Literal["http", "grpc"]
    fps: int
    cameras: List[CameraModel]


class PartModel(BaseModel):
    id: str
    name: str


class PartsModel(BaseModel):
    parts: List[PartModel]


class PartDetectionModeEnum(str, Enum):
    part_detection = "PD"
    part_counting = "PC"
    employee_safety = "ES"
    defect_detection = "DD"


class UploadModelBody(BaseModel):
    model_uri: str = None
    model_dir: str = None
