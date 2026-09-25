from __future__ import annotations

import unittest

from tests.test_route_config_grammar import RouteGrammarMixin
from tests.test_route_config_probe import RouteProbeMixin
from tests.test_route_config_resolution import RouteResolutionMixin
from tests.test_route_config_security import RouteSecurityMixin
from tests.test_route_config_support import RouteConfigSupport


class RouteGrammarTests(RouteGrammarMixin, RouteConfigSupport, unittest.TestCase):
    pass


class RouteSecurityTests(RouteSecurityMixin, RouteConfigSupport, unittest.TestCase):
    pass


class RouteResolutionTests(RouteResolutionMixin, RouteConfigSupport, unittest.TestCase):
    pass


class RouteProbeTests(RouteProbeMixin, RouteConfigSupport, unittest.TestCase):
    pass


if __name__ == "__main__":
    unittest.main()
