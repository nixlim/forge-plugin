from __future__ import annotations
import sys
import unittest

from tests._revision8_constants import ROOT
from tests._revision8_support import Revision8Support

sys.path.insert(0, str(ROOT / "scripts"))




class Revision8CoordinationTests(Revision8Support, unittest.TestCase):
    """Revision-8 append, orphan, identity, and successor-DAG contracts."""


if __name__ == "__main__":
    unittest.main()
