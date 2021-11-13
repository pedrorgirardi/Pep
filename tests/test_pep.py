import sublime

from unittest import TestCase

from Pep.pep import *

class TestPep(TestCase):

    def test_analysis_findings(self):
        self.assertEqual({}, analysis_findings({}))
        self.assertEqual({"foo": []}, analysis_findings({"findings": {"foo": []}}))