from pydantic import BaseModel
class FrontendMetric(BaseModel):
    source_id: int
    camera_name: str
    load_time_sec: float
