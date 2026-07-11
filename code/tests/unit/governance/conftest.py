"""
Mock boto3 at sys.modules level BEFORE governance.py is imported.
governance.py does `import boto3` at module top, so the mock must be injected
before pytest even collects test_governance.py.
"""
import sys
import os
from unittest.mock import MagicMock

# Inject mock boto3 before any test file imports governance
if "boto3" not in sys.modules:
    mock_boto3 = MagicMock()
    mock_boto3.resource.return_value = MagicMock()
    mock_boto3.client.return_value = MagicMock()
    mock_boto3.Session.return_value = MagicMock()
    sys.modules["boto3"] = mock_boto3

# botocore.exceptions is used in tests (ClientError) — provide a real or mocked one
if "botocore" not in sys.modules:
    mock_botocore = MagicMock()

    class _ClientError(Exception):
        def __init__(self, error_response, operation_name):
            self.response = error_response
            self.operation_name = operation_name
            super().__init__(str(error_response))

    mock_botocore.exceptions = MagicMock()
    mock_botocore.exceptions.ClientError = _ClientError
    sys.modules["botocore"] = mock_botocore
    sys.modules["botocore.exceptions"] = mock_botocore.exceptions

# Ensure governance module can be found
GOV_PATH = os.path.join(os.path.dirname(__file__), "../../../lambda/common")
if GOV_PATH not in sys.path:
    sys.path.insert(0, GOV_PATH)
