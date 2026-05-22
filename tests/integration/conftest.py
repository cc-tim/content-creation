import pytest

# Auto-mark every test in this directory as integration so they are
# skipped by default and only run when --integration is passed.
pytestmark = pytest.mark.integration
