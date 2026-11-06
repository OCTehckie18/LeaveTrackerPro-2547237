from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """JSON uses camelCase (`fromDate`); unknown input fields are rejected (blocks mass-assignment,
    e.g. a client sending `status` or `isExtended`)."""

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid", from_attributes=True
    )


class Page[T](CamelModel):
    items: list[T]
    total: int
    page: int
    size: int
