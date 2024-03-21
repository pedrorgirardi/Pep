import html
import inspect
import json
import os
import pathlib
import pprint
import re
import shlex
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import traceback
from typing import Any, Callable, List, Optional, Union
from zipfile import ZipFile

import sublime  # type: ignore
import sublime_plugin  # type: ignore

from .src import op, progress
from .src.error import PepSocketError

# Flags for creating/opening files in various ways.
# https://www.sublimetext.com/docs/api_reference.html#sublime.NewFileFlags

GOTO_DEFAULT_FLAGS = sublime.ENCODED_POSITION

GOTO_TRANSIENT_FLAGS = sublime.ENCODED_POSITION | sublime.TRANSIENT

GOTO_SIDE_BY_SIDE_FLAGS = (
    sublime.ENCODED_POSITION
    | sublime.SEMI_TRANSIENT
    | sublime.ADD_TO_SELECTION
    | sublime.CLEAR_TO_RIGHT
)


# Thingy types

TT_FINDING = "finding"
TT_KEYWORD = "keyword"
TT_SYMBOL = "symbol"
TT_LOCAL = "local"
TT_LOCAL_BINDING = "local_binding"
TT_LOCAL_USAGE = "local_usage"
TT_VAR_DEFINITION = "var_definition"
TT_VAR_USAGE = "var_usage"
TT_NAMESPACE_DEFINITION = "namespace_definition"
TT_NAMESPACE_USAGE = "namespace_usage"
TT_NAMESPACE_USAGE_ALIAS = "namespace_usage_alias"
TT_JAVA_CLASS_USAGE = "java_class_usage"

SEM_NS_DEF = "namespace-definitions"
SEM_VAR_DEF = "var-definitions"
SEM_LOCAL = "locals"

OUTPUT_PANEL_NAME = "pep"
OUTPUT_PANEL_NAME_PREFIXED = f"output.{OUTPUT_PANEL_NAME}"

HIGHLIGHTED_REGIONS_KEY = "pg_pep_highligths"
HIGHLIGHTED_STATUS_KEY = "pg_pep_highligths"

# Setting used to override the clj-kondo config for a view analysis.
SETTING_CLJ_KONDO_CONFIG = "pep_clj_kondo_config"

# Setting used to toggle a view's annotations.
SETTING_ANNOTATE_VIEW = "pep_annotate_view"

# Configuration shared by paths and view analysis - without a common configuration the index would be inconsistent.
CLJ_KONDO_VIEW_PATHS_ANALYSIS_CONFIG = "{:var-definitions true, :var-usages true, :arglists true, :locals true, :keywords true, :symbols true, :java-class-definitions false, :java-class-usages true, :java-member-definitions false, :instance-invocations true}"
CLJ_KONDO_CLASSPATH_ANALYSIS_CONFIG = "{:var-usages false :var-definitions {:shallow true} :arglists true :keywords true :java-class-definitions false}"

CLJ_KONDO_OUTPUT_JSON_CONFIG = "{:format :json :canonical-paths true}"

# Analysis reference: https://github.com/clj-kondo/clj-kondo/tree/master/analysis
CLJ_KONDO_VIEW_CONFIG = f"{{:analysis {CLJ_KONDO_VIEW_PATHS_ANALYSIS_CONFIG} :output {CLJ_KONDO_OUTPUT_JSON_CONFIG} }}"
CLJ_KONDO_PATHS_CONFIG = f"{{:skip-lint true :analysis {CLJ_KONDO_VIEW_PATHS_ANALYSIS_CONFIG} :output {CLJ_KONDO_OUTPUT_JSON_CONFIG} }}"
CLJ_KONDO_CLASSPATH_CONFIG = f"{{:skip-lint true :analysis {CLJ_KONDO_CLASSPATH_ANALYSIS_CONFIG} :output {CLJ_KONDO_OUTPUT_JSON_CONFIG} }}"


## -- Analysis Functions


def af_annotate(context, analysis):
    """
    Analysis Function to annotate view.

    Depends on setting to annotate view after analysis.
    """
    if view := context["view"]:
        if annotate_view_after_analysis(view.window()):
            annotate_view(view)


def af_annotate_on_save(context, analysis):
    """
    Analysis Function to annotate view on save.

    Depends on setting to annotate on save.
    """
    if view := context["view"]:
        if annotate_view_on_save(view.window()):
            annotate_view(view)


def af_highlight_thingy(context, analysis):
    """
    Analysis Function to highlight Thingy under the cursor.
    """
    if view := context["view"]:
        if automatically_highlight(view.window()):
            highlight_thingy(view)


def af_status_summary(context, analysis):
    """
    Analysis Function to show findings summary in the status bar.
    """
    if view := context["view"]:
        view.run_command("pg_pep_view_summary_status")


# Default functions to run after analysis.
DEFAULT_VIEW_ANALYSIS_FUNCTIONS = [
    af_highlight_thingy,
    af_status_summary,
]


# Mapping of filename to analysis data by semantic, e.g. var-definitions.
# (filename -> semantic -> list of 'thingies')
_index_ = {}

_view_analysis_ = {}

_classpath_analysis_ = {}


_client_socket_ = None


def clientsocket():
    global _client_socket_

    if _client_socket_:
        return _client_socket_

    _client_socket_ = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    _client_socket_.connect(op.server_default_path())

    return _client_socket_


def clientsocket_retry(retries=1):
    try:
        return clientsocket()
    except Exception:
        global _client_socket_
        _client_socket_ = None

        if retries > 0:
            print("Pep Error: Socket error; Retrying...", retries)

            return clientsocket_retry(retries=retries - 1)

        raise PepSocketError("Can't connect to Pep server.")


def with_clientsocket_retry(f: Callable[[socket.socket], Any]) -> Any:
    try:
        return f(clientsocket_retry())
    except PepSocketError:
        global _client_socket_
        _client_socket_ = None

        raise


def window_root_path(window: sublime.Window) -> Union[str, None]:
    if len(window.folders()) == 1:
        return window.folders()[0]


def project_index(project_path, not_found={}):
    """
    Mapping of filename to analysis data by semantic, e.g. var-definitions.
    """
    return _index_.get(project_path, not_found) if project_path else not_found


def update_project_index(project_path, index):
    project_index_ = project_index(project_path)

    global _index_
    _index_[project_path] = {**project_index_, **index}


def clear_project_index(project_path):
    global _index_
    _index_.pop(project_path, None)


def clear_cache():
    global _index_
    _index_ = {}

    global _view_analysis_
    _view_analysis_ = {}

    global _classpath_analysis_
    _classpath_analysis_ = {}


def set_classpath_analysis(project_path, analysis):
    """
    Updates analysis for project.
    """
    global _classpath_analysis_
    _classpath_analysis_[project_path] = analysis


def classpath_analysis(project_path, not_found={}):
    """
    Returns analysis for project.
    """
    global _classpath_analysis_
    return _classpath_analysis_.get(project_path, not_found)


def set_view_analysis(view_id, analysis):
    """
    Updates analysis for a particular view.
    """
    global _view_analysis_
    _view_analysis_[view_id] = analysis


def view_analysis(view_id, not_found={}):
    """
    Returns analysis for a particular view.
    """
    global _view_analysis_
    return _view_analysis_.get(view_id, not_found)


def paths_analysis(project_path, not_found={}):
    """
    Returns analysis for paths.

    TODO: Comments
    """
    project_index_ = project_index(project_path, not_found=not_found)

    if not project_index_:
        return not_found

    analysis = unify_analysis(project_index_)

    keyword_index_ = keyword_index(analysis)

    namespace_index_ = namespace_index(
        analysis,
        nrn=False,
        nrn_usages=False,
    )

    symbol_index_ = symbol_index(
        analysis,
        srn=False,
    )

    var_index_ = var_index(
        analysis,
        vrn=False,
        vrn_usages=False,
    )

    java_class_index_ = java_class_index(
        analysis,
        jrn_usages=False,
    )

    return {
        **keyword_index_,
        **namespace_index_,
        **symbol_index_,
        **var_index_,
        **java_class_index_,
    }


# -- Settings


def settings():
    return sublime.load_settings("Pep.sublime-settings")


def project_data(window) -> dict:
    """
    Returns Pep's project data - it's always a dict.

    Pep's project data is data about paths, classpath and settings.
    """
    if window:
        return window.project_data().get("pep", {}) if window.project_data() else {}
    else:
        return {}


def setting(window, k, not_found):
    """
    Get setting k from project's data or Pep settings.

    Returns not_found if setting k is is not set.
    """
    v = project_data(window).get(k)

    return v if v is not None else settings().get(k, not_found)


def is_debug(window):
    return setting(window, "debug", False)


def analysis_applicable_to(window):
    return setting(
        window,
        "analysis_applicable_to",
        [
            "Packages/Clojure/Clojure.sublime-syntax",
            "Packages/Clojure/ClojureScript.sublime-syntax",
        ],
    )


def analysis_delay(window):
    return setting(window, "analysis_delay", 0.6)


def automatically_highlight(window):
    return setting(window, "automatically_highlight", False)


def annotate_view_after_analysis(window):
    return setting(window, "annotate_view_after_analysis", False)


def annotate_view_on_save(window):
    return setting(window, "annotate_view_on_save", False)


def annotation_font_size(window):
    return setting(window, "annotation_font_size", "0.9em")


def analyze_scratch_view(window):
    return setting(window, "analyze_scratch_view", False)


# --- View Status Settings


def view_status_show_errors(window):
    return setting(window, "view_status_show_errors", True)


def view_status_show_warnings(window):
    return setting(window, "view_status_show_warnings", True)


def view_status_show_highlighted(window):
    return setting(window, "view_status_show_highlighted", False)


def view_status_show_highlighted_prefix(window):
    return setting(window, "view_status_show_highlighted_prefix", "")


def view_status_show_highlighted_suffix(window):
    return setting(window, "view_status_show_highlighted_suffix", "")


# ---


def startupinfo():
    # Hide the console window on Windows.
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        return startupinfo


def clj_kondo_path(window):
    cmd = setting(window, "clj_kondo_path", None)

    # From Popen docs:
    # For maximum reliability, use a fully qualified path for the executable.
    # To search for an unqualified name on PATH, use shutil.which().

    return shutil.which(cmd)


# -- Output Panel


def show_output_panel(window):
    window.run_command("show_panel", {"panel": OUTPUT_PANEL_NAME_PREFIXED})


def hide_output_panel(window):
    window.run_command("hide_panel", {"panel": OUTPUT_PANEL_NAME_PREFIXED})


def hide_active_output_panel(window):
    if window.active_panel() == OUTPUT_PANEL_NAME_PREFIXED:
        hide_output_panel(window)


def output_panel(window):
    return window.find_output_panel(OUTPUT_PANEL_NAME) or window.create_output_panel(
        OUTPUT_PANEL_NAME
    )


def replace_output_panel_content(panel, characters):
    panel.run_command("select_all")
    panel.run_command("left_delete")
    panel.run_command("insert", {"characters": characters})


# ---


def analysis_view_change_count(view):
    return view_analysis(view.id()).get("view_change_count")


def analysis_findings(analysis):
    return analysis.get("findings", {})


def analysis_summary(analysis):
    return analysis.get("summary", {})


def analysis_kindex(analysis):
    """
    Returns a dictionary of keywords by (namespace, name).

    'kindex' stands for 'keyword index'.
    """
    return analysis.get("kindex", {})


def analysis_sindex(analysis):
    """
    Returns a dictionary of symbols by symbol.

    'sindex' stands for 'symbol index'.
    """
    return analysis.get("sindex", {})


def analysis_krn(analysis):
    """
    Returns a dictionary of keywords by row.

    This index can be used to quicky find a keyword by row.

    'krn' stands for 'keyword row name'.
    """
    return analysis.get("krn", {})


def analysis_vindex(analysis):
    """
    Returns a dictionary of vars by (namespace, name).

    'vindex' stands for 'var index'.
    """
    return analysis.get("vindex", {})


def analysis_vindex_usages(analysis):
    """
    Returns a dictionary of Var usages by (namespace, name).

    'vindex_usages' stands for 'Var index'.
    """
    return analysis.get("vindex_usages", {})


def analysis_vrn(analysis):
    """
    Returns a dictionary of Vars by row.

    This index can be used to quicky find a Var definition by row.

    'vrn' stands for 'var row name'.
    """
    return analysis.get("vrn", {})


def analysis_vrn_usages(analysis):
    """
    Returns a dictionary of Var usages by row.

    This index can be used to quicky find a Var usage by row.

    'vrn' stands for 'var row name'.
    """
    return analysis.get("vrn_usages", {})


def analysis_jindex(analysis):
    """
    Returns a dictionary of Java class definitions indexed by name.

    'jindex' stands for 'java class definition index'.
    """
    return analysis.get("jindex", {})


def analysis_jrn_usages(analysis):
    """
    Returns a dictionary of Java class usages by row.

    This index can be used to quicky find a Java class usage by row.

    'jrn' stands for 'java row name'.
    """
    return analysis.get("jrn_usages", {})


def analysis_jindex_usages(analysis):
    """
    Returns a dictionary of Java class usages indexed by name - Class name to a set of class usages.

    'jindex_usages' stands for 'java class usages index'.
    """
    return analysis.get("jindex_usages", {})


def analysis_lindex(analysis):
    """
    Returns a dictionary of locals by ID.

    This index can be used to find a local in constant time if you know its ID.

    When finding usages from a usage itself, the first step is to find the usage,
    once you have found it, you can use its ID to find the local.

    Locals and usages have the same ID,
    so it's possible to corretale a usage with a local.

    'lindex' stands for 'local index'.
    """
    return analysis.get("lindex", {})


def analysis_lrn(analysis):
    """
    Returns a dictionary of locals by row.

    This index can be used to quicky find a local definition by row.

    Example: (let [a| 1] ...)

    'lrn' stands for 'local row name'.
    """
    return analysis.get("lrn", {})


def analysis_lrn_usages(analysis):
    """
    Returns a dictionary of local usages by row.

    This index can be used to quicky find a local usage by row.

    Example: (let [a 1] |a)

    'lrn' stands for 'local row name'.
    """
    return analysis.get("lrn_usages", {})


def analysis_nindex(analysis):
    """
    Returns a dictionary of namespace definition by name.

    'nindex' stands for 'Namespace index'.
    """
    return analysis.get("nindex", {})


def analysis_nindex_usages(analysis):
    """
    Returns a dictionary of namespace usages by name.

    'nindex' stands for 'namespace index'.
    """
    return analysis.get("nindex_usages", {})


def analysis_nrn(analysis):
    """
    Returns a dictionary of namespaces by row.
    """
    return analysis.get("nrn", {})


def analysis_nrn_usages(analysis):
    """
    Returns a dictionary of namespace usages by row.

    This index can be used to quicky find a namespace usage by row.

    'nrn' stands for 'namespace row name'.
    """
    return analysis.get("nrn_usages", {})


# ---


def namespace_definitions(analysis):
    """
    Returns a list of namespace definitions.
    """

    l = []

    for namespace_definitions in analysis_nindex(analysis).values():
        l.extend(namespace_definitions)

    return l


def namespace_usages(analysis):
    """
    Returns a list of namespace usages.
    """

    l = []

    for namespace_usages in analysis_nindex_usages(analysis).values():
        l.extend(namespace_usages)

    return l


def var_definitions(analysis):
    """
    Returns a list of var definitions.
    """

    l = []

    for var_definitions in analysis_vindex(analysis).values():
        l.extend(var_definitions)

    return l


def var_usages(analysis):
    """
    Returns a list of var_usage.
    """

    l = []

    for var_usages in analysis_vindex_usages(analysis).values():
        l.extend(var_usages)

    return l


def keyword_regs(analysis) -> List:
    """
    Returns a list of keyword where reg is not None.
    """
    l = []

    for keywords_ in analysis_kindex(analysis).values():
        for keyword_ in keywords_:
            if keyword_.get("reg"):
                l.append(keyword_)

    return l


def recursive_usage(thingy_usage):
    usage_from = thingy_usage.get("from")
    usage_to = thingy_usage.get("to")

    usage_name = thingy_usage.get("name")
    usage_from_var = thingy_usage.get("from-var")

    is_same_ns = usage_from == usage_to
    is_same_var = usage_name == usage_from_var

    return is_same_ns and is_same_var


# ---


def namespace_index(
    analysis,
    nindex=True,
    nindex_usages=True,
    nrn=True,
    nrn_usages=True,
):
    """
    Index namespace definitions and usages.

    Definitions are indexed by name and file extension.

    Usages are indexed by name.

    Returns dict with keys 'nindex', 'nindex_usages', 'nrn', 'nrn_usages'.
    """

    namespace_definitions = analysis.get("namespace-definitions", [])

    # Namespace definitions indexed by name.
    nindex_ = {}

    # Namespace definitions indexed by row.
    nrn_ = {}

    if nindex or nrn:
        for namespace_definition in namespace_definitions:
            # Ignore data missing row and col - it seems like a clj-kondo bug.
            if namespace_definition.get("row") and namespace_definition.get("col"):
                namespace_definition = {
                    **namespace_definition,
                    "_semantic": TT_NAMESPACE_DEFINITION,
                }

                if nindex:
                    name = namespace_definition.get("name")

                    nindex_.setdefault(name, []).append(namespace_definition)

                if nrn:
                    name_row = namespace_definition.get("name-row")

                    nrn_.setdefault(name_row, []).append(namespace_definition)

    # Namespace usages indexed by name.
    nindex_usages_ = {}

    # Var usages indexed by row.
    nrn_usages_ = {}

    if nindex_usages or nrn_usages:
        for namespace_usage in analysis.get("namespace-usages", []):
            # Ignore data missing row and col - it seems like a clj-kondo bug.
            if namespace_usage.get("row") and namespace_usage.get("col"):
                namespace_usage = {
                    **namespace_usage,
                    "_semantic": TT_NAMESPACE_USAGE,
                }

                if nindex_usages:
                    name = namespace_usage.get("to")

                    nindex_usages_.setdefault(name, []).append(namespace_usage)

                if nrn_usages:
                    name_row = namespace_usage.get("name-row")

                    nrn_usages_.setdefault(name_row, []).append(namespace_usage)

                    # Index alias row (in case there's one).
                    # Note: It's possible to have both the name and alias in the same row.
                    if namespace_usage.get("alias"):
                        alias_row = namespace_usage.get("alias-row")

                        nrn_usages_.setdefault(alias_row, []).append(namespace_usage)

    return {
        "nindex": nindex_,
        "nindex_usages": nindex_usages_,
        "nrn": nrn_,
        "nrn_usages": nrn_usages_,
    }


def local_index(
    analysis,
    lindex=True,
    lindex_usages=True,
    lrn=True,
    lrn_usages=True,
):
    """
    Index local definitions and usages.

    Definitions and usages are indexed by id.

    Returns dict with keys 'lindex', 'lindex_usages', 'lrn', 'lrn_usages'.
    """

    # Locals indexed by row.
    lrn_ = {}

    # Locals indexed by ID.
    lindex_ = {}

    if lindex or lrn:
        for local_binding in analysis.get("locals", []):
            # Ignore data missing row and col - it seems like a clj-kondo bug.
            if local_binding.get("row") and local_binding.get("col"):
                local_binding = {
                    **local_binding,
                    "_semantic": TT_LOCAL,
                }

                id = local_binding.get("id")
                row = local_binding.get("row")

                if lrn:
                    lrn_.setdefault(row, []).append(local_binding)

                if lindex:
                    lindex_[id] = local_binding

    # Local usages indexed by ID - local binding ID to a set of local usages.
    lindex_usages_ = {}

    # Local usages indexed by row.
    lrn_usages_ = {}

    if lindex_usages or lrn_usages:
        for local_usage in analysis.get("local-usages", []):
            # Ignore data missing row and col - it seems like a clj-kondo bug.
            if local_usage.get("row") and local_usage.get("col"):
                local_usage = {
                    **local_usage,
                    "_semantic": TT_LOCAL_USAGE,
                }

                id = local_usage.get("id")
                name_row = local_usage.get("name-row")

                if lindex_usages:
                    lindex_usages_.setdefault(id, []).append(local_usage)

                if lrn_usages:
                    lrn_usages_.setdefault(name_row, []).append(local_usage)

    return {
        "lindex": lindex_,
        "lindex_usages": lindex_usages_,
        "lrn": lrn_,
        "lrn_usages": lrn_usages_,
    }


def keyword_index(
    analysis,
    kindex=True,
    krn=True,
):
    # Keywords indexed by name - tuple of namespace and name.
    kindex_ = {}

    # Keywords indexed by row.
    krn_ = {}

    if kindex or krn:
        for keyword in analysis.get("keywords", []):
            # Ignore data missing row and col - it seems like a clj-kondo bug.
            if keyword.get("row") and keyword.get("col"):
                keyword = {
                    **keyword,
                    "_semantic": TT_KEYWORD,
                }

                ns = keyword.get("ns")
                name = keyword.get("name")
                row = keyword.get("row")

                if kindex:
                    kindex_.setdefault((ns, name), []).append(keyword)

                if krn:
                    krn_.setdefault(row, []).append(keyword)

    return {
        "kindex": kindex_,
        "krn": krn_,
    }


def var_index(
    analysis,
    vindex=True,
    vindex_usages=True,
    vrn=True,
    vrn_usages=True,
):
    # Vars indexed by row.
    vrn_ = {}

    # Vars indexed by namespace and name.
    vindex_ = {}

    if vindex or vrn:
        for var_definition in analysis.get("var-definitions", []):
            # Ignore data missing row and col - it seems like a clj-kondo bug.
            if var_definition.get("row") and var_definition.get("col"):
                var_definition = {
                    **var_definition,
                    "_semantic": TT_VAR_DEFINITION,
                }

                if vindex:
                    ns = var_definition.get("ns")

                    name = var_definition.get("name")

                    vindex_.setdefault((ns, name), []).append(var_definition)

                if vrn:
                    name_row = var_definition.get("name-row")

                    vrn_.setdefault(name_row, []).append(var_definition)

    # Var usages indexed by row.
    vrn_usages_ = {}

    # Var usages indexed by name - var name to a set of var usages.
    vindex_usages_ = {}

    if vindex_usages or vrn_usages:
        for var_usage in analysis.get("var-usages", []):
            # Ignore data missing row and col - it seems like a clj-kondo bug.
            if var_usage.get("row") and var_usage.get("col"):
                var_usage = {
                    **var_usage,
                    "_semantic": TT_VAR_USAGE,
                }

                if vindex_usages:
                    ns = var_usage.get("to")

                    name = var_usage.get("name")

                    vindex_usages_.setdefault((ns, name), []).append(var_usage)

                if vrn_usages:
                    name_row = var_usage.get("name-row")

                    vrn_usages_.setdefault(name_row, []).append(var_usage)

    return {
        "vindex": vindex_,
        "vrn": vrn_,
        "vindex_usages": vindex_usages_,
        "vrn_usages": vrn_usages_,
    }


def symbol_index(
    analysis,
    sindex=True,
    srn=True,
):
    # Symbols indexed by row.
    srn_ = {}

    # Symbols indexed by symbol.
    sindex_ = {}

    if sindex or srn:
        for sym in analysis.get("symbols", []):
            # Ignore data missing row and col.
            if sym.get("row") and sym.get("col"):
                sym = {
                    **sym,
                    "_semantic": TT_SYMBOL,
                }

                if sindex:
                    sindex_.setdefault(sym.get("symbol"), []).append(sym)

                if srn:
                    srn_.setdefault(sym.get("row"), []).append(sym)

    return {
        "sindex": sindex_,
        "srn": srn_,
    }


def java_class_index(
    analysis,
    jindex=True,
    jindex_usages=True,
    jrn_usages=True,
):
    """
    Index Java class definitions and usages.

    Definitions and usages are indexed by class name.

    Returns dict with keys 'jindex', 'jindex_usages', 'jrn_usages'.
    """

    # Java class definition indexed by class name.
    jindex_ = {}

    if jindex:
        for java_class_definition in analysis.get("java-class-definitions", []):
            if java_class_definition.get("row") and java_class_definition.get("col"):
                jindex_[java_class_definition.get("class")] = java_class_definition

    # Java class usages indexed by row.
    jrn_usages_ = {}

    # Java class usages indexed by name - Class name to a set of class usages.
    jindex_usages_ = {}

    if jindex_usages or jrn_usages:
        for java_class_usage in analysis.get("java-class-usages", []):
            if java_class_usage.get("row") and java_class_usage.get("col"):
                java_class_usage = {
                    **java_class_usage,
                    "_semantic": TT_JAVA_CLASS_USAGE,
                }

                if jindex_usages:
                    jindex_usages_.setdefault(java_class_usage.get("class"), []).append(
                        java_class_usage
                    )

                if jrn_usages:
                    jrn_usages_.setdefault(java_class_usage.get("row"), []).append(
                        java_class_usage
                    )

    return {
        "jindex": jindex_,
        "jindex_usages": jindex_usages_,
        "jrn_usages": jrn_usages_,
    }


# ---


def file_extension(filename):
    if filename:
        return pathlib.Path(filename).suffix


def remove_empty_rows(thingies):
    """
    For some reason, maybe a clj-kondo bug, a Var usage might have a None row.

    This function is suitable for any thingy data - not only Var usages.
    """
    return [thingy_data for thingy_data in thingies if thingy_data["row"] is not None]


def staled_analysis(view):
    """
    Returns True if view was modified since last analysis.
    """
    return view.change_count() != analysis_view_change_count(view)


def view_navigation(view_state):
    return view_state.get("navigation", {})


def set_view_navigation(view_state, navigation):
    view_state["navigation"] = navigation


def project_path(window) -> Optional[str]:
    return window.extract_variables().get("project_path") if window else None


def project_base_name(window) -> Optional[str]:
    return window.extract_variables().get("project_base_name") if window else None


def window_project(window) -> Optional[str]:
    return window.extract_variables().get("project") if window else None


def project_data_classpath(window) -> Optional[str]:
    """
    Example:

    ["clojure", "-Spath"]
    """
    return project_data(window).get("classpath")


def project_data_paths(window) -> Optional[str]:
    """
    Example:

    ["src", "test"]
    """
    return project_data(window).get("paths")


def symbol_namespace(thingy) -> Optional[str]:
    symbol_split = thingy.get("symbol").split("/")

    if len(symbol_split) > 1:
        return symbol_split[0]
    else:
        return None


def symbol_name(thingy) -> str:
    symbol_split = thingy.get("symbol").split("/")

    if len(symbol_split) > 1:
        return symbol_split[1]
    else:
        return symbol_split[0]


# ---

# Copied from https://github.com/eerohele/Tutkain


def htmlify(text):
    if text:
        return re.sub(r"\n", "<br/>", inspect.cleandoc(html.escape(text)))
    else:
        return ""


def open_jar(filename, f):
    """
    Open JAR `filename` and call `f` with the path of the temporary file.
    """

    dep_jar, dep_filepath = filename.split(":")

    with ZipFile(dep_jar) as jar:
        with jar.open(dep_filepath) as jar_file:
            tmp_path = os.path.join(tempfile.gettempdir(), dep_filepath)

            # Create all parent directories of the temporary file:
            os.makedirs(os.path.dirname(tmp_path), exist_ok=True)

            with open(tmp_path, "w") as tmp_file:
                tmp_file.write(jar_file.read().decode())

            f(tmp_path)


def goto(window, location, flags=sublime.ENCODED_POSITION):
    if location:
        filename = location["filename"]
        line = location["line"]
        column = location["column"]

        if ".jar:" in filename:

            def window_open_file(filename):
                view = window.open_file(f"{filename}:{line}:{column}", flags=flags)
                view.set_scratch(True)
                view.set_read_only(True)

            if is_debug(window):
                print(f"Pep Debug: Goto JAR {filename}:{line}:{column}")

            open_jar(filename, window_open_file)

        else:
            window.open_file(f"{filename}:{line}:{column}", flags=flags)


def thingy_extension(thingy_data) -> Optional[str]:
    if filename := pathlib.Path(thingy_data.get("filename")):
        return filename.suffix.replace(".", "")


def thingy_lang(thingy_data) -> Optional[str]:
    if lang := thingy_data.get("lang"):
        return lang

    else:
        return thingy_extension(thingy_data)


def thingy_dedupe(thingy_data_list) -> List:
    return list(
        {
            (
                thingy_data["filename"],
                thingy_data["row"],
                thingy_data["col"],
            ): thingy_data
            for thingy_data in thingy_data_list
            if thingy_data.get("filename")
            and thingy_data.get("row")
            and thingy_data.get("col")
        }.values()
    )


def namespace_quick_panel_item(thingy_data, opts={}):
    """
    Returns a QuickPanelItem for a namespace, usage or definition, thingy.
    """

    trigger = thingy_data.get("name")

    if opts.get("show_row_col"):
        trigger = f"{trigger}:{thingy_data.get('row')}:{thingy_data.get('col')}"

    details = thingy_data.get("filename", "") if opts.get("show_filename") else ""

    return sublime.QuickPanelItem(
        trigger,
        details=details,
    )


def namespace_usage_quick_panel_item(thingy_data, opts={}):
    """
    Returns a QuickPanelItem for a namespace, usage or definition, thingy.
    """

    trigger = thingy_data.get("from")

    if opts.get("show_row_col"):
        trigger = f"{trigger}:{thingy_data.get('row')}:{thingy_data.get('col')}"

    details = thingy_data.get("filename", "") if opts.get("show_filename") else ""

    return sublime.QuickPanelItem(
        trigger,
        details=details,
    )


def symbol_quick_panel_item(thingy_data, opts={}):
    """
    Returns a QuickPanelItem for a symbol thingy.
    """
    trigger = thingy_data.get("symbol", "")

    if opts.get("show_row_col"):
        trigger = f"{trigger}:{thingy_data.get('row')}:{thingy_data.get('col')}"

    details = ""

    if opts.get("show_filename"):
        details = thingy_data.get("filename", "")

    return sublime.QuickPanelItem(
        trigger,
        details=details,
    )


def var_quick_panel_item(thingy_data, opts={}):
    """
    Returns a QuickPanelItem for a var, definition or usage, thingy.
    """

    var_namespace = thingy_data.get("ns", thingy_data.get("to", ""))
    var_name = thingy_data.get("name", "")
    var_arglist = thingy_data.get("arglist-strs", [])

    trigger = f"{var_namespace}/{var_name}" if opts.get("show_namespace") else var_name

    if opts.get("show_row_col"):
        trigger = f"{trigger}:{thingy_data.get('row')}:{thingy_data.get('col')}"

    details = ""

    if opts.get("show_filename"):
        details = thingy_data.get("filename", "")

    annotation = " ".join(var_arglist)

    return sublime.QuickPanelItem(
        trigger,
        details=details,
        annotation=annotation,
    )


def var_usage_quick_panel_item(thingy_data, opts={}):
    """
    Returns a QuickPanelItem for a Var usage.
    """
    var_namespace = thingy_data.get("from", "")
    var_name = thingy_data.get("from-var", "")

    trigger = ""

    if opts.get("show_namespace"):
        trigger = f"{var_namespace}/{var_name}" if var_name else var_namespace
    else:
        trigger = var_name

    if opts.get("show_row_col"):
        trigger = f"{trigger}:{thingy_data.get('row')}:{thingy_data.get('col')}"

    details = ""

    if opts.get("show_filename"):
        details = thingy_data.get("filename", "")

    return sublime.QuickPanelItem(
        trigger,
        details=details,
    )


def local_usage_quick_panel_item(thingy_data, opts={}):
    """
    Returns a QuickPanelItem for a local usage.
    """

    trigger = f"{thingy_data.get('row')}:{thingy_data.get('col')}"

    details = thingy_data.get("filename", "")

    return sublime.QuickPanelItem(
        trigger,
        details=details,
    )


def finding_quick_panel_item(thingy_data, opts={}):
    return sublime.QuickPanelItem(
        thingy_data["message"],
        annotation=thingy_data["type"],
        kind=(
            (sublime.KIND_ID_COLOR_REDISH, "e", "e")
            if thingy_data["level"] == "error"
            else (sublime.KIND_ID_COLOR_ORANGISH, "w", "w")
        ),
    )


def keyword_quick_panel_item(thingy_data, opts={}):
    """
    Returns a QuickPanelItem for a keyword thingy.
    """

    trigger = ""

    if namespace := thingy_data.get("ns"):
        trigger = f":{namespace}/{thingy_data.get('name')}"
    else:
        trigger = f":{thingy_data.get('name')}"

    if opts.get("show_row_col"):
        trigger = f"{trigger}:{thingy_data.get('row')}:{thingy_data.get('col')}"

    details = thingy_data.get("filename") if opts.get("show_filename") else ""

    annotation = thingy_data.get("reg", "")

    return sublime.QuickPanelItem(
        trigger,
        details=details,
        annotation=annotation,
    )


def thingy_quick_panel_item(thingy, opts={}) -> Optional[sublime.QuickPanelItem]:
    semantic = thingy["_semantic"]

    if semantic == TT_NAMESPACE_DEFINITION or semantic == SEM_NS_DEF:
        return namespace_quick_panel_item(thingy, opts)

    elif semantic == TT_NAMESPACE_USAGE:
        return namespace_usage_quick_panel_item(thingy, opts)

    elif semantic == TT_VAR_DEFINITION or semantic == SEM_VAR_DEF:
        return var_quick_panel_item(thingy, opts)

    elif semantic == TT_VAR_USAGE:
        return var_usage_quick_panel_item(thingy, opts)

    elif semantic == TT_LOCAL_USAGE or semantic == SEM_LOCAL:
        return local_usage_quick_panel_item(thingy, opts)

    elif semantic == TT_KEYWORD:
        return keyword_quick_panel_item(thingy, opts)

    elif semantic == TT_SYMBOL:
        return symbol_quick_panel_item(thingy, opts)

    elif semantic == TT_FINDING:
        return finding_quick_panel_item(thingy, opts)


def goto_thingy(
    window,
    thingy_list,
    goto_on_highlight=False,
    goto_side_by_side=False,
    quick_panel_item_opts={
        "show_namespace": True,
        "show_filename": True,
        "show_row_col": False,
    },
):
    """
    Show a Quick Panel to select a thingy to goto.

    Items is a list of dict with keys "thingy_type", "thingy_data" and "quick_panel_item".
    """

    # Restore active view, its selection, and viewport position - if there's an active view.

    if not thingy_list:
        return

    initial_view = window.active_view()

    initial_regions = [region for region in initial_view.sel()] if initial_view else []

    initial_viewport_position = (
        initial_view.viewport_position() if initial_view else None
    )

    def location(index):
        return thingy_location(thingy_list[index])

    def on_highlight(index):
        goto(
            window,
            location(index),
            flags=GOTO_TRANSIENT_FLAGS,
        )

    def on_select(index):
        if index == -1:
            if initial_view:
                initial_view.sel().clear()

                for region in initial_regions:
                    initial_view.sel().add(region)

                window.focus_view(initial_view)

                initial_view.set_viewport_position(initial_viewport_position, True)
        else:
            goto(
                window,
                location(index),
                GOTO_SIDE_BY_SIDE_FLAGS if goto_side_by_side else GOTO_DEFAULT_FLAGS,
            )

    quick_panel_items = [
        thingy_quick_panel_item(
            thingy,
            opts=quick_panel_item_opts,
        )
        for thingy in thingy_list
    ]

    window.show_quick_panel(
        quick_panel_items,
        on_select,
        on_highlight=on_highlight if goto_on_highlight else None,
    )


## ---


def set_view_name(view, name):
    if view:
        if view.is_loading():
            sublime.set_timeout(lambda: set_view_name(view, name), 100)
        else:
            view.set_name(name)


def view_text(view, region=None):
    if region:
        return view.substr(region)
    else:
        return view.substr(sublime.Region(0, view.size()))


def project_classpath(window):
    """
    Returns the project classpath, or None if a classpath setting does not exist.

    It reads a custom "pep classpath" setting in the project file.

    Example.sublime-project:

    {
        ...

        "pep": {
            "classpath": ["clojure", "-Spath"]
        }
    }
    """
    if classpath := project_data_classpath(window):
        classpath = classpath if isinstance(classpath, list) else shlex.split(classpath)

        classpath_completed_process = subprocess.run(
            classpath,
            cwd=project_path(window),
            text=True,
            capture_output=True,
        )

        classpath_completed_process.check_returncode()

        return classpath_completed_process.stdout


## ---


def analyze_view(view, afs=DEFAULT_VIEW_ANALYSIS_FUNCTIONS):
    # Change count right before analyzing the view.
    # This will be stored in the analysis.
    view_change_count = view.change_count()

    window = view.window()

    view_file_name = view.file_name()

    project_file_name = window.project_file_name() if window else None

    # Setting the working directory is important because of clj-kondo's cache.
    cwd = None

    if project_file_name:
        cwd = os.path.dirname(project_file_name)
    elif view_file_name:
        cwd = os.path.dirname(view_file_name)

    analysis_config = (
        view.settings().get(SETTING_CLJ_KONDO_CONFIG) or CLJ_KONDO_VIEW_CONFIG
    )

    # --lint <file>: a file can either be a normal file, directory or classpath.
    # In the case of a directory or classpath, only .clj, .cljs and .cljc will be processed.
    # Use - as filename for reading from stdin.

    # --filename <file>: in case stdin is used for linting, use this to set the reported filename.

    analysis_subprocess_args = [
        clj_kondo_path(window),
        "--config",
        analysis_config,
        "--lint",
        "-",
        "--filename",
        view_file_name or "-",
    ]

    analysis_completed_process = subprocess.run(
        analysis_subprocess_args,
        cwd=cwd,
        text=True,
        capture_output=True,
        startupinfo=startupinfo(),
        input=view_text(view),
    )

    clj_kondo_data = None

    try:
        clj_kondo_data = json.loads(analysis_completed_process.stdout)
    except Exception:
        clj_kondo_data = {}

    analysis = clj_kondo_data.get("analysis", {})

    namespace_index_ = namespace_index(analysis)

    var_index_ = var_index(analysis)

    java_class_index_ = java_class_index(analysis)

    keyword_index_ = keyword_index(analysis)

    symbol_index_ = symbol_index(analysis)

    local_index_ = local_index(analysis)

    findings_ = [
        {**finding, "_semantic": TT_FINDING}
        for finding in clj_kondo_data.get("findings", [])
    ]

    view_analysis_ = {
        **namespace_index_,
        **var_index_,
        **java_class_index_,
        **keyword_index_,
        **symbol_index_,
        **local_index_,
        "view_change_count": view_change_count,
        "findings": findings_,
        "summary": clj_kondo_data.get("summary", {}),
    }

    set_view_analysis(view.id(), view_analysis_)

    # Update index for view - analysis for a single file (view).
    if project_path_ := project_path(window):
        if file_name := view.buffer().file_name():
            # Don't index non-project files.
            if pathlib.Path(project_path_) in pathlib.Path(file_name).parents:
                update_project_index(project_path_, index_analysis(analysis))

    # Call Analysis Function(s) for side effects.
    for f in afs:
        context = {
            "scope": "view",
            "view": view,
        }

        f(context, view_analysis_)

    return True


def analyze_view_async(view, afs=DEFAULT_VIEW_ANALYSIS_FUNCTIONS):
    threading.Thread(target=lambda: analyze_view(view, afs=afs), daemon=True).start()


def analyze_view_v2(view):
    def handle_response(root_path, response):
        if error := response.get("error"):
            print("Pep Error:", error)

            return

        pprint.pprint(response)

        diagnostics = response.get("success", {}).get("diagnostics", {})

        annotate_view_v2(view, diagnostics)

    def run_():
        try:
            # TODO: It doesn't seem right to default to the first folder.
            root_path = view.window().folders()[0]

            response = with_clientsocket_retry(
                lambda c: op.analyze_text(
                    c,
                    root_path=root_path,
                    text=view_text(view),
                    filename=view.file_name() or f"unnamed_{view.id()}.clj",
                )
            )

            sublime.set_timeout(
                lambda: handle_response(root_path, response),
                0,
            )
        except Exception:
            print("Pep Error:", traceback.format_exc())

    threading.Thread(target=run_).start()


def analyze_classpath(window):
    """
    Analyze classpath to create indexes for var and namespace definitions.
    """

    if classpath := project_classpath(window):
        t0 = time.time()

        sublime.status_message("Analyzing classpath...")

        if is_debug(window):
            print(f"Pep Debug: Analyzing classpath... {window_project(window)}")

        # Analysis doesn't work without a .clj-kondo cache directory:
        clj_kondo_cache_directory = os.path.join(project_path(window), ".clj-kondo")

        if not os.path.exists(clj_kondo_cache_directory):
            os.makedirs(clj_kondo_cache_directory)

        analysis_subprocess_args = [
            clj_kondo_path(window),
            "--config",
            CLJ_KONDO_CLASSPATH_CONFIG,
            "--parallel",
            "--lint",
            classpath,
        ]

        analysis_completed_process = subprocess.run(
            analysis_subprocess_args,
            cwd=project_path(window),
            text=True,
            capture_output=True,
            startupinfo=startupinfo(),
        )

        output = None

        try:
            output = json.loads(analysis_completed_process.stdout)
        except Exception:
            output = {}

        analysis = output.get("analysis", {})

        keyword_index_ = keyword_index(
            analysis,
            krn=False,
        )

        # There's no need to index namespace usages in the classpath.
        namespace_index_ = namespace_index(
            analysis,
            nindex_usages=False,
            nrn=False,
            nrn_usages=False,
        )

        # There's no need to index var usages in the classpath.
        var_index_ = var_index(
            analysis,
            vindex_usages=False,
            vrn=False,
            vrn_usages=False,
        )

        # There's no need to index Java class usages in the classpath.
        java_class_index_ = java_class_index(
            analysis,
            jindex_usages=False,
            jrn_usages=False,
        )

        # Check if there's still a project_path - user might close the project before.
        if project_path_ := project_path(window):
            set_classpath_analysis(
                project_path_,
                {
                    **java_class_index_,
                    **keyword_index_,
                    **namespace_index_,
                    **var_index_,
                },
            )

            if is_debug(window):
                print(
                    f"Pep Debug: Classpath analysis is completed; {window_project(window)} [{time.time() - t0:,.2f} seconds]"
                )

        return True

    return False


def analyze_classpath_async(window):
    threading.Thread(target=lambda: analyze_classpath(window), daemon=True).start()


def analyze_paths(window):
    """
    Analyze paths to create indexes for var and namespace definitions, and keywords.
    """

    if paths := project_data_paths(window):
        t0 = time.time()

        path_separator = ";" if os.name == "nt" else ":"

        paths = path_separator.join(paths)

        sublime.status_message("Analyzing paths...")

        if is_debug(window):
            print(f"Pep Debug: Analyzing paths... {window_project(window)}")

        # Analysis doesn't work without a .clj-kondo cache directory:
        clj_kondo_cache_directory = os.path.join(project_path(window), ".clj-kondo")

        if not os.path.exists(clj_kondo_cache_directory):
            os.makedirs(clj_kondo_cache_directory)

        analysis_subprocess_args = [
            clj_kondo_path(window),
            "--config",
            CLJ_KONDO_PATHS_CONFIG,
            "--parallel",
            "--lint",
            paths,
        ]

        analysis_completed_process = subprocess.run(
            analysis_subprocess_args,
            cwd=project_path(window),
            text=True,
            capture_output=True,
            startupinfo=startupinfo(),
        )

        output = None

        try:
            output = json.loads(analysis_completed_process.stdout)
        except Exception:
            output = {}

        analysis = output.get("analysis", {})

        # Check if there's still a project_path - user might close the project before.
        if project_path_ := project_path(window):
            # Update index for paths - analysis for files in the project.
            update_project_index(
                project_path_,
                index_analysis(analysis),
            )

            if is_debug(window):
                print(
                    f"Pep Debug: Paths analysis is completed; {window_project(window)} [{time.time() - t0:,.2f} seconds]"
                )


def analyze_paths_async(window):
    threading.Thread(target=lambda: analyze_paths(window), daemon=True).start()


def index_analysis(analysis: dict) -> dict:
    """
    Analyze paths to create indexes for var and namespace definitions, and keywords.

    Semantic is one of:
      - namespace-definitions
      - namespace-usages
      - var-definitions
      - var-usages
      - locals
      - local-usages
      - keywords
      - java-class-usages

    TODO: Comments
    """

    index = {}

    for semantic, thingies in analysis.items():
        for thingy in thingies:
            filename = thingy["filename"]

            index.setdefault(filename, {}).setdefault(semantic, []).append(thingy)

    return index


def unify_analysis(index: dict) -> dict:
    """
    TODO: Comments
    """
    analysis = {}

    for _, analysis_ in index.items():
        for semantic, thingies in analysis_.items():
            analysis.setdefault(semantic, []).extend(thingies)

    return analysis


## ---


def erase_analysis_regions(view):
    view.erase_regions("pg_pep_analysis_error")
    view.erase_regions("pg_pep_analysis_warning")


# ---


def thingy_to_region(view, thingy) -> sublime.Region:
    """
    Returns Region for `thingy`.
    """

    row_start = thingy.get("name-row", thingy.get("row"))
    col_start = thingy.get("name-col", thingy.get("col"))

    row_end = thingy.get("name-end-row", thingy.get("end-row"))
    col_end = thingy.get("name-end-col", thingy.get("end-col"))

    start_point = view.text_point(row_start - 1, col_start - 1)
    end_point = view.text_point(row_end - 1, col_end - 1)

    return sublime.Region(start_point, end_point)


def keyword_region(view, thingy) -> sublime.Region:
    """
    Returns Region for keyword.
    """

    return thingy_to_region(view, thingy)


def symbol_region(view, thingy) -> sublime.Region:
    """
    Returns Region for symbol.
    """
    return thingy_to_region(view, thingy)


def namespace_definition_region(view, namespace_definition):
    """
    Returns a Region of a namespace definition.
    """

    return thingy_to_region(view, namespace_definition)


def namespace_usage_region(view, namespace_usage):
    """
    Returns a Region of a namespace usage.
    """

    return thingy_to_region(view, namespace_usage)


def namespace_usage_alias_region(view, namespace_usage):
    """
    Returns a Region of a namespace usage.
    """

    if namespace_usage.get("alias"):
        row_start = namespace_usage.get("alias-row")
        col_start = namespace_usage.get("alias-col")

        row_end = namespace_usage.get("alias-end-row")
        col_end = namespace_usage.get("alias-end-col")

        start_point = view.text_point(row_start - 1, col_start - 1)
        end_point = view.text_point(row_end - 1, col_end - 1)

        return sublime.Region(start_point, end_point)


def local_usage_region(view, local_usage):
    """
    Returns the Region of a local usage.
    """

    return thingy_to_region(view, local_usage)


def local_binding_region(view, local_binding):
    """
    Returns the Region of a local binding.
    """

    return thingy_to_region(view, local_binding)


def var_definition_region(view, var_definition):
    """
    Returns the Region of a Var definition.
    """

    return thingy_to_region(view, var_definition)


def var_usage_region(view, var_usage):
    """
    Returns the Region of a Var usage.
    """

    return thingy_to_region(view, var_usage)


def java_class_usage_region(view, java_class_usage):
    """
    Returns the Region of a Java class usage.
    """

    return thingy_to_region(view, java_class_usage)


def var_usage_namespace_region(view, var_usage):
    """
    Returns the namespace Region of var_usage, or None.

    For some (odd) reason, a var_usage might not have name row & col.
    """

    try:
        name_row_start = var_usage["name-row"]
        name_col_start = var_usage["name-col"]

        name_row_end = var_usage["name-end-row"]
        name_col_end = var_usage["name-end-col"]

        alias = var_usage.get("alias")

        # If a var doesn't have an alias, its name is the region.
        # But if a var has an alias, alias is the region.
        name_start_point = view.text_point(name_row_start - 1, name_col_start - 1)
        name_end_point = (
            name_start_point + len(alias)
            if alias
            else view.text_point(name_row_end - 1, name_col_end - 1)
        )

        return sublime.Region(name_start_point, name_end_point)
    except Exception:
        return None


def thingy_region(view, thingy):
    thingy_type, _, thingy_data = thingy

    if thingy_type == TT_KEYWORD:
        return keyword_region(view, thingy_data)

    elif thingy_type == TT_SYMBOL:
        return symbol_region(view, thingy_data)

    elif thingy_type == TT_LOCAL_BINDING:
        return local_binding_region(view, thingy_data)

    elif thingy_type == TT_LOCAL_USAGE:
        return local_binding_region(view, thingy_data)

    elif thingy_type == TT_VAR_DEFINITION:
        return var_definition_region(view, thingy_data)

    elif thingy_type == TT_VAR_USAGE:
        return var_usage_region(view, thingy_data)

    elif thingy_type == TT_JAVA_CLASS_USAGE:
        return java_class_usage_region(view, thingy_data)

    elif thingy_type == TT_NAMESPACE_DEFINITION:
        return namespace_definition_region(view, thingy_data)

    elif thingy_type == TT_NAMESPACE_USAGE:
        return namespace_usage_region(view, thingy_data)

    elif thingy_type == TT_NAMESPACE_USAGE_ALIAS:
        return namespace_usage_alias_region(view, thingy_data)


# ---


def keyword_in_region(view, krn, region):
    """
    Try to find a keyword in region using the krn index.
    """

    region_begin_row, _ = view.rowcol(region.begin())

    keywords = krn.get(region_begin_row + 1, [])

    for keyword in keywords:
        _region = keyword_region(view, keyword)

        if _region.contains(region):
            return (_region, keyword)


def symbol_in_region(view, srn, region):
    """
    Try to find a symbol in region using the srn index.
    """

    region_begin_row, _ = view.rowcol(region.begin())

    symbols = srn.get(region_begin_row + 1, [])

    for sym in symbols:
        _region = symbol_region(view, sym)

        if _region.contains(region):
            return (_region, sym)


def namespace_definition_in_region(view, nrn, region):
    region_begin_row, _ = view.rowcol(region.begin())

    for namespace_definition in nrn.get(region_begin_row + 1, []):
        _region = namespace_definition_region(view, namespace_definition)

        if _region.contains(region):
            return (_region, namespace_definition)


def namespace_usage_in_region(view, nrn_usages, region):
    region_begin_row, _ = view.rowcol(region.begin())

    for namespace_usage in nrn_usages.get(region_begin_row + 1, []):
        _region = namespace_usage_region(view, namespace_usage)

        if _region.contains(region):
            return (_region, namespace_usage)


def namespace_usage_alias_in_region(view, nrn_usages, region):
    region_begin_row, _ = view.rowcol(region.begin())

    for namespace_usage in nrn_usages.get(region_begin_row + 1, []):
        if _region := namespace_usage_alias_region(view, namespace_usage):
            if _region.contains(region):
                return (_region, namespace_usage)


def local_usage_in_region(view, lrn_usages, region):
    """
    Local usage dictionary, or None.

    Try to find a local usage in the index (lrn_usages).
    """

    region_begin_row, _ = view.rowcol(region.begin())

    usages = lrn_usages.get(region_begin_row + 1, [])

    for usage in usages:
        _region = local_usage_region(view, usage)

        if _region.contains(region):
            return (_region, usage)


def local_binding_in_region(view, lrn, region):
    region_begin_row, _ = view.rowcol(region.begin())

    for local_binding in lrn.get(region_begin_row + 1, []):
        _region = local_binding_region(view, local_binding)

        if _region.contains(region):
            return (_region, local_binding)


def var_usage_in_region(view, vrn_usages, region):
    region_begin_row, _ = view.rowcol(region.begin())

    for var_usage in vrn_usages.get(region_begin_row + 1, []):
        _region = var_usage_region(view, var_usage)

        if _region.contains(region):
            return (_region, var_usage)


def var_definition_in_region(view, vrn, region):
    region_begin_row, _ = view.rowcol(region.begin())

    for var_definition in vrn.get(region_begin_row + 1, []):
        _region = var_definition_region(view, var_definition)

        if _region.contains(region):
            return (_region, var_definition)


def java_class_usage_in_region(view, jrn_usages, region):
    region_begin_row, _ = view.rowcol(region.begin())

    for java_class_usage in jrn_usages.get(region_begin_row + 1, []):
        _region = java_class_usage_region(view, java_class_usage)

        if _region.contains(region):
            return (_region, java_class_usage)


# ---


def thingy_text(view, thingy):
    if tregion := thingy_region(view, thingy):
        return view.substr(tregion)


def thingy_name(thingy_data) -> str:
    namespace_ = thingy_data.get("ns") or thingy_data.get("to")

    name_ = thingy_data.get("name")

    if name_:
        prefix = ""

        if thingy_data["_semantic"] == TT_KEYWORD:
            prefix = ":"

        s = f"{namespace_}/{name_}" if namespace_ else name_
        s = prefix + s

        return s
    else:
        return namespace_


def thingy_location(thingy_data):
    """
    Thingy (data) is one of: Var definition, Var usage, local binding, or local usage.
    """
    if thingy_data and (filename := thingy_data.get("filename")):
        return {
            "filename": filename,
            "line": thingy_data.get("name-row") or thingy_data.get("row"),
            "column": thingy_data.get("name-col") or thingy_data.get("col"),
        }


def thingy_file_extensions(thingy_data):
    """
    Returns a set of file extensions in which a thingy might be defined.

    Thingy in a cljc file might be defined in clj, cljs and cljc.

    Thingy in clj or cljs might be defined in cljc or same as its file extension.
    """

    if file_extension_ := file_extension(thingy_data.get("filename")):
        return (
            {".clj", ".cljs", ".cljc"}
            if file_extension_ == ".cljc"
            else {file_extension_, ".cljc"}
        )
    else:
        return {".clj"}


def thingy_kind(thingy_type, thingy_data):
    """
    Mapping of Thingy Type to Sublime KindId.

    https://www.sublimetext.com/docs/api_reference.html#sublime.KindId
    """

    if thingy_type == TT_KEYWORD:
        return sublime.KIND_KEYWORD

    elif thingy_type == TT_LOCAL_BINDING:
        return (sublime.KIND_ID_VARIABLE, "v", "Local binding")

    elif thingy_type == TT_LOCAL_USAGE:
        return (sublime.KIND_ID_VARIABLE, "v", "Local usage")

    elif thingy_type == TT_VAR_DEFINITION:
        return (
            sublime.KIND_FUNCTION
            if thingy_data.get("arglist-strs")
            else sublime.KIND_VARIABLE
        )

    elif thingy_type == TT_VAR_USAGE:
        return (
            sublime.KIND_FUNCTION
            if thingy_data.get("arglist-strs")
            else sublime.KIND_VARIABLE
        )

    elif (
        thingy_type == TT_NAMESPACE_DEFINITION
        or thingy_type == TT_NAMESPACE_USAGE
        or thingy_type == TT_NAMESPACE_USAGE_ALIAS
    ):
        return (sublime.KIND_ID_NAMESPACE, "n", "Namespace")

    else:
        return sublime.KIND_AMBIGUOUS


def thingy_sel_region(view):
    """
    Thingy region is no special region, is simply the first one in the selection.

    Most of the time, the first region is what you're looking for.
    """
    return view.sel()[0]


# TODO: Replace with `thingy_at`.
def thingy_in_region(view, analysis, region):
    """
    Tuple of type, region and data.

    Thingy is not a good name, but what to call something that
    can be a local binding, local usage, Var definition, or Var usage?

    It's difficult to find a good name for it.

    A thingy is a triple:
        - Type:
            - Local binding
            - Local usage
            - Var definition
            - Var usage
            - Namespace definition
            - Namespace usage
            - Namespace usage alias
            - Keywords
            - Java class definition
            - Java class usage

        - Region for the symbol

        - The thingy itself - clj-kondo data.
    """

    # Try local usages.
    thingy_region, thingy_data = local_usage_in_region(
        view, analysis.get("lrn_usages", {}), region
    ) or (None, None)

    if thingy_data:
        return (TT_LOCAL_USAGE, thingy_region, thingy_data)

    # Try local bindings.
    thingy_region, thingy_data = local_binding_in_region(
        view, analysis.get("lrn", {}), region
    ) or (None, None)

    if thingy_data:
        return (TT_LOCAL_BINDING, thingy_region, thingy_data)

    # Try Var usages.
    thingy_region, thingy_data = var_usage_in_region(
        view, analysis.get("vrn_usages", {}), region
    ) or (None, None)

    if thingy_data:
        return (TT_VAR_USAGE, thingy_region, thingy_data)

    # Try Var definitions.
    thingy_region, thingy_data = var_definition_in_region(
        view, analysis.get("vrn", {}), region
    ) or (None, None)

    if thingy_data:
        return (TT_VAR_DEFINITION, thingy_region, thingy_data)

    # Try keywords.
    #
    # Note:
    # Keyword is checked after locals because destructuring introduces a local binding.
    # If keyword is placed before locals, a command like 'Find Usages'
    # finds keyword usages instead of locals.
    thingy_region, thingy_data = keyword_in_region(
        view, analysis.get("krn", {}), region
    ) or (None, None)

    if thingy_data:
        return (TT_KEYWORD, thingy_region, thingy_data)

    # Try namespace usages.
    thingy_region, thingy_data = namespace_usage_in_region(
        view, analysis.get("nrn_usages", {}), region
    ) or (None, None)

    if thingy_data:
        return (TT_NAMESPACE_USAGE, thingy_region, thingy_data)

    # Try namespace usages alias.
    thingy_region, thingy_data = namespace_usage_alias_in_region(
        view, analysis.get("nrn_usages", {}), region
    ) or (None, None)

    if thingy_data:
        return (TT_NAMESPACE_USAGE_ALIAS, thingy_region, thingy_data)

    # Try namespace definitions.
    thingy_region, thingy_data = namespace_definition_in_region(
        view, analysis.get("nrn", {}), region
    ) or (None, None)

    if thingy_data:
        return (TT_NAMESPACE_DEFINITION, thingy_region, thingy_data)

    # Try Java class usages.
    thingy_region, thingy_data = java_class_usage_in_region(
        view, analysis_jrn_usages(analysis), region
    ) or (None, None)

    if thingy_data:
        return (TT_JAVA_CLASS_USAGE, thingy_region, thingy_data)

    # Try symbols.
    thingy_region, thingy_data = symbol_in_region(
        view, analysis.get("srn", {}), region
    ) or (None, None)

    if thingy_data:
        return (TT_SYMBOL, thingy_region, thingy_data)


def thingy_at(view, analysis, region) -> Optional[dict]:
    """
    Returns Thingy at region (a region under the cursor, most likely) or None.
    """

    if semantic_region_data := thingy_in_region(view, analysis, region):
        _, _, data = semantic_region_data

        return data


# ---


def find_keywords(analysis, keyword):
    keyword_qualified_name = (keyword.get("ns"), keyword.get("name"))

    return analysis_kindex(analysis).get(keyword_qualified_name, [])


def find_keyword_usages(analysis, keyword):
    keywords = find_keywords(analysis, keyword)

    return [keyword for keyword in keywords if not keyword.get("reg")]


def find_local_binding(analysis, local_usage):
    return analysis_lindex(analysis).get(local_usage.get("id"))


def find_local_usages(analysis, local_binding_or_usage):
    return analysis.get("lindex_usages", {}).get(local_binding_or_usage.get("id"), [])


# Deprecated
# See `find_var_definitions`
def find_var_definition(analysis, thingy_data) -> Optional[dict]:
    """
    Returns a var_definition or None.

    `thingy_data` can be either a var_definirion or var_usage.
    """

    ns = thingy_data.get("ns", thingy_data.get("to"))

    name = thingy_data.get("name")

    vindex = analysis_vindex(analysis)

    file_extensions = thingy_file_extensions(thingy_data)

    for var_definition in vindex.get((ns, name), []):
        definition_file_extension = None

        if file_extension_ := file_extension(var_definition.get("filename")):
            definition_file_extension = file_extension_
        else:
            definition_file_extension = ".clj"

        if definition_file_extension in file_extensions:
            return var_definition


def find_var_definitions(analysis, thingy_data) -> List:
    """
    Returns a list of var_definition.

    `thingy_data` can be either a var_definirion or var_usage.
    """

    k = (thingy_data.get("ns", thingy_data.get("to")), thingy_data.get("name"))

    return analysis_vindex(analysis).get(k, [])


def find_var_usages(analysis, thingy_data) -> List:
    """
    Returns a list of var_usage and symbols.

    `thingy_data` can be a Var definition, usage or a symbol.
    """

    var_namespace = thingy_data.get("ns") or thingy_data.get("to")
    var_name = thingy_data.get("name")

    # Look up Var usages by key - a tuple with namespace and name:
    var_usages = analysis_vindex_usages(analysis).get(
        (var_namespace, var_name),
        [],
    )

    # Find usages of symbol too:
    var_symbol = f"{var_namespace}/{var_name}" if var_namespace else var_name
    var_symbol_usages = analysis_sindex(analysis).get(var_symbol, [])

    return var_usages + var_symbol_usages


def find_java_class_definition(analysis, thingy_data):
    """
    Returns a Java class definition analysis or None.
    """
    return analysis_jindex(analysis).get(thingy_data.get("class"))


def find_java_class_usages(analysis, thingy_data) -> List:
    """
    Returns a list of java_class_usage.
    """
    class_usages = analysis_jindex_usages(analysis).get(thingy_data.get("class"), [])

    if thingy_data.get("method-name"):
        class_usages = [
            class_usage
            for class_usage in class_usages
            if class_usage.get("method-name") == thingy_data.get("method-name")
        ]

    return class_usages


# Deprecated
# See `find_namespace_definitions`
def find_namespace_definition(analysis, thingy_data) -> Optional[dict]:
    """
    Returns a namespace_definition or None.

    `thingy_data` can be either a namespace_definition or namespace_usage.
    """

    name = thingy_data.get("name", thingy_data.get("to"))

    nindex = analysis_nindex(analysis)

    file_extensions = thingy_file_extensions(thingy_data)

    for namespace_definition in nindex.get(name, []):
        definition_file_extension = None

        if file_extension_ := file_extension(namespace_definition.get("filename")):
            definition_file_extension = file_extension_
        else:
            definition_file_extension = ".clj"

        if definition_file_extension in file_extensions:
            return namespace_definition


def find_namespace_definitions(analysis, thingy_data) -> List:
    """
    Returns a list of namespace_definition.

    `thingy_data` can be either a namespace_definition or namespace_usage.
    """

    k = thingy_data.get("name", thingy_data.get("to"))

    return analysis_nindex(analysis).get(k, [])


def find_namespace_usages(analysis, thingy_data) -> List:
    """
    Returns a list of namespace_usage.

    `thingy_data` can be either a namespace_definition or namespace_usage.
    """

    name = thingy_data.get("name", thingy_data.get("to"))

    nindex_usages = analysis_nindex_usages(analysis)

    return [
        namespace_usage
        for namespace_usage in nindex_usages.get(name, [])
        if file_extension(thingy_data.get("filename"))
        in thingy_file_extensions(thingy_data)
    ]


def find_namespace_vars_usages(analysis, namespace):
    """
    Returns a list of var_usage of Vars from namespace.

    It's useful when you want to see Vars (from namespace) being used in your namespace.
    """

    usages = []

    for var_qualified_name, var_usages in analysis_vindex_usages(analysis).items():
        var_namespace, _ = var_qualified_name

        if var_namespace == namespace:
            usages.extend(var_usages)

    return usages


# Deprecated
# See `find_keyword_definitions`
def find_keyword_definition(analysis, keyword):
    """
    Returns a keyword which has "definition semantics":
    - Clojure Spec
    - re-frame
    """
    for keyword_indexed in find_keywords(analysis, keyword):
        if keyword_indexed.get("reg", None):
            return keyword_indexed


def find_keyword_definitions(analysis, keyword):
    """
    Returns a list of keyword which has "definition semantics":
    - Clojure Spec
    - re-frame
    """
    return [
        keyword_ for keyword_ in find_keywords(analysis, keyword) if keyword_.get("reg")
    ]


# Deprecated
# See `find_symbol_definitions`
def find_symbol_definition(analysis, sym):
    """
    Returns Var definition for symbol `sym`.
    """
    k = (symbol_namespace(sym), symbol_name(sym))

    for var_definition in analysis_vindex(analysis).get(k, []):
        return var_definition


def find_symbol_definitions(analysis, sym):
    """
    Returns a list of Var definition for symbol `sym`.
    """
    k = (symbol_namespace(sym), symbol_name(sym))

    return analysis_vindex(analysis).get(k, [])


def find_symbol_usages(analysis, thingy):
    """
    Returns Var usages for symbol thingy.
    """
    k = (symbol_namespace(thingy), symbol_name(thingy))

    var_usages = analysis_vindex_usages(analysis).get(k, [])

    symbol_usages = analysis_sindex(analysis).get(thingy.get("symbol", ""), [])

    return symbol_usages + var_usages


def find_usages(analysis, thingy) -> Optional[List]:
    thingy_semantic = thingy["_semantic"]

    if thingy_semantic == TT_KEYWORD:
        return find_keyword_usages(analysis, thingy)

    elif thingy_semantic == TT_LOCAL or thingy_semantic == TT_LOCAL_USAGE:
        return find_local_usages(analysis, thingy)

    elif thingy_semantic == TT_VAR_DEFINITION or thingy_semantic == TT_VAR_USAGE:
        return find_var_usages(analysis, thingy)

    elif thingy_semantic == TT_SYMBOL:
        return find_symbol_usages(analysis, thingy)

    elif thingy_semantic == TT_JAVA_CLASS_USAGE:
        return find_java_class_usages(analysis, thingy)

    elif (
        thingy_semantic == TT_NAMESPACE_DEFINITION
        or thingy_semantic == TT_NAMESPACE_USAGE
        or thingy_semantic == TT_NAMESPACE_USAGE_ALIAS
    ):
        return find_namespace_usages(analysis, thingy)


def find_definitions(analysis, thingy) -> Optional[List]:
    thingy_semantic = thingy["_semantic"]

    if thingy_semantic == TT_LOCAL_USAGE:
        if local_binding := find_local_binding(analysis, thingy):
            return [local_binding]

    elif (
        thingy_semantic == TT_NAMESPACE_USAGE
        or thingy_semantic == TT_NAMESPACE_USAGE_ALIAS
    ):
        return find_namespace_definitions(analysis, thingy)

    elif thingy_semantic == TT_VAR_USAGE:
        return find_var_definitions(analysis, thingy)

    elif thingy_semantic == TT_KEYWORD:
        return find_keyword_definitions(analysis, thingy)

    elif thingy_semantic == TT_SYMBOL:
        return find_symbol_definitions(analysis, thingy)


# ---


def highlight_regions(view, selection, regions):
    if regions:
        view.add_regions(
            HIGHLIGHTED_REGIONS_KEY,
            regions,
            scope=setting(view.window(), "highlight_scope", "region.cyanish"),
            icon="dot" if setting(view.window(), "highlight_gutter", None) else "",
            flags=sublime.DRAW_NO_FILL
            if setting(view.window(), "highlight_region", None)
            else sublime.HIDDEN,
        )


def highlight_thingy(view):
    """
    Highlight regions of thingy under cursor.
    """
    regions = []

    status_message = ""

    if not staled_analysis(view):
        analysis = view_analysis(view.id())

        for region in view.sel():
            if thingy := thingy_in_region(view, analysis, region):
                if regions_ := find_thingy_regions(view, analysis, thingy):
                    # Exclude 'self'
                    if not setting(view.window(), "highlight_self", None):
                        regions_ = [
                            region_
                            for region_ in regions_
                            if not region_.contains(region)
                        ]

                    regions.extend(regions_)

    if regions:
        window = view.window()

        highlight_regions(view, view.sel(), regions)

        if view_status_show_highlighted(window):
            prefix = view_status_show_highlighted_prefix(window)

            suffix = view_status_show_highlighted_suffix(window)

            status_message = f"{prefix}{len(regions)}{suffix}"
    else:
        view.erase_regions(HIGHLIGHTED_REGIONS_KEY)

    view.set_status(HIGHLIGHTED_STATUS_KEY, status_message)


def find_thingy_regions(view, analysis, thingy) -> List[sublime.Region]:
    """
    Returns a list of regions where Thingy is found in analysis.

    Note that an analysis might be for a view, paths or classpath.
    """

    thingy_type, _, thingy_data = thingy

    regions = []

    if thingy_type == TT_KEYWORD:
        # It's a little more involved if it's a 'keys destructuring'.
        # Keys names become locals, so their usages must be highligthed.
        if thingy_data.get("keys-destructuring"):
            lrn = analysis_lrn(analysis)

            region = keyword_region(view, thingy_data)

            # We should find a local binding for the keyword because of destructuring.
            thingy_region, thingy_data = local_binding_in_region(view, lrn, region) or (
                None,
                None,
            )

            thingy = ("local_binding", thingy_region, thingy_data)

            # Recursive call to find usages regions.
            local_usages_regions = find_thingy_regions(view, analysis, thingy)

            if local_usages_regions:
                regions.extend(local_usages_regions)
        else:
            keywords = find_keywords(analysis, thingy_data)

            for keyword in keywords:
                regions.append(keyword_region(view, keyword))

    elif thingy_type == TT_SYMBOL:
        regions.append(symbol_region(view, thingy_data))

        if var_definition := find_var_definition(analysis, thingy_data):
            regions.append(var_definition_region(view, var_definition))

        var_usages = find_var_usages(analysis, thingy_data)

        for var_usage in var_usages:
            regions.append(var_usage_region(view, var_usage))

    elif thingy_type == TT_LOCAL_BINDING:
        regions.append(local_binding_region(view, thingy_data))

        local_usages = find_local_usages(analysis, thingy_data)

        for local_usage in local_usages:
            regions.append(local_usage_region(view, local_usage))

    elif thingy_type == TT_LOCAL_USAGE:
        # It's possible to have a local usage without a local binding.
        # (It looks like a clj-kondo bug.)
        if local_binding := find_local_binding(analysis, thingy_data):
            regions.append(local_binding_region(view, local_binding))

        local_usages = find_local_usages(analysis, thingy_data)

        for local_usage in local_usages:
            regions.append(local_usage_region(view, local_usage))

    elif thingy_type == TT_VAR_DEFINITION:
        regions.append(var_definition_region(view, thingy_data))

        var_usages = find_var_usages(analysis, thingy_data)

        for var_usage in var_usages:
            regions.append(var_usage_region(view, var_usage))

    elif thingy_type == TT_VAR_USAGE:
        if var_definition := find_var_definition(analysis, thingy_data):
            regions.append(var_definition_region(view, var_definition))

        var_usages = find_var_usages(analysis, thingy_data)

        for var_usage in var_usages:
            regions.append(var_usage_region(view, var_usage))

    elif thingy_type == TT_JAVA_CLASS_USAGE:
        java_class_usages = find_java_class_usages(analysis, thingy_data)

        for java_class_usage in java_class_usages:
            regions.append(java_class_usage_region(view, java_class_usage))

    elif thingy_type == TT_NAMESPACE_DEFINITION:
        regions.append(namespace_definition_region(view, thingy_data))

    elif thingy_type == TT_NAMESPACE_USAGE:
        regions.append(namespace_usage_region(view, thingy_data))

        var_usages = find_namespace_vars_usages(analysis, thingy_data["to"])

        for var_usage in var_usages:
            if region := var_usage_namespace_region(view, var_usage):
                regions.append(region)

    elif thingy_type == TT_NAMESPACE_USAGE_ALIAS:
        regions.append(namespace_usage_alias_region(view, thingy_data))

        var_usages = find_namespace_vars_usages(analysis, thingy_data["to"])

        for var_usage in var_usages:
            if region := var_usage_namespace_region(view, var_usage):
                regions.append(region)

    return regions


def find_thingy_text_regions(view, analysis, thingy):
    # There's at least one region - thingy's region.
    thingy_regions = []

    # Only exact text matches of thingy usages.
    for r in find_thingy_regions(view, analysis, thingy):
        if thingy_text(view, thingy) == view_text(view, r):
            thingy_regions.append(r)

    return thingy_regions


def annotate_view(view):
    def finding_region(finding):
        line_start = finding["row"] - 1
        line_end = (finding.get("end-row") or finding.get("row")) - 1
        col_start = finding["col"] - 1
        col_end = (finding.get("end-col") or finding.get("col")) - 1

        pa = view.text_point(line_start, col_start)
        pb = view.text_point(line_end, col_end)

        return sublime.Region(pa, pb)

    def finding_minihtml(finding):
        return f"""
        <body>
            <div>
                <span style="font-size:{annotation_font_size(view.window())}">
                    {htmlify(finding["message"])}
                </span>
            </div>
        </body>
        """

    # Erase regions from previous analysis.
    erase_analysis_regions(view)

    # Skip annotation if view explicitly set the custom setting to disable it.
    if view.settings().get(SETTING_ANNOTATE_VIEW) is False:
        return

    analysis = view_analysis(view.id())

    findings = analysis_findings(analysis)

    warning_region_set = []
    warning_minihtml_set = []

    error_region_set = []
    error_minihtml_set = []

    for finding in findings:
        if finding["level"] == "error":
            error_region_set.append(finding_region(finding))
            error_minihtml_set.append(finding_minihtml(finding))
        elif finding["level"] == "warning":
            warning_region_set.append(finding_region(finding))
            warning_minihtml_set.append(finding_minihtml(finding))

    redish = view.style_for_scope("region.redish").get("foreground")
    orangish = view.style_for_scope("region.orangish").get("foreground")

    view.add_regions(
        "pg_pep_analysis_error",
        error_region_set,
        scope="region.redish",
        annotations=error_minihtml_set,
        annotation_color=redish or "red",
        flags=(
            sublime.DRAW_SQUIGGLY_UNDERLINE
            | sublime.DRAW_NO_FILL
            | sublime.DRAW_NO_OUTLINE
        ),
    )

    view.add_regions(
        "pg_pep_analysis_warning",
        warning_region_set,
        scope="region.orangish",
        annotations=warning_minihtml_set,
        annotation_color=orangish or "orange",
        flags=(
            sublime.DRAW_SQUIGGLY_UNDERLINE
            | sublime.DRAW_NO_FILL
            | sublime.DRAW_NO_OUTLINE
        ),
    )


def annotate_view_v2(view, diagnostics):
    def finding_region(finding):
        line_start = finding["row"] - 1
        line_end = (finding.get("end-row") or finding.get("row")) - 1
        col_start = finding["col"] - 1
        col_end = (finding.get("end-col") or finding.get("col")) - 1

        pa = view.text_point(line_start, col_start)
        pb = view.text_point(line_end, col_end)

        return sublime.Region(pa, pb)

    def finding_minihtml(finding):
        return f"""
        <body>
            <div>
                <span style="font-size:{annotation_font_size(view.window())}">
                    {htmlify(finding["message"])}
                </span>
            </div>
        </body>
        """

    # Erase regions from previous analysis.
    erase_analysis_regions(view)

    # Skip annotation if view explicitly set the custom setting to disable it.
    if view.settings().get(SETTING_ANNOTATE_VIEW) is False:
        return

    warning_region_set = []
    warning_minihtml_set = []

    error_region_set = []
    error_minihtml_set = []

    for finding in diagnostics.get("error", []):
        error_region_set.append(finding_region(finding))
        error_minihtml_set.append(finding_minihtml(finding))

    for finding in diagnostics.get("warning", []):
        warning_region_set.append(finding_region(finding))
        warning_minihtml_set.append(finding_minihtml(finding))

    redish = view.style_for_scope("region.redish").get("foreground")
    orangish = view.style_for_scope("region.orangish").get("foreground")

    view.add_regions(
        "pg_pep_analysis_error",
        error_region_set,
        scope="region.redish",
        annotations=error_minihtml_set,
        annotation_color=redish or "red",
        flags=(
            sublime.DRAW_SQUIGGLY_UNDERLINE
            | sublime.DRAW_NO_FILL
            | sublime.DRAW_NO_OUTLINE
        ),
    )

    view.add_regions(
        "pg_pep_analysis_warning",
        warning_region_set,
        scope="region.orangish",
        annotations=warning_minihtml_set,
        annotation_color=orangish or "orange",
        flags=(
            sublime.DRAW_SQUIGGLY_UNDERLINE
            | sublime.DRAW_NO_FILL
            | sublime.DRAW_NO_OUTLINE
        ),
    )


# ---


class ScopeInputHandler(sublime_plugin.ListInputHandler):
    def __init__(self, scopes):
        self.scopes = scopes

    def name(self):
        return "scope"

    def list_items(self):
        return [(scope.capitalize(), scope) for scope in self.scopes]

    def placeholder(self):
        return "Scope"


class RootPathInputHandler(sublime_plugin.ListInputHandler):
    def name(self):
        return "root_path"

    def list_items(self):
        # The returned value may be a list of item,
        # or a 2-element tuple containing a list of items,
        # and an int index of the item to pre-select.
        return (sublime.active_window().folders(), 0)

    def placeholder(self):
        return "Root Path"


class ReplaceTextInputHandler(sublime_plugin.TextInputHandler):
    def __init__(self, text):
        self.text = text

    def name(self):
        return "text"

    def initial_text(self):
        return self.text


class PgPepClearCacheCommand(sublime_plugin.WindowCommand):
    def run(self):
        clear_cache()

        if is_debug(self.window):
            print("Pep Debug: Cleared cache")


class PgPepAnalyzeCommand(sublime_plugin.WindowCommand):
    def input(self, args):
        if "scope" not in args:
            return ScopeInputHandler(scopes=["view", "paths", "classpath"])

    def run(self, scope):
        if scope == "view":
            if view := self.window.active_view():
                analyze_view_async(view)

        elif scope == "paths":
            analyze_paths_async(self.window)

        elif scope == "classpath":
            analyze_classpath_async(self.window)


# Deprecated. It should be deleted soon.
class PgPepOutlineCommand(sublime_plugin.TextCommand):
    """
    Outline Thingies in View.
    """

    def run(self, edit):
        view_analysis_ = view_analysis(self.view.id())

        thingy_list = thingy_dedupe(
            [
                *namespace_definitions(view_analysis_),
                *var_definitions(view_analysis_),
                *keyword_regs(view_analysis_),
            ],
        )

        thingy_list = sorted(
            thingy_list,
            key=lambda thingy: (
                thingy["row"],
                thingy["col"],
            ),
        )

        goto_thingy(
            self.view.window(),
            thingy_list,
            goto_on_highlight=True,
            goto_side_by_side=False,
            quick_panel_item_opts={
                "show_namespace": False,
                "show_row_col": False,
                "show_filename": False,
            },
        )


class PgPepCopyNameCommand(sublime_plugin.TextCommand):
    """
    Copy a Thingy's name to the clipboard.
    """

    def run(self, edit):
        view_analysis_ = view_analysis(self.view.id())

        region = thingy_sel_region(self.view)

        if thingy := thingy_at(self.view, view_analysis_, region):
            sublime.set_clipboard(thingy_name(thingy))

            self.view.window().status_message("Copied " + thingy_name(thingy))


class PgPepShowNameCommand(sublime_plugin.TextCommand):
    """
    Show a Thingy's name in a popup.
    """

    def run(self, edit):
        view_analysis_ = view_analysis(self.view.id())

        region = thingy_sel_region(self.view)

        if thingy := thingy_at(self.view, view_analysis_, region):
            content = f"""
                    <body id='pg-pep-show-name'>

                        {htmlify(thingy_name(thingy))}

                    </body>
                    """

            self.view.show_popup(
                content,
                location=-1,
                max_width=500,
            )


class PgPepShowDocCommand(sublime_plugin.TextCommand):
    def run(self, edit, show="popup"):
        view_analysis_ = view_analysis(self.view.id())

        project_path_ = project_path(self.view.window())

        def paths_analysis_delay():
            analysis = None

            def f():
                nonlocal analysis
                if analysis is None:
                    analysis = paths_analysis(project_path_)
                return analysis

            return f

        paths_analysis_ = paths_analysis_delay()

        classpath_analysis_ = classpath_analysis(project_path_)

        minihtmls = []

        for region in self.view.sel():
            definition = None

            if thingy := thingy_at(self.view, view_analysis_, region):
                thingy_semantic = thingy["_semantic"]

                if (
                    thingy_semantic == TT_VAR_DEFINITION
                    or thingy_semantic == TT_VAR_USAGE
                ):
                    # Try to find Var definition in view first,
                    # only if not found try paths and project analysis.
                    definition = (
                        find_var_definition(view_analysis_, thingy)
                        or find_var_definition(paths_analysis_(), thingy)
                        or find_var_definition(classpath_analysis_, thingy)
                    )

                elif (
                    thingy_semantic == TT_NAMESPACE_DEFINITION
                    or thingy_semantic == TT_NAMESPACE_USAGE
                    or thingy_semantic == TT_NAMESPACE_USAGE_ALIAS
                ):
                    definition = (
                        find_namespace_definition(view_analysis_, thingy)
                        or find_namespace_definition(paths_analysis_(), thingy)
                        or find_namespace_definition(classpath_analysis_, thingy)
                    )

                elif thingy_semantic == TT_SYMBOL:
                    definition = (
                        find_symbol_definition(view_analysis_, thingy)
                        or find_symbol_definition(paths_analysis_(), thingy)
                        or find_symbol_definition(classpath_analysis_, thingy)
                    )

            if definition:
                # Name
                # ---

                name = definition.get("name", "")
                name = inspect.cleandoc(html.escape(name))

                ns = definition.get("ns", "")
                ns = inspect.cleandoc(html.escape(ns))

                qualified_name = f"{ns}/{name}" if ns else name

                goto_command_url = sublime.command_url(
                    "pg_pep_open_file",
                    {"location": thingy_location(definition)},
                )

                name_minihtml = f"""
                <p class="name">
                    <a href="{goto_command_url}"><b>{qualified_name}</b></a>
                </p>
                """

                # Arglists
                # ---

                arglists = definition.get("arglist-strs", [])

                arglists_minihtml = ""

                if arglists:
                    arglists_minihtml = """<p class="arglists">"""

                    for arglist in arglists:
                        arglists_minihtml += f"<code>{htmlify(arglist)}</code><br/>"

                    arglists_minihtml += """</p>"""

                # Doc
                # ---

                doc = definition.get("doc")

                doc_minihtml = ""

                if doc:
                    doc = re.sub(r"\s", "&nbsp;", htmlify(doc))

                    doc_minihtml = f"""<p class="doc">{doc}</p>"""

                minihtmls.append(
                    f"""
                        {name_minihtml}

                        {arglists_minihtml}

                        {doc_minihtml}
                    """
                )

        if minihtmls:
            content = f"""
            <body id='pg-pep-show-doc'>

                {"<br/>".join(minihtmls)}

            </body>
            """

            if show == "popup":
                self.view.show_popup(
                    content,
                    location=-1,
                    max_width=500,
                )

            elif show == "side_by_side":
                sheet = self.view.window().new_html_sheet(
                    "Documentation",
                    content,
                    sublime.SEMI_TRANSIENT | sublime.ADD_TO_SELECTION,
                )

                self.view.window().focus_sheet(sheet)


class PgPepJumpCommand(sublime_plugin.TextCommand):
    """
    Command to jump to thingies.
    """

    def initialize_navigation(self, analysis, thingy_id, thingy_findings):
        navigation = view_navigation(analysis)

        if thingy_id != navigation.get("thingy_id"):
            set_view_navigation(
                analysis,
                {
                    "thingy_id": thingy_id,
                    "thingy_findings": thingy_findings,
                },
            )

    def find_position(self, thingy_data, thingy_findings):
        for position, finding in enumerate(thingy_findings):
            if finding == thingy_data:
                return position

        return -1

    def jump(self, state, movement, findings_position):
        navigation = view_navigation(state)

        findings_position_after = findings_position

        if movement == "forward":
            if findings_position < len(navigation["thingy_findings"]) - 1:
                findings_position_after = findings_position + 1

        elif movement == "back":
            if findings_position > 0:
                findings_position_after = findings_position - 1

        if findings_position != findings_position_after:
            finding_at_position = navigation["thingy_findings"][findings_position_after]

            region = local_binding_region(self.view, finding_at_position)
            region = sublime.Region(region.begin(), region.begin())

            self.view.sel().clear()
            self.view.sel().add(region)
            self.view.show(region)

    def run(self, edit, movement):
        state = view_analysis(self.view.id())

        region = self.view.sel()[0]

        if thingy := thingy_in_region(self.view, state, region):
            thingy_type, thingy_region, thingy_data = thingy

            thingy_findings = []

            thingy_id = None

            if thingy_type == TT_KEYWORD:
                # It's a keyword in a keys destructuring context, so it creates a local binding.
                # Instead of navigating to another keyword, we navigate to the next usage of the local.
                if thingy_data.get("keys-destructuring", False):
                    lrn = analysis_lrn(state)

                    region = keyword_region(self.view, thingy_data)

                    # We should find a local binding for the keyword because of destructuring.
                    thingy_region, thingy_data = local_binding_in_region(
                        self.view, lrn, region
                    ) or (None, None)

                    thingy = (TT_LOCAL_BINDING, thingy_region, thingy_data)

                    # Find local usages for this local binding (thingy).
                    local_usages = find_local_usages(state, thingy_data)

                    thingy_findings = [thingy_data]
                    thingy_findings.extend(local_usages)

                    thingy_id = thingy_data.get("id")

                else:
                    thingy_findings = find_keywords(state, thingy_data)

                    thingy_id = (thingy_data.get("ns"), thingy_data.get("name"))

                self.initialize_navigation(state, thingy_id, thingy_findings)

                position = self.find_position(thingy_data, thingy_findings)

                if position != -1:
                    self.jump(state, movement, position)

            elif thingy_type == TT_LOCAL_BINDING:
                # Find local usages for this local binding (thingy).
                local_usages = find_local_usages(state, thingy_data)

                thingy_findings = [thingy_data]
                thingy_findings.extend(local_usages)

                thingy_id = thingy_data.get("id")

                if thingy_id:
                    self.initialize_navigation(state, thingy_id, thingy_findings)

                    position = self.find_position(thingy_data, thingy_findings)

                    if position != -1:
                        self.jump(state, movement, position)

            elif thingy_type == TT_LOCAL_USAGE:
                # Find local binding for this local usage (thingy).
                local_binding = find_local_binding(state, thingy_data)

                # It's possible to have a local usage without a local binding.
                # (It looks like a clj-kondo bug.)
                if local_binding is None:
                    return

                local_usages = find_local_usages(state, local_binding)

                thingy_findings = [local_binding]
                thingy_findings.extend(local_usages)

                thingy_id = thingy_data.get("id")

                if thingy_id:
                    self.initialize_navigation(state, thingy_id, thingy_findings)

                    position = self.find_position(thingy_data, thingy_findings)

                    if position != -1:
                        self.jump(state, movement, position)

            elif thingy_type == TT_VAR_DEFINITION:
                # Find Var usages for this Var definition (thingy).
                var_usages = find_var_usages(state, thingy_data)

                thingy_findings = [thingy_data]
                thingy_findings.extend(var_usages)

                thingy_id = (thingy_data.get("ns"), thingy_data.get("name"))

                if thingy_id:
                    self.initialize_navigation(state, thingy_id, thingy_findings)

                    position = self.find_position(thingy_data, thingy_findings)

                    if position != -1:
                        self.jump(state, movement, position)

            elif thingy_type == TT_VAR_USAGE:
                # Find Var definition for this Var usage (thingy).
                var_definition = find_var_definition(state, thingy_data)

                var_usages = find_var_usages(state, thingy_data)

                thingy_findings = [var_definition] if var_definition else []
                thingy_findings.extend(var_usages)

                thingy_id = (thingy_data.get("to"), thingy_data.get("name"))

                if thingy_id:
                    self.initialize_navigation(state, thingy_id, thingy_findings)

                    position = self.find_position(thingy_data, thingy_findings)

                    if position != -1:
                        self.jump(state, movement, position)

            elif thingy_type == TT_JAVA_CLASS_USAGE:
                thingy_findings = find_java_class_usages(state, thingy_data)

                if thingy_id := thingy_data.get("class"):
                    self.initialize_navigation(state, thingy_id, thingy_findings)

                    position = self.find_position(thingy_data, thingy_findings)

                    if position != -1:
                        self.jump(state, movement, position)

            elif (
                thingy_type == TT_NAMESPACE_USAGE
                or thingy_type == TT_NAMESPACE_USAGE_ALIAS
            ):
                # Jumping from a namespace usage, or alias, moves the caret
                # to the first var usage of the namespace.

                if thingy_findings := find_namespace_vars_usages(
                    state, thingy_data["to"]
                ):
                    # ID is the namespace name.
                    thingy_id = thingy_data.get("to")

                    self.initialize_navigation(state, thingy_id, thingy_findings)

                    # Jump to first var usage.
                    self.jump(state, movement, -1)


class PgPepInspect(sublime_plugin.TextCommand):
    def run(self, edit):
        region = self.view.sel()[0]

        analysis = view_analysis(self.view.id())

        if thingy := thingy_at(self.view, analysis, region):
            items_html = ""

            for k, v in thingy.items():
                items_html += f"<li>{htmlify(str(k))}: {htmlify(str(v))}</li>"

            html = f"""
            <body id='pg-pep-inspect'>
                <style>
                    h1 {{
                        font-size: 1.1rem;
                        font-weight: 500;
                        font-family: system;
                    }}
                </style>

                <h1>{thingy['_semantic']}</h1>

                <ul>
                    {items_html}
                </ul>

            </body>
            """

            self.view.show_popup(html)


class PgPepOpenFileCommand(sublime_plugin.WindowCommand):
    def run(self, location, flags=GOTO_DEFAULT_FLAGS):
        goto(self.window, location, flags)


class PgPepGotoAnythingInClasspathCommand(sublime_plugin.WindowCommand):
    """
    Goto namespace, Var, Keyword in classpath.
    """

    def run(
        self,
        goto_on_highlight=False,
        goto_side_by_side=False,
    ):
        window_ = self.window

        project_path_ = project_path(self.window)

        def done_(thingy_list):
            progress.stop()

            goto_thingy(
                window_,
                thingy_list,
                goto_on_highlight=goto_on_highlight,
                goto_side_by_side=goto_side_by_side,
                quick_panel_item_opts={
                    "show_namespace": True,
                    "show_row_col": False,
                },
            )

        def run_():
            classpath_analysis_ = classpath_analysis(project_path_, not_found={})

            thingy_list = thingy_dedupe(
                [
                    *namespace_definitions(classpath_analysis_),
                    *var_definitions(classpath_analysis_),
                    *keyword_regs(classpath_analysis_),
                ],
            )

            thingy_list = sorted(thingy_list, key=thingy_name)

            sublime.set_timeout(lambda: done_(thingy_list), 0)

        progress.start("")

        threading.Thread(target=run_).start()


class PgPepGotoAnythingInViewPathsCommand(sublime_plugin.WindowCommand):
    """
    Goto namespace, var or keyword in paths or view.
    """

    def run(
        self,
        goto_on_highlight=False,
        goto_side_by_side=False,
    ):
        active_view_ = self.window.active_view()
        active_view_id_ = self.window.active_view().id()
        window_ = self.window

        def done_(thingy_list):
            progress.stop()

            goto_thingy(
                window_,
                thingy_list,
                goto_on_highlight=goto_on_highlight,
                goto_side_by_side=goto_side_by_side,
                quick_panel_item_opts={
                    "show_namespace": True,
                    "show_row_col": False,
                },
            )

        def run_():
            view_analysis_ = (
                view_analysis(active_view_id_, not_found=None) if active_view_ else None
            )

            project_path_ = project_path(window_)

            paths_analysis_ = paths_analysis(project_path_, not_found=None)

            analysis_ = paths_analysis_ or view_analysis_ or {}

            thingy_list = thingy_dedupe(
                [
                    *namespace_definitions(analysis_),
                    *var_definitions(analysis_),
                    *keyword_regs(analysis_),
                ],
            )

            thingy_list = sorted(thingy_list, key=thingy_name)

            sublime.set_timeout(lambda: done_(thingy_list), 0)

        progress.start("")

        threading.Thread(target=run_).start()


class PgPepGotoAnythingInViewCommand(sublime_plugin.TextCommand):
    """
    Goto namespace, var or keyword in paths or view.
    """

    def run(self, edit):
        view_analysis_ = view_analysis(self.view.id())

        thingy_list = thingy_dedupe(
            [
                *namespace_definitions(view_analysis_),
                *var_definitions(view_analysis_),
                *keyword_regs(view_analysis_),
            ],
        )

        thingy_list = sorted(
            thingy_list,
            key=lambda thingy: (
                thingy["row"],
                thingy["col"],
            ),
        )

        goto_thingy(
            self.view.window(),
            thingy_list,
            goto_on_highlight=True,
            goto_side_by_side=False,
            quick_panel_item_opts={
                "show_namespace": False,
                "show_row_col": False,
                "show_filename": False,
            },
        )


class PgPepGotoKeywordInClasspathCommand(sublime_plugin.WindowCommand):
    """
    Goto Keyword in classpath.
    """

    def run(
        self,
        goto_on_highlight=False,
        goto_side_by_side=False,
        show_filename=True,
        show_row_col=False,
    ):
        project_path_ = project_path(self.window)

        if classpath_analysis_ := classpath_analysis(project_path_, not_found=None):
            thingy_list = thingy_dedupe(keyword_regs(classpath_analysis_))

            thingy_list = sorted(thingy_list, key=thingy_name)

            goto_thingy(
                self.window,
                thingy_list,
                goto_on_highlight=goto_on_highlight,
                goto_side_by_side=goto_side_by_side,
                quick_panel_item_opts={
                    "show_row_col": show_row_col,
                    "show_filename": show_filename,
                },
            )


class PgPepGotoKeywordInViewPathsCommand(sublime_plugin.WindowCommand):
    """
    Goto to keyword in paths or view.
    """

    def run(
        self,
        goto_on_highlight=False,
        goto_side_by_side=False,
        show_filename=False,
        show_row_col=False,
    ):
        active_view = self.window.active_view()

        view_analysis_ = (
            view_analysis(active_view.id(), not_found=None) if active_view else None
        )

        project_path_ = project_path(self.window)

        paths_analysis_ = paths_analysis(project_path_, not_found=None)

        if analysis_ := paths_analysis_ or view_analysis_:
            thingy_list = thingy_dedupe(keyword_regs(analysis_))

            thingy_list = sorted(thingy_list, key=thingy_name)

            goto_thingy(
                self.window,
                thingy_list,
                goto_on_highlight=goto_on_highlight,
                goto_side_by_side=goto_side_by_side,
                quick_panel_item_opts={
                    "show_row_col": show_row_col,
                    "show_filename": show_filename,
                },
            )


class PgPepGotoNamespaceInClasspathCommand(sublime_plugin.WindowCommand):
    """
    Goto namespace in paths or view.
    """

    def run(
        self,
        goto_on_highlight=False,
        goto_side_by_side=False,
        show_filename=False,
        show_row_col=False,
    ):
        window_ = self.window

        project_path_ = project_path(self.window)

        def done_(thingy_list):
            progress.stop()

            goto_thingy(
                window_,
                thingy_list,
                goto_on_highlight=goto_on_highlight,
                goto_side_by_side=goto_side_by_side,
                quick_panel_item_opts={
                    "show_filename": show_filename,
                    "show_row_col": show_row_col,
                },
            )

        def run_():
            analysis_ = classpath_analysis(project_path_, not_found={})

            thingy_list = thingy_dedupe(namespace_definitions(analysis_))
            thingy_list = sorted(thingy_list, key=thingy_name)

            sublime.set_timeout(lambda: done_(thingy_list), 0)

        progress.start("")

        threading.Thread(target=run_).start()


class PgPepGotoNamespaceInViewPathsCommand(sublime_plugin.WindowCommand):
    """
    Goto namespace in paths or view.
    """

    def run(
        self,
        goto_on_highlight=False,
        goto_side_by_side=False,
        show_filename=False,
        show_row_col=False,
    ):
        window_ = self.window

        project_path_ = project_path(self.window)

        def done_(thingy_list):
            progress.stop()

            goto_thingy(
                window_,
                thingy_list,
                goto_on_highlight=goto_on_highlight,
                goto_side_by_side=goto_side_by_side,
                quick_panel_item_opts={
                    "show_filename": show_filename,
                    "show_row_col": show_row_col,
                },
            )

        def run_():
            analysis_ = paths_analysis(project_path_, not_found={})

            thingy_list = thingy_dedupe(namespace_definitions(analysis_))
            thingy_list = sorted(thingy_list, key=thingy_name)

            sublime.set_timeout(lambda: done_(thingy_list), 0)

        progress.start("")

        threading.Thread(target=run_).start()


class PgPepGotoDefinitionCommand(sublime_plugin.TextCommand):
    """
    Command to goto definition of a var, namespace, and keyword.

    In case of a keyword, it works for re-frame handlers and Clojure Spec.
    """

    def run(
        self,
        edit,
        goto_on_highlight=True,
        goto_side_by_side=False,
    ):
        view_ = self.view
        view_id_ = self.view.id()
        view_sel_ = self.view.sel()
        window_ = self.view.window()

        def done_(thingy_definitions):
            progress.stop()

            if not thingy_definitions:
                return

            thingy_definitions = thingy_dedupe(thingy_definitions)

            if len(thingy_definitions) == 1:
                location = thingy_location(thingy_definitions[0])

                goto(
                    window_,
                    location,
                    GOTO_SIDE_BY_SIDE_FLAGS
                    if goto_side_by_side
                    else GOTO_DEFAULT_FLAGS,
                )

            else:
                thingy_definitions_sorted = sorted(
                    thingy_definitions,
                    key=lambda thingy_definition: [
                        thingy_definition.get("filename"),
                        thingy_definition.get("row"),
                        thingy_definition.get("col"),
                    ],
                )

                goto_thingy(
                    window_,
                    thingy_definitions_sorted,
                    goto_on_highlight=goto_on_highlight,
                    goto_side_by_side=goto_side_by_side,
                    quick_panel_item_opts={
                        "show_namespace": True,
                        "show_row_col": False,
                    },
                )

        def run_():
            project_path_ = project_path(window_)

            def paths_analysis_delay():
                analysis = None

                def f():
                    nonlocal analysis
                    if analysis is None:
                        analysis = paths_analysis(project_path_)
                    return analysis

                return f

            view_analysis_ = view_analysis(view_id_)

            classpath_analysis_ = classpath_analysis(project_path_)

            paths_analysis_ = paths_analysis_delay()

            # Store usages of Thingy at region(s).
            thingy_definitions_ = []

            for region in view_sel_:
                if thingy := thingy_at(view_, view_analysis_, region):
                    if (
                        thingy_definitions := find_definitions(
                            analysis=view_analysis_,
                            thingy=thingy,
                        )
                        or find_definitions(
                            analysis=paths_analysis_(),
                            thingy=thingy,
                        )
                        or find_definitions(
                            analysis=classpath_analysis_,
                            thingy=thingy,
                        )
                    ):
                        thingy_definitions_.extend(thingy_definitions)

            sublime.set_timeout(lambda: done_(thingy_definitions_), 0)

        progress.start("")

        threading.Thread(target=run_).start()


class PgPepGotoNamespaceUsageInViewCommand(sublime_plugin.TextCommand):
    """
    Goto usages of namespace in buffer.

    Namespace is extracted from a namespace usage or var usage.
    """

    def run(self, edit):
        view_analysis_ = view_analysis(self.view.id())

        thingy_list = []

        for region in self.view.sel():
            if thingy := thingy_at(self.view, view_analysis_, region):
                thingy_semantic = thingy["_semantic"]

                namespace = None

                if thingy_semantic == TT_VAR_USAGE:
                    namespace = thingy["to"]

                elif (
                    thingy_semantic == TT_NAMESPACE_USAGE
                    or thingy_semantic == TT_NAMESPACE_USAGE_ALIAS
                ):
                    namespace = thingy["to"]

                if namespace:
                    thingy_list.extend(
                        find_namespace_vars_usages(
                            view_analysis_,
                            namespace,
                        )
                    )

        if thingy_list:
            thingy_list = sorted(
                thingy_list,
                key=lambda thingy: (
                    thingy["row"],
                    thingy["col"],
                ),
            )

            goto_thingy(
                self.view.window(),
                thingy_list,
                goto_on_highlight=True,
                goto_side_by_side=False,
                quick_panel_item_opts={
                    "show_namespace": True,
                    "show_row_col": True,
                },
            )


class PgPepGotoWarningErrorInViewCommand(sublime_plugin.WindowCommand):
    def run(
        self,
        goto_on_highlight=True,
        goto_side_by_side=False,
    ):
        try:
            active_view = self.window.active_view()

            view_analysis_ = view_analysis(active_view.id()) if active_view else {}

            thingy_list = analysis_findings(view_analysis_)

            thingy_list = sorted(
                thingy_list,
                key=lambda thingy_usage: [
                    thingy_usage.get("row"),
                    thingy_usage.get("col"),
                ],
            )

            goto_thingy(
                self.window,
                thingy_list,
                goto_on_highlight=goto_on_highlight,
                goto_side_by_side=goto_side_by_side,
            )

        except Exception:
            print("Pep: Error: PgPepGotoWarningErrorCommand", traceback.format_exc())


class PgPepGotoRequireImportInViewCommand(sublime_plugin.TextCommand):
    """
    Command to goto to a require or import form for the thingy under cursor.
    """

    def run(self, edit):
        try:
            view_analysis_ = view_analysis(self.view.id())

            cursor_region = self.view.sel()[0]

            if thingy := thingy_at(self.view, view_analysis_, cursor_region):
                if cursor_namespace_usage := thingy.get("to"):
                    nindex_usages = analysis_nindex_usages(view_analysis_)

                    if namespace_usages := nindex_usages.get(cursor_namespace_usage):
                        # Goto first usage only.
                        # TODO: Show a QuickPanel if there are multiple options.
                        goto(self.view.window(), thingy_location(namespace_usages[0]))

                elif cursor_class_usage := thingy.get("class"):
                    jindex_usages = analysis_jindex_usages(view_analysis_)

                    if class_usages := jindex_usages.get(cursor_class_usage):
                        # Goto first usage only.
                        # TODO: Show a QuickPanel if there are multiple options.
                        goto(self.view.window(), thingy_location(class_usages[0]))

        except Exception:
            print("Pep: Error: PgPepGotoRequireImportCommand", traceback.format_exc())


def goto_thingy_usage(
    window,
    thingy_usages,
    goto_on_highlight=False,
    goto_side_by_side=False,
):
    if not thingy_usages:
        return

    thingy_usages_ = thingy_dedupe(thingy_usages)

    if len(thingy_usages_) == 1:
        location = thingy_location(thingy_usages_[0])

        goto(
            window,
            location,
            GOTO_SIDE_BY_SIDE_FLAGS if goto_side_by_side else GOTO_DEFAULT_FLAGS,
        )

    else:
        thingy_usages_sorted = sorted(
            thingy_usages_,
            key=lambda thingy_usage: [
                thingy_usage.get("filename"),
                thingy_usage.get("row"),
                thingy_usage.get("col"),
            ],
        )

        # TODO: Quick Panel Item options per semantic.

        goto_thingy(
            window,
            thingy_usages_sorted,
            goto_on_highlight=goto_on_highlight,
            goto_side_by_side=goto_side_by_side,
            quick_panel_item_opts={
                "show_namespace": True,
                "show_row_col": True,
                "show_filename": False,
            },
        )


class PgPepGotoUsageCommand(sublime_plugin.TextCommand):
    def run(
        self,
        edit,
        goto_on_highlight=False,
        goto_side_by_side=False,
    ):
        view_ = self.view
        view_id_ = self.view.id()
        view_sel_ = self.view.sel()
        window_ = self.view.window()

        def done_(thingy_usages):
            progress.stop()

            goto_thingy_usage(
                window_,
                thingy_usages,
                goto_on_highlight=goto_on_highlight,
                goto_side_by_side=goto_side_by_side,
            )

        def run_():
            view_analysis_ = view_analysis(view_id_)

            project_path_ = project_path(window_)

            paths_analysis_ = paths_analysis(project_path_)

            # Store usages of Thingy at region(s).
            thingy_usages_ = []

            for region in view_sel_:
                if thingy := thingy_at(view_, view_analysis_, region):
                    if thingy_usages := find_usages(
                        analysis=paths_analysis_,
                        thingy=thingy,
                    ) or find_usages(
                        analysis=view_analysis_,
                        thingy=thingy,
                    ):
                        thingy_usages_.extend(thingy_usages)

            sublime.set_timeout(lambda: done_(thingy_usages_), 0)

        progress.start("")

        threading.Thread(target=run_).start()


class PgPepGotoUsageInViewCommand(sublime_plugin.TextCommand):
    def run(
        self,
        edit,
        goto_on_highlight=True,
        goto_side_by_side=False,
    ):
        view_analysis_ = view_analysis(self.view.id())

        # Store usages of Thingy at region(s).
        thingy_usages_ = []

        for region in self.view.sel():
            if thingy := thingy_at(self.view, view_analysis_, region):
                if thingy_usages := find_usages(
                    analysis=view_analysis_,
                    thingy=thingy,
                ):
                    thingy_usages_.extend(thingy_usages)

        goto_thingy_usage(
            self.view.window(),
            thingy_usages_,
            goto_on_highlight=goto_on_highlight,
            goto_side_by_side=goto_side_by_side,
        )


class PgPepFindUsagesCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        view_analysis_ = view_analysis(self.view.id())

        project_path_ = project_path(self.view.window())

        paths_analysis_ = paths_analysis(project_path_)

        # Mapping of Thingy's name to its usages.
        thingy_name_to_usages = {}

        for region in self.view.sel():
            if thingy := thingy_at(self.view, view_analysis_, region):
                thingy_usages = find_usages(
                    analysis=paths_analysis_,
                    thingy=thingy,
                ) or find_usages(
                    analysis=view_analysis_,
                    thingy=thingy,
                )

                thingy_name_to_usages[thingy_name(thingy)] = thingy_usages or []

        usages_content = []

        for thingy_name_, thingy_usages_ in thingy_name_to_usages.items():
            thingy_usages_ = thingy_dedupe(thingy_usages_)

            thingy_usages_sorted = sorted(
                thingy_usages_,
                key=lambda thingy_usage: [
                    thingy_usage.get("filename"),
                    thingy_usage.get("row"),
                    thingy_usage.get("col"),
                ],
            )

            name_usages_content = []

            for thingy_usage in thingy_usages_sorted:
                if location := thingy_location(thingy_usage):
                    name_usages_content.append(
                        f'- {location.get("filename")}:{location.get("line")}:{location.get("column")}'
                    )

            usages_content.append("Find Usages: " + thingy_name_)
            usages_content.append(
                "\n".join(name_usages_content) if name_usages_content else "Not found."
            )

        panel = output_panel(self.view.window())
        panel.settings().set("gutter", False)
        panel.settings().set("result_file_regex", r"^- (.*):([0-9]+):([0-9]+)$")
        panel.settings().set("result_line_regex", r"^- (.*):([0-9]+):([0-9]+)$")
        panel.settings().set("highlight_line", False)
        panel.settings().set("line_numbers", False)
        panel.settings().set("gutter", False)
        panel.settings().set("scroll_past_end", False)

        panel.set_read_only(False)

        replace_output_panel_content(panel, "\n\n".join(usages_content))

        panel.set_read_only(True)

        show_output_panel(self.view.window())


class PgPepSelectCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        try:
            view_analysis_ = view_analysis(self.view.id())

            regions = []

            for region in self.view.sel():
                if thingy := thingy_in_region(
                    self.view,
                    view_analysis_,
                    region,
                ):
                    if thingy_regions := find_thingy_text_regions(
                        self.view,
                        view_analysis_,
                        thingy,
                    ):
                        regions.extend(thingy_regions)

            if regions:
                self.view.sel().clear()
                self.view.sel().add_all(regions)

        except Exception:
            print("Pep: Error: PgPepSelectCommand", traceback.format_exc())


class PgPepReplaceCommand(sublime_plugin.TextCommand):
    def input(self, args):
        if "text" not in args:
            view_analysis_ = view_analysis(self.view.id())

            cursor_region = self.view.sel()[0]

            if cursor_thingy := thingy_in_region(
                self.view, view_analysis_, cursor_region
            ):
                return ReplaceTextInputHandler(
                    text=thingy_text(self.view, cursor_thingy)
                )

    def run(self, edit, text):
        try:
            view_analysis_ = view_analysis(self.view.id())

            cursor_region = self.view.sel()[0]

            if thingy := thingy_in_region(
                self.view,
                view_analysis_,
                cursor_region,
            ):
                thingy_regions = find_thingy_text_regions(
                    self.view,
                    view_analysis_,
                    thingy,
                )

                # Dedupe regions - it's necessary because clj-kondo duplicates data for .cljc
                # (It's duplicate because clj-kondo returns data for each 'lang' - clj/cljs)
                thingy_regions = list(
                    {
                        (
                            region.a,
                            region.b,
                        ): region
                        for region in thingy_regions
                    }.values()
                )

                adjust = 0

                for thingy_region in thingy_regions:
                    replace = sublime.Region(
                        thingy_region.a - adjust,
                        thingy_region.b - adjust,
                    )

                    adjust += replace.size() - len(text)

                    self.view.replace(edit, replace, text)

        except Exception:
            print("Pep: Error: PgPepReplaceCommand", traceback.format_exc())


class PgPepHighlightCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        highlight_thingy(self.view)


class PgPepToggleViewAnnotationsCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        # Is enabled by default:
        annotate = self.view.settings().get(SETTING_ANNOTATE_VIEW, True)

        self.view.settings().set(SETTING_ANNOTATE_VIEW, not annotate)


class PgPepViewSummaryStatusCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        try:
            analysis = view_analysis(self.view.id())

            status_messages = []

            if view_status_show_errors(self.view.window()):
                if summary_errors := analysis_summary(analysis).get("error"):
                    status_messages.append(f"Errors: {summary_errors}")

            if view_status_show_warnings(self.view.window()):
                if summary_warnings := analysis_summary(analysis).get("warning"):
                    status_messages.append(f"Warnings: {summary_warnings}")

            status_message = ", ".join(status_messages) if status_messages else ""

            # Show the number of errors and/or warnings.
            # (Setting the value to the empty string will clear the status.)
            self.view.set_status("pg_pep_view_summary", status_message)

        except Exception:
            print("Pep: Error: PgPepViewSummaryStatusCommand", traceback.format_exc())


class PgPepShowOutputPanelCommand(sublime_plugin.WindowCommand):
    def run(self):
        show_output_panel(self.window)


## ------------------------------------------------------------------
## Pep V2
## ------------------------------------------------------------------


class PgPepV2DiagnosticsCommand(sublime_plugin.WindowCommand):
    """
    Project's diagnostics.
    """

    def input(self, args):
        if "root_path" not in args:
            return RootPathInputHandler()

    def run(self, root_path):
        def handle_response(root_path, response):
            if error := response.get("error"):
                print("Pep Error:", error)

                return

            contents = ["Diagnostics", f"Root Path: {root_path}"]

            summary = response.get("success", {}).get("summary", {})

            contents.append(
                f"Files: {summary.get('files')}, Duration: {summary.get('duration')}"
            )

            contents.append(
                f"Errors: {summary.get('error')}, Warnings: {summary.get('warning')}"
            )

            diagnostics = response.get("success", {}).get("diagnostics", {})

            for index, diagnostic in enumerate(diagnostics.get("error", [])):
                if location := thingy_location(diagnostic):
                    contents.append(
                        f'{index+1}. Error: {diagnostic.get("message")}\n{location.get("filename")}:{location.get("line")}:{location.get("column")}'
                    )

            for index, diagnostic in enumerate(diagnostics.get("warning", [])):
                if location := thingy_location(diagnostic):
                    contents.append(
                        f'{index+1}. Warning: {diagnostic.get("message")}\n{location.get("filename")}:{location.get("line")}:{location.get("column")}'
                    )

            panel = output_panel(self.window)
            panel.settings().set("gutter", False)
            panel.settings().set("result_file_regex", r"^(.*):([0-9]+):([0-9]+)$")
            panel.settings().set("result_line_regex", r"^(.*):([0-9]+):([0-9]+)$")
            panel.settings().set("highlight_line", False)
            panel.settings().set("line_numbers", False)
            panel.settings().set("gutter", False)
            panel.settings().set("scroll_past_end", False)

            panel.set_read_only(False)

            replace_output_panel_content(panel, "\n\n".join(contents))

            panel.set_read_only(True)

            panel.show_at_center(0)

            show_output_panel(self.window)

        def run_():
            try:
                progress.start("Running Diagnostics...")

                response = with_clientsocket_retry(
                    lambda c: op.diagnostics(c, root_path)
                )

                sublime.set_timeout(lambda: handle_response(root_path, response), 0)
            except Exception:
                print("Pep Error:", traceback.format_exc())
            finally:
                progress.stop()

        threading.Thread(target=run_).start()


class PgPepV2AnalyzeCommand(sublime_plugin.WindowCommand):
    def input(self, args):
        if "root_path" not in args:
            return RootPathInputHandler()

    def run(self, root_path):
        def handle_response(root_path, response):
            if error := response.get("error"):
                print("Pep Error:", error)

                return

            contents = ["Analysis", f"Root Path: {root_path}"]

            summary = response.get("success", {}).get("summary", {})

            contents.append(
                f"Files: {summary.get('files')}, Duration: {summary.get('duration')}"
            )

            panel = output_panel(self.window)
            panel.settings().set("gutter", False)
            panel.settings().set("highlight_line", False)
            panel.settings().set("line_numbers", False)
            panel.settings().set("gutter", False)
            panel.settings().set("scroll_past_end", False)

            panel.set_read_only(False)

            replace_output_panel_content(panel, "\n\n".join(contents))

            panel.set_read_only(True)

            panel.show_at_center(0)

            show_output_panel(self.window)

        def run_():
            try:
                progress.start("Running Analysis...")

                response = with_clientsocket_retry(
                    lambda c: op.analyze_paths(c, root_path)
                )

                sublime.set_timeout(
                    lambda: handle_response(root_path, response),
                    0,
                )
            except Exception:
                print("Pep Error:", traceback.format_exc())
            finally:
                progress.stop()

        threading.Thread(target=run_).start()


class PgPepV2GotoNamespaceDefaultsCommand(sublime_plugin.WindowCommand):
    def run(self):
        args = None

        if root_path := window_root_path(self.window):
            args = {"root_path": root_path}

        self.window.run_command("pg_pep_v2_goto_namespace", args)


class PgPepV2GotoNamespaceCommand(sublime_plugin.WindowCommand):
    def input(self, args):
        if "root_path" not in args:
            return RootPathInputHandler()

    def run(self, root_path):
        def handle_response(root_path, response):
            if error := response.get("error"):
                print("Pep Error:", error)

                return

            goto_thingy(
                self.window,
                response.get("success"),
                goto_on_highlight=False,
                goto_side_by_side=False,
                quick_panel_item_opts={
                    "show_filename": False,
                    "show_row_col": False,
                },
            )

        def run_():
            try:
                progress.start("")

                response = with_clientsocket_retry(
                    lambda c: op.namespace_definitions(c, root_path)
                )

                sublime.set_timeout(
                    lambda: handle_response(root_path, response),
                    0,
                )
            except Exception:
                print("Pep Error:", traceback.format_exc())
            finally:
                progress.stop()

        threading.Thread(target=run_).start()


class PgPepV2GotoDefinitionDefaultsCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        args = None

        if root_path := window_root_path(self.view.window()):
            args = {"root_path": root_path}

        self.view.run_command("pg_pep_v2_goto_definition", args)


class PgPepV2GotoDefinitionCommand(sublime_plugin.TextCommand):
    def input(self, args):
        if "root_path" not in args:
            return RootPathInputHandler()

    def run(self, edit, root_path):
        def handle_response(root_path, response):
            if error := response.get("error"):
                print("Pep Error:", error)

                return

            definitions = response.get("success") or []

            if len(definitions) == 1:
                location = thingy_location(definitions[0])

                goto(
                    self.view.window(),
                    location,
                    GOTO_DEFAULT_FLAGS,
                )
            else:
                goto_thingy(
                    self.view.window(),
                    response.get("success"),
                    goto_on_highlight=False,
                    goto_side_by_side=False,
                    quick_panel_item_opts={
                        "show_filename": False,
                        "show_row_col": False,
                    },
                )

        def run_():
            try:
                progress.start("")

                region = self.view.sel()[0]

                # The second end of the region. In a selection this is the location of the caret. May be less than a.
                caret = region.b

                row, col = self.view.rowcol(caret)

                response = with_clientsocket_retry(
                    lambda c: op.find_definitions(
                        c,
                        root_path=root_path,
                        filename=self.view.file_name(),
                        row=row + 1,
                        col=col + 1,
                    )
                )

                sublime.set_timeout(
                    lambda: handle_response(root_path, response),
                    0,
                )
            except Exception:
                print("Pep Error:", traceback.format_exc())
            finally:
                progress.stop()

        threading.Thread(target=run_).start()


# ---


class PgPepViewListener(sublime_plugin.ViewEventListener):
    """
    These 'actions' are configured via settings.

    You might want to disable running analyzes on load & save for instance.

    See Pep.sublime-settings.
    """

    @classmethod
    def is_applicable(cls, settings):
        return settings.get("syntax") in set(
            analysis_applicable_to(sublime.active_window())
        )

    def __init__(self, view):
        super().__init__(view)

        self.analyzer = None
        self.analyzer_v2 = None
        self.highlighter = None
        self.is_highlight_pending = False

    def analyze(self, afs=DEFAULT_VIEW_ANALYSIS_FUNCTIONS):
        analyze_view = True

        if self.view.is_scratch():
            analyze_view = analyze_scratch_view(self.view.window())

        if analyze_view:
            analyze_view_async(self.view, afs)

    def analyze_v2(self):
        analyze_view = True

        if self.view.is_scratch():
            analyze_view = analyze_scratch_view(self.view.window())

        if analyze_view:
            analyze_view_v2(self.view)

    def highlight(self):
        self.is_highlight_pending = False

        highlight_thingy(self.view)

    def on_load(self):
        self.analyze()
        self.analyze_v2()

    def on_activated_async(self):
        self.analyze()
        self.analyze_v2()

    def on_modified_async(self):
        if self.analyzer_v2:
            self.analyzer_v2.cancel()

        analysis_delay_ = analysis_delay(self.view.window())

        self.analyzer_v2 = threading.Timer(analysis_delay_, self.analyze_v2)
        self.analyzer_v2.start()

    def on_selection_modified_async(self):
        if self.highlighter:
            self.highlighter.cancel()

        if automatically_highlight(self.view.window()):
            interval = 0.3 if self.is_highlight_pending else 0.1

            self.is_highlight_pending = True

            self.highlighter = threading.Timer(interval, self.highlight)
            self.highlighter.start()

    def on_post_save_async(self):
        # Include function to annotate view on save (if applicable).
        self.analyze(afs=[*DEFAULT_VIEW_ANALYSIS_FUNCTIONS, af_annotate_on_save])

    def on_close(self):
        """
        It's important to delete a view's state on close.
        """
        set_view_analysis(self.view.id(), {})


class PgPepEventListener(sublime_plugin.EventListener):
    """
    Paths and classpath are analyzed when a project is loaded.

    Analysis are cleared when a project is closed.
    """

    def on_load_project_async(self, window):
        if setting(window, "analyze_paths_on_load_project", False):
            analyze_paths_async(window)

        if setting(window, "analyze_classpath_on_load_project", False):
            analyze_classpath_async(window)

    def on_pre_close_project(self, window):
        """
        Called right before a project is closed.
        """
        if project_path_ := project_path(window):
            if is_debug(window):
                print(f"Pep Debug: Clear project cache: {project_path_}")

            clear_project_index(project_path_)

            set_classpath_analysis(project_path_, {})

    def on_pre_close_window(self, window):
        """
        Called right before a window is closed.
        """
        global _client_socket_

        if _client_socket_:
            _client_socket_.close()
            _client_socket_ = None


# ---


def plugin_loaded():
    if window := sublime.active_window():
        if setting(window, "analyze_paths_on_plugin_loaded", False):
            analyze_paths_async(window)

        if setting(window, "analyze_classpath_on_plugin_loaded", False):
            analyze_classpath_async(window)
