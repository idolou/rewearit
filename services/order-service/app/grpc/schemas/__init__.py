"""Generated Protobuf and gRPC stubs for ReWearIt schemas."""
import sys
from pathlib import Path
from google.protobuf import timestamp_pb2  # noqa: F401

_schemas_dir = str(Path(__file__).parent.resolve())
if _schemas_dir not in sys.path:
    sys.path.insert(0, _schemas_dir)

from . import events_pb2  # noqa: E402, F401
from . import events_pb2_grpc  # noqa: E402, F401
from . import catalog_service_pb2  # noqa: E402, F401
from . import catalog_service_pb2_grpc  # noqa: E402, F401
