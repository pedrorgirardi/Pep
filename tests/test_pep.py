import sublime

from unittest import TestCase

import Pep.pep as pep


def scratch_view(append=None):
    view = sublime.active_window().new_file()
    view.set_scratch(True)

    if append:
        view.run_command("append", {"characters": append})

    return view


class TestAnalyzeViewCljKondo(TestCase):
    def test_analyze_view_clj_kondo_1(self):
        """
        Blank view.
        """

        view = None

        try:
            view = scratch_view("")

            clj_kondo_data = pep.analyze_view_clj_kondo(view)

            self.assertEqual(
                {
                    "namespace-definitions": [],
                    "namespace-usages": [],
                    "var-definitions": [],
                    "var-usages": [],
                    "locals": [],
                    "local-usages": [],
                    "keywords": [],
                },
                clj_kondo_data["analysis"],
            )

        finally:
            if view:
                view.close()

    def test_analyze_view_clj_kondo_2(self):
        """
        Findings & invalid syntax.
        """

        view = None

        try:
            view = scratch_view("(")

            clj_kondo_data = pep.analyze_view_clj_kondo(view)

            self.assertEqual(
                [
                    {
                        "filename": "-",
                        "row": 1,
                        "col": 1,
                        "level": "error",
                        "type": "syntax",
                        "message": "Found an opening ( with no matching )",
                    },
                    {
                        "filename": "-",
                        "row": 1,
                        "col": 2,
                        "level": "error",
                        "type": "syntax",
                        "message": "Expected a ) to match ( from line 1",
                    },
                ],
                clj_kondo_data["findings"],
            )

        finally:
            if view:
                view.close()


class TestIndexes(TestCase):
    def setUp(self):
        self.window = sublime.active_window()
        self.view = scratch_view()

    def tearDown(self):
        if self.view:
            self.view.close()

    def test_indexes(self):
        self.view.run_command(
            "append",
            {
                "characters": "(ns ns1 (:require [clojure.str :as str :refer [blank?]])) (def x 1)"
            },
        )

        analyzed = pep.analyze_view(self.view)

        self.assertEqual(True, analyzed)

        view_analysis_ = pep.view_analysis(self.view.id())

        # Namespace defintions.

        self.assertEqual(
            {
                "ns1": [
                    {
                        "filename": "-",
                        "row": 1,
                        "col": 1,
                        "name": "ns1",
                        "name-col": 5,
                        "name-end-col": 8,
                        "name-row": 1,
                        "name-end-row": 1,
                    }
                ]
            },
            pep.analysis_nindex(view_analysis_),
        )

        # Namespace usages.

        self.assertEqual(
            {
                "clojure.str": [
                    {
                        "filename": "-",
                        "row": 1,
                        "col": 20,
                        "name-row": 1,
                        "name-end-row": 1,
                        "name-col": 20,
                        "name-end-col": 31,
                        "alias-row": 1,
                        "alias-end-row": 1,
                        "alias-col": 36,
                        "alias-end-col": 39,
                        "alias": "str",
                        "from": "ns1",
                        "to": "clojure.str",
                    }
                ]
            },
            pep.analysis_nindex_usages(view_analysis_),
        )

        # Namespace definition by row.

        self.assertEqual(
            {
                1: [
                    {
                        "filename": "-",
                        "row": 1,
                        "col": 1,
                        "name": "ns1",
                        "name-col": 5,
                        "name-end-col": 8,
                        "name-row": 1,
                        "name-end-row": 1,
                    }
                ]
            },
            pep.analysis_nrn(view_analysis_),
        )

        # Namespace usages by row.

        self.assertEqual(
            {
                1: [
                    {
                        "filename": "-",
                        "row": 1,
                        "col": 20,
                        "name-row": 1,
                        "name-end-row": 1,
                        "name-col": 20,
                        "name-end-col": 31,
                        "alias-row": 1,
                        "alias-end-row": 1,
                        "alias": "str",
                        "alias-col": 36,
                        "alias-end-col": 39,
                        "from": "ns1",
                        "to": "clojure.str",
                    },
                    {
                        "filename": "-",
                        "row": 1,
                        "col": 20,
                        "name-row": 1,
                        "name-end-row": 1,
                        "name-col": 20,
                        "name-end-col": 31,
                        "alias-row": 1,
                        "alias-end-row": 1,
                        "alias": "str",
                        "alias-col": 36,
                        "alias-end-col": 39,
                        "from": "ns1",
                        "to": "clojure.str",
                    },
                ]
            },
            pep.analysis_nrn_usages(view_analysis_),
        )

        # Var definitions.

        self.assertEqual(
            {
                ("ns1", "x"): [
                    {
                        "filename": "-",
                        "row": 1,
                        "end-row": 1,
                        "col": 59,
                        "end-col": 68,
                        "name-row": 1,
                        "name-end-row": 1,
                        "name-col": 64,
                        "name-end-col": 65,
                        "ns": "ns1",
                        "name": "x",
                        "defined-by": "clojure.core/def",
                    }
                ]
            },
            pep.analysis_vindex(view_analysis_),
        )

        # Var usages.

        self.assertEqual(
            {
                ("clojure.str", "blank?"): [
                    {
                        "filename": "-",
                        "row": 1,
                        "end-row": 1,
                        "col": 48,
                        "end-col": 54,
                        "name-col": 48,
                        "name-end-col": 54,
                        "name-row": 1,
                        "name-end-row": 1,
                        "name": "blank?",
                        "from": "ns1",
                        "to": "clojure.str",
                        "refer": True,
                    }
                ],
                ("clojure.core", "def"): [
                    {
                        "filename": "-",
                        "row": 1,
                        "end-row": 1,
                        "col": 59,
                        "end-col": 68,
                        "name-col": 60,
                        "name-end-col": 63,
                        "name-row": 1,
                        "name-end-row": 1,
                        "arity": 2,
                        "fixed-arities": [1, 3, 2],
                        "name": "def",
                        "from": "ns1",
                        "to": "clojure.core",
                        "macro": True,
                    }
                ],
            },
            pep.analysis_vindex_usages(view_analysis_),
        )
