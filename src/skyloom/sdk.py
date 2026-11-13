"""Public SDK conversion at the boundary to immutable application records."""

from atproto_client.models.base import ModelBase
from atproto_client.models.blob_ref import BlobRef
from atproto_client.models.dot_dict import DotDict
from atproto_client.models.utils import get_model_as_dict
from atproto_client.utils import PaginatedResponse


def model_data(value):
    """Preserve SDK extensions and unknown records, including DotDict fallbacks.

    Plain dictionaries and other fixture values retain the existing adapter
    contract. DotDict's missing attributes return None, so attribute probing is
    not a reliable way to identify SDK models.
    """
    if isinstance(value, ModelBase | BlobRef | DotDict):
        return get_model_as_dict(value)
    return value


def page_items(response: PaginatedResponse, convert=None):
    """Convert this already-fetched page only; never fetch or retain other pages."""
    items = (model_data(item) for item in response.get_page_items())
    return tuple(map(convert, items)) if convert is not None else tuple(items)
