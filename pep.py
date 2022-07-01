import html
import inspect
import subprocess
import os
import re
import tempfile
import json
import traceback
import pprint
import threading
import time
import linecache
import pathlib
import shlex
import time

from zipfile import ZipFile

import sublime_plugin
import sublime


GOTO_DEFAULT_FLAGS = sublime.ENCODED_POSITION

GOTO_USAGE_FLAGS = sublime.ENCODED_POSITION | sublime.TRANSIENT

GOTO_SIDE_BY_SIDE_FLAGS = (
    sublime.ENCODED_POSITION
    | sublime.SEMI_TRANSIENT
    | sublime.ADD_TO_SELECTION
    | sublime.CLEAR_TO_RIGHT
)


# Thingy types

TT_FINDING = "finding"
TT_KEYWORD = "keyword"
TT_LOCAL_BINDING = "local_binding"
TT_LOCAL_USAGE = "local_usage"
TT_VAR_DEFINITION = "var_definition"
TT_VAR_USAGE = "var_usage"
TT_NAMESPACE_DEFINITION = "namespace_definition"
TT_NAMESPACE_USAGE = "namespace_usage"
TT_NAMESPACE_USAGE_ALIAS = "namespace_usage_alias"
TT_JAVA_CLASS_USAGE = "java_class_usage"

OUTPUT_PANEL_NAME = "pep"
OUTPUT_PANEL_NAME_PREFIXED = f"output.{OUTPUT_PANEL_NAME}"

HIGHLIGHTED_REGIONS_KEY = "pg_pep_highligths"
HIGHLIGHTED_STATUS_KEY = "pg_pep_highligths"

# Setting used to override the clj-kondo config for a view analysis.
S_PEP_CLJ_KONDO_CONFIG = "pep_clj_kondo_config"

# Status bar key used to show documentation.
STATUS_BAR_DOC_KEY = "pep_doc"

_view_analysis_ = {}

_paths_analysis_ = {}

_classpath_analysis_ = {}


def clear_cache():
    global _view_analysis_
    _view_analysis_ = {}

    global _paths_analysis_
    _paths_analysis_ = {}

    global _classpath_analysis_
    _classpath_analysis_ = {}


# -- Settings


def settings():
    return sublime.load_settings("Pep.sublime-settings")


def project_data(window):
    return window.project_data().get("pep", {}) if window.project_data() else {}


def setting(window, k, not_found):
    v = project_data(window).get(k)

    return v if v is not None else settings().get(k, not_found)


def is_debug(window):
    return setting(window, "debug", False)


def automatically_highlight(window):
    return setting(window, "automatically_highlight", False)


def annotate_view_analysis(window):
    return setting(window, "annotate_view_analysis", False)


def annotation_font_size(window):
    return setting(window, "annotation_font_size", "0.9em")


def analyze_scratch_view(window):
    return setting(window, "analyze_scratch_view", False)


def view_status_show_namespace(window):
    return setting(window, "view_status_show_namespace", False)


def view_status_show_namespace_prefix(window):
    return setting(window, "view_status_show_namespace_prefix", "")


def view_status_show_namespace_suffix(window):
    return setting(window, "view_status_show_namespace_suffix", "")


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


def clj_kondo_path(window):
    return setting(window, "clj_kondo_path", None)


# -- Output


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


# -- Analysis


def set_paths_analysis(project_path, analysis):
    """
    Updates analysis for paths.
    """
    global _paths_analysis_
    _paths_analysis_[project_path] = analysis


def paths_analysis(project_path):
    """
    Returns analysis for paths.
    """
    global _paths_analysis_
    return _paths_analysis_.get(project_path, {})


def set_classpath_analysis(project_path, analysis):
    """
    Updates analysis for project.
    """
    global _classpath_analysis_
    _classpath_analysis_[project_path] = analysis


def classpath_analysis(project_path):
    """
    Returns analysis for project.
    """
    global _classpath_analysis_
    return _classpath_analysis_.get(project_path, {})


def set_view_analysis(view_id, analysis):
    """
    Updates analysis for a particular view.
    """
    global _view_analysis_
    _view_analysis_[view_id] = analysis


def view_analysis(view_id):
    """
    Returns analysis for a particular view.
    """
    global _view_analysis_
    return _view_analysis_.get(view_id, {})


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


def namespace_definitions(analysis):
    """
    Returns a list of namespace definitions.
    """

    l = []

    for namespace_definitions in analysis_nindex(analysis).values():
        for namespace_definition in namespace_definitions:
            l.append(namespace_definition)

    return l


def var_definitions(analysis):
    """
    Returns a list of var definitions.
    """

    l = []

    for var_definitions in analysis_vindex(analysis).values():
        for var_definition in var_definitions:
            l.append(var_definition)

    return l


def var_usages(analysis, name):
    """
    Returns Var usages for name.
    """

    usages = analysis_vindex_usages(analysis).get(name, [])

    return remove_empty_rows(usages)


def recursive_usage(thingy_usage):
    usage_from = thingy_usage.get("from")
    usage_to = thingy_usage.get("to")

    usage_name = thingy_usage.get("name")
    usage_from_var = thingy_usage.get("from-var")

    is_same_ns = usage_from == usage_to
    is_same_var = usage_name == usage_from_var

    return is_same_ns and is_same_var


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


def keyword_index(
    analysis,
    kindex=True,
):
    # Keywords indexed by name - tuple of namespace and name.
    kindex_ = {}

    if kindex:
        for keyword in analysis.get("keywords", []):
            ns = keyword.get("ns")
            name = keyword.get("name")
            row = keyword.get("row")

            kindex_.setdefault((ns, name), []).append(keyword)

    return {
        "kindex": kindex_,
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
            jindex_[java_class_definition.get("class")] = java_class_definition

    # Java class usages indexed by row.
    jrn_usages_ = {}

    # Java class usages indexed by name - Class name to a set of class usages.
    jindex_usages_ = {}

    if jindex_usages or jrn_usages:
        for java_class_usage in analysis.get("java-class-usages", []):

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
    return [thingy_data for thingy_data in thingies if thingy_data["row"] != None]


def staled_analysis(view):
    """
    Returns True if view was modified since last analysis.
    """
    return view.change_count() != analysis_view_change_count(view)


def view_navigation(view_state):
    return view_state.get("navigation", {})


def set_view_navigation(view_state, navigation):
    view_state["navigation"] = navigation


def project_path(window):
    return window.extract_variables().get("project_path")


def project_data_classpath(window):
    """
    Example:

    ["clojure", "-Spath"]
    """
    if project_data := window.project_data():
        return project_data.get("pep", {}).get("classpath")


def project_data_paths(window):
    """
    Example:

    ["src", "test"]
    """
    if project_data := window.project_data():
        return project_data.get("pep", {}).get("paths")


def view_analysis_completed(view):
    def on_completed(analysis):
        view.run_command("pg_pep_annotate")
        view.run_command("pg_pep_view_summary_status")
        view.run_command("pg_pep_view_namespace_status")

    return on_completed


# ---


# Copied from https://github.com/SublimeText/UnitTesting/blob/master/unittesting/utils/progress_bar.py


class ProgressBar:
    def __init__(self, label, width=10):
        self.label = label
        self.width = width

    def start(self):
        self.done = False
        self.update()

    def stop(self):
        sublime.status_message("")
        self.done = True

    def update(self, status=0):
        if self.done:
            return
        status = status % (2 * self.width)
        before = min(status, (2 * self.width) - status)
        after = self.width - before
        sublime.status_message("%s [%s=%s]" % (self.label, " " * before, " " * after))
        sublime.set_timeout(lambda: self.update(status + 1), 100)


# Copied from https://github.com/eerohele/Tutkain


def htmlify(text):
    if text:
        return re.sub(r"\n", "<br/>", inspect.cleandoc(html.escape(text)))
    else:
        return ""


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


def open_jar(filename, f):
    """
    Open JAR `filename` and call `f` with filename and a file-like object (ZipExtFile).

    Filename passed to `f` is a temporary file and it will be removed afterwards.
    """

    filename_split = filename.split(":")
    filename_jar = filename_split[0]
    filename_file = filename_split[1]

    with ZipFile(filename_jar) as jar:
        with jar.open(filename_file) as jar_file:

            tmp_path = pathlib.Path(filename_file)
            tmp_file_suffix = "." + tmp_path.name

            descriptor, tempath = tempfile.mkstemp(suffix=tmp_file_suffix)

            with os.fdopen(descriptor, "w") as file:
                file.write(jar_file.read().decode())

            f(tempath, jar_file)


def getlines(filename, begin, end):
    """
    Returns a list of lines read from filename.

    `end` is inclusive.
    """

    return [linecache.getline(filename, lineno) for lineno in range(begin, end + 1)]


def goto(window, location, flags=sublime.ENCODED_POSITION):
    if location:
        filename = location["filename"]
        line = location["line"]
        column = location["column"]

        if ".jar:" in filename:

            def open_file(filename, file):
                view = window.open_file(f"{filename}:{line}:{column}", flags=flags)
                view.set_scratch(False)
                view.set_read_only(True)

                # Filename doesn't match the namespace name because it's a temp file,
                # and that's why the linter :namespace-name-mismatch is disabled.
                view.settings().set(
                    S_PEP_CLJ_KONDO_CONFIG,
                    "{:linters {:namespace-name-mismatch {:level :off}} :output {:analysis {:arglists true :locals true :keywords true :java-class-usages true} :format :json :canonical-paths true} }",
                )

            open_jar(filename, open_file)

        else:
            window.open_file(f"{filename}:{line}:{column}", flags=flags)


def thingy_quick_panel_item_annotation(thingy_data):
    """
    Uses a thingy lang or filename for QuickPanelItem's annotation.

    Note: clj-kondo adds 'lang' to .cljc files only.
    """
    return thingy_data.get("lang") or pathlib.Path(
        thingy_data.get("filename", "")
    ).suffix.replace(".", "")


def namespace_quick_panel_item(thingy_data):
    namespace_name = thingy_data.get("name", thingy_data.get("to", ""))

    return sublime.QuickPanelItem(
        namespace_name,
        kind=(sublime.KIND_ID_NAMESPACE, "n", ""),
        details=thingy_data.get("doc", ""),
        annotation=thingy_quick_panel_item_annotation(thingy_data),
    )


def var_quick_panel_item(thingy_data, namespace_visible=True):
    var_namespace = thingy_data.get("ns", thingy_data.get("to", ""))
    var_name = thingy_data.get("name", "")
    var_arglist = thingy_data.get("arglist-strs", [])

    trigger = f"{var_namespace}/{var_name}" if namespace_visible else var_name

    annotation = thingy_quick_panel_item_annotation(thingy_data)

    if var_arglist:
        return sublime.QuickPanelItem(
            trigger,
            kind=sublime.KIND_FUNCTION,
            details=" ".join(var_arglist),
            annotation=annotation,
        )
    else:
        return sublime.QuickPanelItem(
            trigger,
            kind=sublime.KIND_VARIABLE,
            annotation=annotation,
        )


def keyword_quick_panel_item(thingy_data):
    keyword_namespace = thingy_data.get("ns", "")
    keyword_name = thingy_data.get("name", "")
    keyword_reg = thingy_data.get("reg", "")

    trigger = ":" + (
        f"{keyword_namespace}/{keyword_name}" if keyword_namespace else keyword_name
    )

    return sublime.QuickPanelItem(
        trigger,
        kind=sublime.KIND_KEYWORD,
        details=keyword_reg,
        annotation=thingy_quick_panel_item_annotation(thingy_data),
    )


def var_goto_items(analysis, namespace_visible=True):
    items_ = []

    for var_definition in var_definitions(analysis):
        items_.append(
            {
                "thingy_type": TT_VAR_DEFINITION,
                "thingy_data": var_definition,
                "quick_panel_item": var_quick_panel_item(
                    var_definition, namespace_visible
                ),
            }
        )

    return items_


def keyword_goto_items(analysis):
    items_ = []

    for keywords_ in analysis_kindex(analysis).values():
        for keyword_ in keywords_:
            if reg := keyword_.get("reg", None):
                items_.append(
                    {
                        "thingy_type": TT_KEYWORD,
                        "thingy_data": keyword_,
                        "quick_panel_item": keyword_quick_panel_item(keyword_),
                    }
                )

    return items_


def namespace_goto_items(analysis):
    items_ = []

    for namespace_definition in namespace_definitions(analysis):
        items_.append(
            {
                "thingy_type": TT_NAMESPACE_DEFINITION,
                "thingy_data": namespace_definition,
                "quick_panel_item": namespace_quick_panel_item(namespace_definition),
            }
        )

    return items_


def preview_thingy(window, thingy_type, thingy_data):
    def peek_params(thingy_type, thingy_data):
        ns_ = thingy_data.get("ns", None)
        name_ = thingy_data.get("name", None)

        text_ = None
        syntax_ = None

        if thingy_type == TT_KEYWORD:
            text_ = f"{ns_}/{name_}" if ns_ else name_
            text_ = text_ + "\n\n" + thingy_data.get("reg", "")

        elif thingy_type == TT_VAR_DEFINITION:

            lineno_begin = thingy_data.get("row", thingy_data.get("name-row"))

            lineno_end = thingy_data.get("end-row", thingy_data.get("name-end-row"))

            thingy_filename = thingy_data["filename"]

            # TODO: Try to use the same syntax as the "origin".
            syntax_ = "Clojure.sublime-syntax"

            if ".jar:" in thingy_filename:

                def read_jar_source(filename, file):
                    nonlocal text_
                    text_ = "".join(getlines(filename, lineno_begin, lineno_end))

                open_jar(thingy_filename, read_jar_source)

            else:
                text_ = "".join(getlines(thingy_filename, lineno_begin, lineno_end))

        elif thingy_type == TT_NAMESPACE_DEFINITION:
            text_ = name_

            # Doc (optional)
            if doc_ := thingy_data.get("doc"):
                text_ = text_ + "\n\n" + re.sub(r"^ +", "", doc_, flags=re.M)

        else:
            text_ = f"{ns_}/{name_}" if ns_ else name_

        return {
            "characters": text_,
            "syntax": syntax_ or "Packages/Text/Plain text.tmLanguage",
        }

    params = peek_params(thingy_type, thingy_data)
    peek_characters = params["characters"]
    peek_syntax = params["syntax"]

    output_view_ = output_panel(window)
    output_view_.set_read_only(False)
    output_view_.assign_syntax(peek_syntax)
    output_view_.settings().set("line_numbers", False)
    output_view_.settings().set("gutter", False)
    output_view_.settings().set("is_widget", True)
    output_view_.run_command("select_all")
    output_view_.run_command("right_delete")
    output_view_.run_command(
        "append",
        {
            "characters": peek_characters,
        },
    )
    output_view_.set_read_only(True)

    show_output_panel(window)


def show_goto_thingy_quick_panel(window, items, goto_on_highlight=False):
    # Active view, if there's one, when the QuickPanel UI is shown.
    initial_view = window.active_view()

    # Set of views opened by the QuickPanel UI.
    goto_views = set()

    def on_highlight(index):
        thingy_data_ = items[index]["thingy_data"]

        location = thingy_location(thingy_data_)

        goto(window, location)

        # Book-keeping of opened views - initial view is not considered:

        goto_view = window.active_view()

        if not initial_view == goto_view:
            goto_views.add(goto_view)

    def on_select(index):
        if index == -1:
            # Close opened views and restore focus to initial view:

            for goto_view in goto_views:
                goto_view.close()

            if initial_view:
                window.focus_view(initial_view)
        else:
            thingy_data_ = items[index]["thingy_data"]

            location = thingy_location(thingy_data_)

            goto(window, location)

            to_be_closed = goto_views.difference({window.active_view()})

            # Close opened views - during goto highlight:
            for goto_view in to_be_closed:
                goto_view.close()

    quick_panel_items = [item_["quick_panel_item"] for item_ in items]

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


def view_text(view):
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


def analyze_view_clj_kondo(view):
    try:

        window = view.window()

        view_file_name = view.file_name()

        project_file_name = window.project_file_name() if window else None

        # Setting the working directory is important because of clj-kondo's cache.
        cwd = None

        if project_file_name:
            cwd = os.path.dirname(project_file_name)
        elif view_file_name:
            cwd = os.path.dirname(view_file_name)

        analysis_config = "{:output {:analysis {:arglists true :locals true :keywords true :java-class-usages true} :format :json :canonical-paths true} }"
        analysis_config = view.settings().get(S_PEP_CLJ_KONDO_CONFIG) or analysis_config

        # --lint <file>: a file can either be a normal file, directory or classpath.
        # In the case of a directory or classpath, only .clj, .cljs and .cljc will be processed.
        # Use - as filename for reading from stdin.

        # --filename <file>: in case stdin is used for linting, use this to set the reported filename.

        analysis_subprocess_args = [
            clj_kondo_path(view.window()),
            "--config",
            analysis_config,
            "--lint",
            "-",
            "--filename",
            view_file_name or "-",
        ]

        # Hide the console window on Windows.
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        analysis_completed_process = subprocess.run(
            analysis_subprocess_args,
            cwd=cwd,
            text=True,
            capture_output=True,
            startupinfo=startupinfo,
            input=view_text(view),
        )

        return json.loads(analysis_completed_process.stdout)

    except:
        # Always return a dict, no matter what.
        return {}


def analyze_view(view, on_completed=None):

    # Change count right before analyzing the view.
    # This will be stored in the analysis.
    view_change_count = view.change_count()

    clj_kondo_data = analyze_view_clj_kondo(view)

    analysis = clj_kondo_data.get("analysis", {})

    # Keywords indexed by row.
    krn = {}

    # Keywords indexed by name - tuple of namespace and name.
    kindex = {}

    for keyword in analysis.get("keywords", []):
        ns = keyword.get("ns")
        name = keyword.get("name")
        row = keyword.get("row")

        krn.setdefault(row, []).append(keyword)

        kindex.setdefault((ns, name), []).append(keyword)

    # Locals indexed by row.
    lrn = {}

    # Locals indexed by ID.
    lindex = {}

    for local_binding in analysis.get("locals", []):
        id = local_binding.get("id")
        row = local_binding.get("row")

        lrn.setdefault(row, []).append(local_binding)

        lindex[id] = local_binding

    # Local usages indexed by ID - local binding ID to a set of local usages.
    lindex_usages = {}

    # Local usages indexed by row.
    lrn_usages = {}

    for local_usage in analysis.get("local-usages", []):
        id = local_usage.get("id")
        name_row = local_usage.get("name-row")

        lindex_usages.setdefault(id, []).append(local_usage)

        lrn_usages.setdefault(name_row, []).append(local_usage)

    namespace_index_ = namespace_index(analysis)

    var_index_ = var_index(analysis)

    java_class_index_ = java_class_index(analysis)

    view_analysis_ = {
        **namespace_index_,
        **var_index_,
        **java_class_index_,
        "view_change_count": view_change_count,
        "findings": clj_kondo_data.get("findings", []),
        "summary": clj_kondo_data.get("summary", {}),
        "kindex": kindex,
        "krn": krn,
        "lindex": lindex,
        "lindex_usages": lindex_usages,
        "lrn": lrn,
        "lrn_usages": lrn_usages,
    }

    set_view_analysis(view.id(), view_analysis_)

    if on_completed:
        on_completed(view_analysis_)

    return True


def analyze_view_async(view, on_completed=None):
    threading.Thread(
        target=lambda: analyze_view(view, on_completed=on_completed), daemon=True
    ).start()


def analyze_classpath(window):
    """
    Analyze classpath to create indexes for var and namespace definitions.
    """

    if classpath := project_classpath(window):
        t0 = time.time()

        if is_debug(window):
            print(f"(Pep) Analyzing classpath... (Project: {project_path(window)})")

        analysis_config = "{:skip-lint true :output {:analysis {:var-usages false :var-definitions {:shallow true} :arglists true :keywords true :java-class-definitions false} :format :json :canonical-paths true}}"

        analysis_subprocess_args = [
            clj_kondo_path(window),
            "--config",
            analysis_config,
            "--parallel",
            "--lint",
            classpath,
        ]

        # Hide the console window on Windows.
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        analysis_completed_process = subprocess.run(
            analysis_subprocess_args,
            cwd=project_path(window),
            text=True,
            capture_output=True,
            startupinfo=startupinfo,
        )

        output = None

        try:
            output = json.loads(analysis_completed_process.stdout)
        except:
            output = {}

        analysis = output.get("analysis", {})

        keyword_index_ = keyword_index(analysis)

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

        set_classpath_analysis(
            project_path(window),
            {
                **java_class_index_,
                **keyword_index_,
                **namespace_index_,
                **var_index_,
            },
        )

        if is_debug(window):
            print(
                f"(Pep) Classpath analysis is completed (Project: {project_path(window)}) [{time.time() - t0:,.2f} seconds]"
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

        classpath = path_separator.join(paths)

        if is_debug(window):
            print(
                f"(Pep) Analyzing paths... (Project: {project_path(window)}, Paths {paths})"
            )

        analysis_config = "{:skip-lint true :output {:analysis {:var-definitions true :var-usages true :arglists true :keywords true :java-class-usages true :java-class-definitions false} :format :json :canonical-paths true} }"

        analysis_subprocess_args = [
            clj_kondo_path(window),
            "--config",
            analysis_config,
            "--parallel",
            "--lint",
            classpath,
        ]

        # Hide the console window on Windows.
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        analysis_completed_process = subprocess.run(
            analysis_subprocess_args,
            cwd=project_path(window),
            text=True,
            capture_output=True,
            startupinfo=startupinfo,
        )

        output = None

        try:
            output = json.loads(analysis_completed_process.stdout)
        except:
            output = {}

        analysis = output.get("analysis", {})

        # Keywords indexed by name - tuple of namespace and name.
        kindex = {}

        for keyword in analysis.get("keywords", []):
            ns = keyword.get("ns")
            name = keyword.get("name")
            row = keyword.get("row")

            kindex.setdefault((ns, name), []).append(keyword)

        keyword_index_ = keyword_index(analysis)

        namespace_index_ = namespace_index(
            analysis,
            nrn=False,
            nrn_usages=False,
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

        set_paths_analysis(
            project_path(window),
            {
                **keyword_index_,
                **namespace_index_,
                **var_index_,
                **java_class_index_,
                "findings": output.get("findings", []),
            },
        )

        if is_debug(window):
            print(
                f"(Pep) Paths analysis is completed (Project {project_path(window)}, Paths {paths}) [{time.time() - t0:,.2f} seconds]"
            )


def analyze_paths_async(window):
    threading.Thread(target=lambda: analyze_paths(window), daemon=True).start()


## ---


def erase_analysis_regions(view):
    view.erase_regions("pg_pep_analysis_error")
    view.erase_regions("pg_pep_analysis_warning")


# ---


def keyword_region(view, keyword_usage):
    """
    Returns the Region of a keyword_usage.
    """

    row_start = keyword_usage["row"]
    col_start = keyword_usage["col"]

    row_end = keyword_usage["end-row"]
    col_end = keyword_usage["end-col"]

    start_point = view.text_point(row_start - 1, col_start - 1)
    end_point = view.text_point(row_end - 1, col_end - 1)

    return sublime.Region(start_point, end_point)


def namespace_region(view, namespace):
    """
    Returns a Region of a namespace usage.
    """

    row_start = namespace.get("name-row")
    col_start = namespace.get("name-col")

    row_end = namespace.get("name-end-row")
    col_end = namespace.get("name-end-col")

    start_point = view.text_point(row_start - 1, col_start - 1)
    end_point = view.text_point(row_end - 1, col_end - 1)

    return sublime.Region(start_point, end_point)


def namespace_definition_region(view, namespace_definition):
    """
    Returns a Region of a namespace definition.
    """

    return namespace_region(view, namespace_definition)


def namespace_usage_region(view, namespace_usage):
    """
    Returns a Region of a namespace usage.
    """

    return namespace_region(view, namespace_usage)


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

    name_row_start = local_usage["name-row"]
    name_col_start = local_usage["name-col"]

    name_row_end = local_usage["name-end-row"]
    name_col_end = local_usage["name-end-col"]

    name_start_point = view.text_point(name_row_start - 1, name_col_start - 1)
    name_end_point = view.text_point(name_row_end - 1, name_col_end - 1)

    return sublime.Region(name_start_point, name_end_point)


def local_binding_region(view, local_binding):
    """
    Returns the Region of a local binding.
    """

    row_start = local_binding.get("name-row") or local_binding.get("row")
    col_start = local_binding.get("name-col") or local_binding.get("col")

    row_end = local_binding.get("name-end-row") or local_binding.get("end-row")
    col_end = local_binding.get("name-end-col") or local_binding.get("end-col")

    start_point = view.text_point(row_start - 1, col_start - 1)
    end_point = view.text_point(row_end - 1, col_end - 1)

    return sublime.Region(start_point, end_point)


def var_definition_region(view, var_definition):
    """
    Returns the Region of a Var definition.
    """

    name_row_start = var_definition["name-row"]
    name_col_start = var_definition["name-col"]

    name_row_end = var_definition["name-end-row"]
    name_col_end = var_definition["name-end-col"]

    name_start_point = view.text_point(name_row_start - 1, name_col_start - 1)
    name_end_point = view.text_point(name_row_end - 1, name_col_end - 1)

    return sublime.Region(name_start_point, name_end_point)


def var_usage_region(view, var_usage):
    """
    Returns the Region of a Var usage.
    """

    name_row_start = var_usage.get("name-row") or var_usage.get("row")
    name_col_start = var_usage.get("name-col") or var_usage.get("col")

    name_row_end = var_usage.get("name-end-row") or var_usage.get("end-row")
    name_col_end = var_usage.get("name-end-col") or var_usage.get("end-col")

    name_start_point = view.text_point(name_row_start - 1, name_col_start - 1)
    name_end_point = view.text_point(name_row_end - 1, name_col_end - 1)

    return sublime.Region(name_start_point, name_end_point)


def java_class_usage_region(view, java_class_usage):
    """
    Returns the Region of a Java class usage.
    """

    name_row_start = java_class_usage.get("row")
    name_col_start = java_class_usage.get("col")

    name_row_end = java_class_usage.get("end-row")
    name_col_end = java_class_usage.get("end-col")

    name_start_point = view.text_point(name_row_start - 1, name_col_start - 1)
    name_end_point = view.text_point(name_row_end - 1, name_col_end - 1)

    return sublime.Region(name_start_point, name_end_point)


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
    except:
        return None


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
    Mapping of thingy type to kind.
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

    # 1. Try keywords.
    thingy_region, thingy_data = keyword_in_region(
        view, analysis.get("krn", {}), region
    ) or (None, None)

    if thingy_data:
        return ("keyword", thingy_region, thingy_data)

    # 2. Try local usages.
    thingy_region, thingy_data = local_usage_in_region(
        view, analysis.get("lrn_usages", {}), region
    ) or (None, None)

    if thingy_data:
        return ("local_usage", thingy_region, thingy_data)

    # 3. Try Var usages.
    thingy_region, thingy_data = var_usage_in_region(
        view, analysis.get("vrn_usages", {}), region
    ) or (None, None)

    if thingy_data:
        return ("var_usage", thingy_region, thingy_data)

    # 4. Try local bindings.
    thingy_region, thingy_data = local_binding_in_region(
        view, analysis.get("lrn", {}), region
    ) or (None, None)

    if thingy_data:
        return ("local_binding", thingy_region, thingy_data)

    # 5. Try Var definitions.
    thingy_region, thingy_data = var_definition_in_region(
        view, analysis.get("vrn", {}), region
    ) or (None, None)

    if thingy_data:
        return ("var_definition", thingy_region, thingy_data)

    # 6. Try namespace usages.
    thingy_region, thingy_data = namespace_usage_in_region(
        view, analysis.get("nrn_usages", {}), region
    ) or (None, None)

    if thingy_data:
        return ("namespace_usage", thingy_region, thingy_data)

    # 7. Try namespace usages alias.
    thingy_region, thingy_data = namespace_usage_alias_in_region(
        view, analysis.get("nrn_usages", {}), region
    ) or (None, None)

    if thingy_data:
        return ("namespace_usage_alias", thingy_region, thingy_data)

    # 8. Try namespace definitions.
    thingy_region, thingy_data = namespace_definition_in_region(
        view, analysis.get("nrn", {}), region
    ) or (None, None)

    if thingy_data:
        return ("namespace_definition", thingy_region, thingy_data)

    # 9. Try Java class usages.
    thingy_region, thingy_data = java_class_usage_in_region(
        view, analysis_jrn_usages(analysis), region
    ) or (None, None)

    if thingy_data:
        return (TT_JAVA_CLASS_USAGE, thingy_region, thingy_data)


# ---


def find_keywords(analysis, keyword):
    keyword_qualified_name = (keyword.get("ns"), keyword.get("name"))

    return analysis.get("kindex", {}).get(keyword_qualified_name, [])


def find_keyword_usages(analysis, keyword):
    keywords = find_keywords(analysis, keyword)

    return [keyword for keyword in keywords if not keyword.get("reg")]


def find_local_binding(analysis, local_usage):
    return analysis_lindex(analysis).get(local_usage.get("id"))


def find_local_usages(analysis, local_binding_or_usage):
    return analysis.get("lindex_usages", {}).get(local_binding_or_usage.get("id"), [])


def find_var_definition(analysis, thingy_data):
    """
    Returns a var definition thingy data or None.
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


def find_var_usages(analysis, thingy_data):
    var_ns = thingy_data.get("ns") or thingy_data.get("to")

    var_name = thingy_data.get("name")

    return var_usages(analysis, (var_ns, var_name))


def find_java_class_definition(analysis, thingy_data):
    """
    Returns a Java class definition analysis or None.
    """
    return analysis_jindex(analysis).get(thingy_data.get("class"))


def find_java_class_usages(analysis, thingy_data):
    """
    Returns a list of Java class usage analysis.
    """
    return analysis_jindex_usages(analysis).get(thingy_data.get("class"), [])


def find_namespace_definition(analysis, thingy_data):
    """
    Returns a namespace definition thingy data or None.
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


def find_namespace_usages(analysis, namespace_definition):
    """
    Returns usages of namespace_definition.
    """

    name = namespace_definition.get("name")

    nindex_usages = analysis_nindex_usages(analysis)

    return [
        namespace_usage
        for namespace_usage in nindex_usages.get(name, [])
        if file_extension(namespace_usage.get("filename"))
        in thingy_file_extensions(namespace_definition)
    ]


def find_namespace_usages_with_usage(analysis, namespace_usage):
    """
    Returns usages of namespace_usage.
    """

    name = namespace_usage.get("to")

    return [
        usage
        for usage in analysis_nindex_usages(analysis).get(name, [])
        if file_extension(usage.get("filename"))
        in thingy_file_extensions(namespace_usage)
    ]


def find_namespace_vars_usages(analysis, namespace_usage):
    """
    Returns usages of Vars from namespace_usage.

    It's useful when you want to see Vars (from namespace_usage) being used in your namespace.
    """

    usages = []

    for var_qualified_name, var_usages in analysis.get("vindex_usages", {}).items():
        namespace, _ = var_qualified_name

        if namespace == namespace_usage.get("to"):
            usages.extend(var_usages)

    return usages


def find_keyword_definition(analysis, keyword):
    """
    Returns a keyword which has "definition semantics":
    - Clojure Spec
    - re-frame
    """
    k = (keyword.get("ns"), keyword.get("name"))

    for keyword_indexed in analysis_kindex(analysis).get(k, []):
        if keyword_indexed.get("reg", None):
            return keyword_indexed


# ---


def highlight_regions(view, selection, regions):
    if regions:
        view.add_regions(
            HIGHLIGHTED_REGIONS_KEY,
            regions,
            scope="region.cyanish",
            icon="dot" if setting(view.window(), "highlight_gutter", None) else "",
            flags=sublime.DRAW_NO_FILL
            if setting(view.window(), "highlight_region", None)
            else sublime.HIDDEN,
        )


def highlight_thingy(view):
    """
    Highlight regions of thingy under cursor.
    """
    analysis = view_analysis(view.id())

    region = thingy_sel_region(view)

    thingy = thingy_in_region(view, analysis, region)

    view.erase_regions(HIGHLIGHTED_REGIONS_KEY)

    status_message = ""

    # We can't highlight if view was modified,
    # because regions might be different.
    if thingy and not staled_analysis(view):
        if regions := find_thingy_regions(view, analysis, thingy):

            window = view.window()

            if not setting(window, "highlight_self", None):
                regions = [
                    region_ for region_ in regions if not region_.contains(region)
                ]

            highlight_regions(view, view.sel(), regions)

            if view_status_show_highlighted(window):
                prefix = view_status_show_highlighted_prefix(window)

                suffix = view_status_show_highlighted_suffix(window)

                status_message = f"{prefix}{len(regions)}{suffix}"

    view.set_status(HIGHLIGHTED_STATUS_KEY, status_message)


def find_thingy_regions(view, analysis, thingy):
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

        var_usages = find_namespace_vars_usages(analysis, thingy_data)

        for var_usage in var_usages:
            if region := var_usage_namespace_region(view, var_usage):
                regions.append(region)

    elif thingy_type == TT_NAMESPACE_USAGE_ALIAS:
        regions.append(namespace_usage_alias_region(view, thingy_data))

        var_usages = find_namespace_vars_usages(analysis, thingy_data)

        for var_usage in var_usages:
            if region := var_usage_namespace_region(view, var_usage):
                regions.append(region)

    return regions


# ---


class GotoScopeInputHandler(sublime_plugin.ListInputHandler):
    def __init__(self, scopes):
        self.scopes = scopes

    def name(self):
        return "scope"

    def list_items(self):
        return [(scope.capitalize(), scope) for scope in self.scopes]

    def placeholder(self):
        return "Scope"


class PgPepClearCacheCommand(sublime_plugin.WindowCommand):
    def run(self):
        clear_cache()

        if is_debug(self.window):
            print(f"(Pep) Cleared cache")


class PgPepEraseAnalysisRegionsCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        erase_analysis_regions(self.view)


class PgPepAnalyzeClasspathCommand(sublime_plugin.WindowCommand):
    def run(self):
        analyze_classpath_async(self.window)


class PgPepAnalyzePathsCommand(sublime_plugin.WindowCommand):
    def run(self):
        analyze_paths_async(self.window)


class PgPepAnalyzeViewCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        analyze_view_async(self.view, on_completed=view_analysis_completed(self.view))


class PgPepGotoAnythingCommand(sublime_plugin.WindowCommand):
    """
    Goto anything in scope.

    Scope is one of: 'view', 'paths' or 'classpath'.
    """

    def input(self, args):
        if "scope" not in args:
            return GotoScopeInputHandler(scopes={"view", "paths", "classpath"})

    def run(self, scope):
        project_path_ = project_path(self.window)

        active_view = self.window.active_view()

        # Goto is a window command, so it's possible
        # that there isn't an active view.
        # In that case, an empty analysis dict is used.

        view_analysis_ = view_analysis(active_view.id()) if active_view else {}

        paths_analysis_ = paths_analysis(project_path_)

        classpath_analysis_ = classpath_analysis(project_path_)

        analysis_ = {}

        if scope == "view":
            analysis_ = view_analysis_
        elif scope == "paths":
            analysis_ = paths_analysis_
        elif scope == "classpath":
            analysis_ = classpath_analysis_

        items_ = [
            *namespace_goto_items(analysis_),
            *var_goto_items(analysis_),
            *keyword_goto_items(analysis_),
        ]

        show_goto_thingy_quick_panel(self.window, items_)


class PgPepOutlineCommand(sublime_plugin.TextCommand):
    """
    Outline thingies in view.
    """

    def run(self, edit):
        view_analysis_ = view_analysis(self.view.id())

        items_ = [
            *namespace_goto_items(view_analysis_),
            *var_goto_items(view_analysis_, namespace_visible=False),
            *keyword_goto_items(view_analysis_),
        ]

        show_goto_thingy_quick_panel(self.view.window(), items_)


class PgPepGotoNamespaceCommand(sublime_plugin.WindowCommand):
    """
    Goto namespace in scope.

    Scope is either 'classpath' or 'paths'.
    """

    def input(self, args):
        if "scope" not in args:
            return GotoScopeInputHandler(scopes={"paths", "classpath"})

    def run(self, scope):
        project_path_ = project_path(self.window)


        analysis_ = {}

        if scope == "paths":
            analysis_ = paths_analysis(project_path_)
        elif scope == "classpath":
            analysis_ = classpath_analysis(project_path_)

        items_ = namespace_goto_items(analysis_)

        # Sort by namespace name.
        items_ = sorted(items_, key=lambda d: d["thingy_data"]["name"])

        show_goto_thingy_quick_panel(self.window, items_)


class PgPepGotoVarCommand(sublime_plugin.WindowCommand):
    """
    Goto var in scope.

    Scope is either 'classpath' or 'paths'.
    """

    def input(self, args):
        if "scope" not in args:
            return GotoScopeInputHandler(scopes={"view", "paths", "classpath"})

    def run(self, scope):
        project_path_ = project_path(self.window)

        analysis_ = {}

        if scope == "view":
            analysis_ = view_analysis(self.window.active_view().id())
        elif scope == "paths":
            analysis_ = paths_analysis(project_path_)
        elif scope == "classpath":
            analysis_ = classpath_analysis(project_path_)

        items_ = var_goto_items(analysis_)

        show_goto_thingy_quick_panel(self.window, items_)


class PgPepGotoKeywordCommand(sublime_plugin.WindowCommand):
    """
    Goto keyword in scope.
    """

    def input(self, args):
        if "scope" not in args:
            return GotoScopeInputHandler(scopes={"view", "paths", "classpath"})

    def run(self, scope="paths"):
        project_path_ = project_path(self.window)

        analysis_ = {}

        if scope == "view":
            analysis_ = view_analysis(self.window.active_view().id())
        elif scope == "paths":
            analysis_ = paths_analysis(project_path_)
        elif scope == "classpath":
            analysis_ = classpath_analysis(project_path_)

        items_ = keyword_goto_items(analysis_)

        show_goto_thingy_quick_panel(self.window, items_)


class PgPepGotoSpecCommand(sublime_plugin.WindowCommand):
    """
    Goto keyword defined by Clojure Spec in scope.
    """

    def input(self, args):
        if "scope" not in args:
            return GotoScopeInputHandler(scopes={"view", "paths", "classpath"})

    def run(self, scope="paths"):
        project_path_ = project_path(self.window)

        analysis_ = {}

        if scope == "view":
            analysis_ = view_analysis(self.window.active_view().id())
        elif scope == "paths":
            analysis_ = paths_analysis(project_path_)
        elif scope == "classpath":
            analysis_ = classpath_analysis(project_path_)

        items_ = keyword_goto_items(analysis_)

        items_ = [
            item_
            for item_ in items_
            if item_["thingy_data"]["reg"] == "clojure.spec.alpha/def"
        ]

        show_goto_thingy_quick_panel(self.window, items_)


def thingy_name(thingy):
    thingy_type, _, thingy_data = thingy

    thingy_namespace = thingy_data.get("ns") or thingy_data.get("to")

    thingy_name = thingy_data.get("name")

    thingy_qualified_name = (
        f"{thingy_namespace}/{thingy_name}" if thingy_namespace else thingy_name
    )

    # Prefix ':' to a Keyword Thingy.
    if thingy_type == TT_KEYWORD:
        thingy_qualified_name = ":" + thingy_qualified_name

    return thingy_qualified_name


class PgPepCopyNameCommand(sublime_plugin.TextCommand):
    """
    Copy a Thingy's name to the clipboard.
    """

    def run(self, edit):
        view_analysis_ = view_analysis(self.view.id())

        region = thingy_sel_region(self.view)

        if thingy := thingy_in_region(self.view, view_analysis_, region):
            sublime.set_clipboard(thingy_name(thingy))

            self.view.window().status_message("Copied")


class PgPepShowNameCommand(sublime_plugin.TextCommand):
    """
    Show a Thingy's name in a popup.
    """

    def run(self, edit):
        view_analysis_ = view_analysis(self.view.id())

        region = thingy_sel_region(self.view)

        if thingy := thingy_in_region(self.view, view_analysis_, region):
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

        region = self.view.sel()[0]

        thingy = thingy_in_region(self.view, view_analysis_, region)

        thingy_type, _, thingy_data = thingy or (None, None, None)

        definition = None

        project_path_ = project_path(self.view.window())

        paths_analysis_ = paths_analysis(project_path_)

        classpath_analysis_ = classpath_analysis(project_path_)

        if thingy_type == TT_VAR_DEFINITION or thingy_type == TT_VAR_USAGE:
            # Try to find Var definition in view first,
            # only if not found try paths and project analysis.
            definition = (
                find_var_definition(view_analysis_, thingy_data)
                or find_var_definition(paths_analysis_, thingy_data)
                or find_var_definition(classpath_analysis_, thingy_data)
            )

        elif (
            thingy_type == TT_NAMESPACE_DEFINITION
            or thingy_type == TT_NAMESPACE_USAGE
            or thingy_type == TT_NAMESPACE_USAGE_ALIAS
        ):
            definition = (
                find_namespace_definition(view_analysis_, thingy_data)
                or find_namespace_definition(paths_analysis_, thingy_data)
                or find_namespace_definition(classpath_analysis_, thingy_data)
            )

        if definition:
            # Name
            # ---

            name = definition.get("name", "")
            name = inspect.cleandoc(html.escape(name))

            ns = definition.get("ns", "")
            ns = inspect.cleandoc(html.escape(ns))

            filename = definition.get("filename")

            qualified_name = f"{ns}/{name}" if ns else name

            goto_command_url = sublime.command_url(
                "pg_pep_goto",
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
                    arglists_minihtml += f"<code>{htmlify(arglist)}</code>"

                arglists_minihtml += """</p>"""

            # Doc
            # ---

            doc = definition.get("doc")

            doc_minihtml = ""

            if doc:
                doc = re.sub(r"\s", "&nbsp;", htmlify(doc))

                doc_minihtml = f"""<p class="doc">{doc}</p>"""

            content = f"""
            <body id='pg-pep-show-doc'>

                {name_minihtml}

                {arglists_minihtml}

                {doc_minihtml}
                
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
                    qualified_name,
                    content,
                    sublime.SEMI_TRANSIENT,
                )

                self.view.window().focus_sheet(sheet)

            elif show == "status_bar":
                name = definition.get("name", "")

                ns = definition.get("ns", "")

                qualified_name = f"{ns}/{name}" if ns else name

                self.view.set_status(
                    STATUS_BAR_DOC_KEY, f"{qualified_name} {' '.join(arglists)}"
                )

        else:

            # Status bar documentation must be cleared when a definition is not found.

            if show == "status_bar":
                self.view.set_status(STATUS_BAR_DOC_KEY, "")


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

            # Navigation is a dictionary with keys:
            # - thingy_id
            # - thingy_findings
            navigation = view_navigation(state)

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

                if thingy_findings := find_namespace_vars_usages(state, thingy_data):

                    # ID is the namespace name.
                    thingy_id = thingy_data.get("to")

                    self.initialize_navigation(state, thingy_id, thingy_findings)

                    # Jump to first var usage.
                    self.jump(state, movement, -1)


class PgPepShowThingy(sublime_plugin.TextCommand):
    def run(self, edit):
        region = self.view.sel()[0]

        analysis = view_analysis(self.view.id())

        thingy = thingy_in_region(self.view, analysis, region)

        if thingy is None:
            return

        thingy_type, _, thingy_data = thingy

        items_html = ""

        for k, v in thingy_data.items():
            items_html += f"<li>{htmlify(str(k))}: {htmlify(str(v))}</li>"

        html = f"""
        <body id='pg-pep-show-thingy'>
            <style>
                h1 {{
                    font-size: 1.1rem;
                    font-weight: 500;
                    font-family: system;
                }}
            </style>

            <h1>{thingy_type}</h1>

            <ul>
                {items_html}
            </ul>

        </body>
        """

        flags = (
            sublime.SEMI_TRANSIENT | sublime.ADD_TO_SELECTION | sublime.CLEAR_TO_RIGHT
        )

        sheet = self.view.window().new_html_sheet(thingy_type, html, flags)

        self.view.window().focus_sheet(sheet)


class PgPepGotoCommand(sublime_plugin.WindowCommand):
    def run(self, location=None, side_by_side=False):
        if location:
            flags = GOTO_SIDE_BY_SIDE_FLAGS if side_by_side else GOTO_DEFAULT_FLAGS

            goto(self.window, location, flags)

        else:
            print("(Pep) Can't goto without a location")


class PgPepGotoDefinitionCommand(sublime_plugin.TextCommand):
    """
    Command to goto definition of a var, namespace, and keyword.

    In case of a keyword, it works for re-frame handlers and Clojure Spec.
    """

    def run(self, edit, side_by_side=False):

        window = self.view.window()

        view = self.view

        analysis = view_analysis(view.id())

        region = thingy_sel_region(view)

        if thingy := thingy_in_region(view, analysis, region):

            thingy_type, _, thingy_data = thingy

            definition = None

            if thingy_type == TT_LOCAL_USAGE:
                definition = find_local_binding(analysis, thingy_data)

            elif (
                thingy_type == TT_NAMESPACE_USAGE
                or thingy_type == TT_NAMESPACE_USAGE_ALIAS
            ):
                project_path_ = project_path(window)

                paths_analysis_ = paths_analysis(project_path_)

                classpath_analysis_ = classpath_analysis(project_path_)

                definition = (
                    find_namespace_definition(analysis, thingy_data)
                    or find_namespace_definition(paths_analysis_, thingy_data)
                    or find_namespace_definition(classpath_analysis_, thingy_data)
                )

            elif thingy_type == TT_VAR_USAGE:
                namespace_ = thingy_data.get("to", None)
                name_ = thingy_data.get("name", None)

                project_path_ = project_path(window)

                paths_analysis_ = paths_analysis(project_path_)

                classpath_analysis_ = classpath_analysis(project_path_)

                definition = (
                    find_var_definition(analysis, thingy_data)
                    or find_var_definition(paths_analysis_, thingy_data)
                    or find_var_definition(classpath_analysis_, thingy_data)
                )

            # TODO
            # elif thingy_type == TT_JAVA_CLASS_USAGE:
            #     project_path_ = project_path(window)

            #     paths_analysis_ = paths_analysis(project_path_)

            #     classpath_analysis_ = classpath_analysis(project_path_)

            #     definition = (
            #         find_java_class_definition(analysis, thingy_data)
            #         or find_java_class_definition(paths_analysis_, thingy_data)
            #         or find_java_class_definition(classpath_analysis_, thingy_data)
            #     )

            elif thingy_type == TT_KEYWORD:
                keyword_namespace = thingy_data.get("ns", None)
                keyword_name = thingy_data.get("name", None)

                project_path_ = project_path(window)

                paths_analysis_ = paths_analysis(project_path_)

                definition = find_keyword_definition(
                    analysis, thingy_data
                ) or find_keyword_definition(paths_analysis_, thingy_data)

            if definition:
                flags = GOTO_SIDE_BY_SIDE_FLAGS if side_by_side else GOTO_DEFAULT_FLAGS

                goto(window, thingy_location(definition), flags)

            else:
                print("(Pep) Unable to find definition")


class PgPepGotoAnalysisFindingCommand(sublime_plugin.WindowCommand):
    def input(self, args):
        if "scope" not in args:
            return GotoScopeInputHandler(scopes={"view", "paths"})

    def run(self, scope):
        try:

            project_path_ = project_path(self.window)

            active_view = self.window.active_view()

            # Goto is a window command, so it's possible
            # that there isn't an active view.
            # In that case, an empty analysis dict is used.

            view_analysis_ = view_analysis(active_view.id()) if active_view else {}

            paths_analysis_ = paths_analysis(project_path_)

            findings = analysis_findings(
                view_analysis_ if scope == "view" else paths_analysis_
            )

            items = []

            for finding in findings:

                item_kind = (
                    (sublime.KindId.COLOR_REDISH, "e", "e")
                    if finding["level"] == "error"
                    else (sublime.KindId.COLOR_ORANGISH, "w", "w")
                )

                items.append(
                    {
                        "thingy_type": TT_FINDING,
                        "thingy_data": finding,
                        "quick_panel_item": sublime.QuickPanelItem(
                            finding["message"],
                            details=finding["filename"],
                            kind=item_kind,
                            annotation=finding["type"],
                        ),
                    }
                )

            show_goto_thingy_quick_panel(
                self.window,
                items,
                goto_on_highlight=True,
            )

        except Exception as e:
            print(f"(Pep) Goto Analysis Finding failed.", traceback.format_exc())


class PgPepTraceUsages(sublime_plugin.TextCommand):
    """
    Command to trace usages of a var or namespace.
    """

    def input(self, args):
        if "scope" not in args:
            return GotoScopeInputHandler(scopes={"view", "paths"})

    def run(self, edit, scope):
        view_analysis_ = view_analysis(self.view.id())

        region = thingy_sel_region(self.view)

        if thingy := thingy_in_region(self.view, view_analysis_, region):
            thingy_type, thingy_region, thingy_data = thingy

            analysis_ = {}

            if scope == "view":
                analysis_ = view_analysis_
            elif scope == "paths":
                project_path_ = project_path(self.view.window())

                analysis_ = paths_analysis(project_path_)

            thingy_usages = None

            # Find usages, in paths analysis, from var definition or usage:
            if thingy_type == TT_VAR_DEFINITION or thingy_type == TT_VAR_USAGE:
                thingy_usages = find_var_usages(analysis_, thingy_data)

            def trace_var_usages(thingy_usage):
                from_ = thingy_usage.get("from")

                from_var_ = thingy_usage.get("from-var")

                from_usages = var_usages(analysis_, (from_, from_var_))

                return {
                    "thingy_data": thingy_usage,
                    "thingy_traces": [
                        trace_var_usages(from_usage)
                        for from_usage in from_usages
                        if not recursive_usage(from_usage)
                    ],
                }

            def tree_branches(trace):
                thingy_data = trace.get("thingy_data", {})

                from_namespace = thingy_data.get("from")

                from_var = thingy_data.get("from-var")
                from_var = "/" + from_var if from_var else ""

                goto_location = thingy_location(thingy_data)

                goto_command_url = sublime.command_url("pg_pep_goto", {"location": goto_location})

                goto_text = f"{from_namespace}{from_var}:{goto_location['line']}:{goto_location['column']}"

                s = f"<li><a href='{goto_command_url}'>{goto_text}</a></li>"

                thingy_traces = trace["thingy_traces"]

                if thingy_traces:
                    s += "<ul>"

                for trace in thingy_traces:
                    s += tree_branches(trace)

                if thingy_traces:
                    s += "</ul>"

                return s

            def tree(trace):
                thingy_data = trace.get("thingy_data", {})

                name = thingy_data.get("name")
                namespace = thingy_data.get("ns") or thingy_data.get("from")

                thingy_traces = trace["thingy_traces"]

                s = f"<b>{namespace}/{name} (Usages: {len(thingy_traces)})</b>"

                if thingy_traces:
                    s += "<ul>"

                for trace in thingy_traces:
                    s += tree_branches(trace)

                if thingy_traces:
                    s += "</ul>"

                return s

            if thingy_usages:
                trace = {
                    "thingy_data": thingy_data,
                    "thingy_traces": [
                        trace_var_usages(thingy_usage)
                        for thingy_usage in thingy_usages
                        if not recursive_usage(thingy_usage)
                    ],
                }


                sheet = self.view.window().new_html_sheet(
                    "Trace Usages",
                    tree(trace),
                    sublime.NewFileFlags.SEMI_TRANSIENT,
                )

                self.view.window().focus_sheet(sheet)


class PgPepFindUsagesCommand(sublime_plugin.TextCommand):
    def input(self, args):
        if "scope" not in args:
            return GotoScopeInputHandler(scopes={"view", "paths"})

    def run(self, edit, scope):
        view_analysis_ = view_analysis(self.view.id())

        viewport_position = self.view.viewport_position()

        region = self.view.sel()[0]

        if thingy := thingy_in_region(self.view, view_analysis_, region):

            thingy_type, thingy_region, thingy_data = thingy

            thingy_usages = None

            analysis_ = {}

            if scope == "view":
                analysis_ = view_analysis_
            elif scope == "paths":
                project_path_ = project_path(self.view.window())

                analysis_ = paths_analysis(project_path_)

            if thingy_type == TT_KEYWORD:
                # To be considered:
                # If the keyword is a destructuring key,
                # should it show its local usages?

                thingy_usages = find_keyword_usages(analysis_, thingy_data)

            elif thingy_type == TT_LOCAL_BINDING:
                thingy_usages = find_local_usages(analysis_, thingy_data)

            elif thingy_type == TT_LOCAL_USAGE:
                thingy_usages = find_local_usages(analysis_, thingy_data)

            elif thingy_type == TT_VAR_DEFINITION:
                thingy_usages = find_var_usages(analysis_, thingy_data)

            elif thingy_type == TT_VAR_USAGE:
                thingy_usages = find_var_usages(analysis_, thingy_data)

            elif thingy_type == TT_JAVA_CLASS_USAGE:
                thingy_usages = find_java_class_usages(analysis_, thingy_data)

            elif thingy_type == TT_NAMESPACE_DEFINITION:
                thingy_usages = find_namespace_usages(analysis_, thingy_data)

            elif (
                thingy_type == TT_NAMESPACE_USAGE
                or thingy_type == TT_NAMESPACE_USAGE_ALIAS
            ):

                # Usages of a namespace, in the scope of a single view, shows usages of vars instead of namespace.
                # I think it's safe to assume that this behavior is expected for view usages.

                if scope == "view":
                    thingy_usages = find_namespace_vars_usages(
                        analysis_,
                        thingy_data,
                    )
                else:
                    thingy_usages = find_namespace_usages_with_usage(
                        analysis_,
                        thingy_data,
                    )

            # Prune None usages - it's strange that there are None items though.
            thingy_usages = [usage for usage in thingy_usages if usage]

            if thingy_usages:

                if len(thingy_usages) == 1:
                    location = thingy_location(thingy_usages[0])

                    goto(self.view.window(), location)

                else:
                    quick_panel_items = []

                    selected_index = 0

                    for index, thingy_usage in enumerate(thingy_usages):
                        trigger = (
                            thingy_usage.get("from")
                            or thingy_usage.get("ns")
                            or os.path.basename(thingy_usage.get("filename"))
                        )

                        trigger = f'{trigger} {thingy_usage.get("row", "-")}:{thingy_usage.get("col", "-")}'

                        # It's a nice experience to open the panel
                        # with the thingy under the cursor as the selected index.
                        if thingy_usage == thingy_data:
                            selected_index = index

                        quick_panel_items.append(sublime.QuickPanelItem(trigger))

                    def on_done(index, _):
                        if index == -1:
                            # Restore selection and viewport position:

                            self.view.sel().clear()

                            self.view.sel().add(region)

                            self.view.window().focus_view(self.view)

                            self.view.set_viewport_position(viewport_position, True)

                        else:
                            location = thingy_location(thingy_usages[index])

                            goto(self.view.window(), location)

                    def on_highlighted(index):
                        location = thingy_location(thingy_usages[index])

                        goto(
                            self.view.window(),
                            location,
                            flags=sublime.ENCODED_POSITION | sublime.TRANSIENT,
                        )

                    placeholder = None

                    if (
                        thingy_type == TT_NAMESPACE_USAGE
                        or thingy_type == TT_NAMESPACE_USAGE_ALIAS
                    ):
                        placeholder = f"{thingy_data.get('to')} is used {len(thingy_usages)} times"
                    else:
                        sym = thingy_data.get("name") or thingy_data.get("class")

                        placeholder = f"{sym} is used {len(thingy_usages)} times"

                    self.view.window().show_quick_panel(
                        quick_panel_items,
                        on_done,
                        sublime.WANT_EVENT,
                        selected_index,
                        on_highlighted,
                        placeholder,
                    )


class PgPepSelectCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        view_analysis_ = view_analysis(self.view.id())

        region = self.view.sel()[0]

        thingy = thingy_in_region(self.view, view_analysis_, region)

        if thingy:
            regions = find_thingy_regions(self.view, view_analysis_, thingy)

            self.view.sel().clear()
            self.view.sel().add_all(regions)


class PgPepRenameCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        view_analysis_ = view_analysis(self.view.id())

        region = thingy_sel_region(self.view)

        thingy = thingy_in_region(self.view, view_analysis_, region)

        if thingy:
            thingy_text = self.view.substr(region)

            def rename(name):
                for region in find_thingy_regions(self.view, view_analysis_, thingy):
                    self.view.replace(edit, region, name)

            self.view.window().show_input_panel("Rename:", thingy_text, on_done=rename)


class PgPepHighlightCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        highlight_thingy(self.view)


class PgPepClearHighlightedCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        self.view.erase_regions(HIGHLIGHTED_REGIONS_KEY)
        self.view.set_status(HIGHLIGHTED_STATUS_KEY, "")


class PgPepToggleHighlightCommand(sublime_plugin.TextCommand):
    def __init__(self, view):
        self.view = view
        self.is_toggled = (
            True if self.view.get_regions(HIGHLIGHTED_REGIONS_KEY) else False
        )

    def run(self, edit):
        self.view.run_command(
            "pg_pep_clear_highlighted" if self.is_toggled else "pg_pep_highlight"
        )

        self.is_toggled = not self.is_toggled


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

            if status_message:
                status_message = "⚠ " + status_message

            # Show the number of errors and/or warnings.
            # (Setting the value to the empty string will clear the status.)
            self.view.set_status("pg_pep_view_summary", status_message)

        except Exception as e:
            print(f"(Pep) View summary status failed.", traceback.format_exc())


class PgPepViewNamespaceStatusCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        try:

            analysis = view_analysis(self.view.id())

            view_namespace = ""

            if view_status_show_namespace(self.view.window()):
                # It's possible to get the namespace wrong since it's a list of definitions,
                # but it's unlikely because of the scope (view) of the analysis.
                if namespaces := list(analysis_nindex(analysis).keys()):
                    namespace_prefix = (
                        view_status_show_namespace_prefix(self.view.window()) or ""
                    )

                    namespace_suffix = (
                        view_status_show_namespace_suffix(self.view.window()) or ""
                    )

                    view_namespace = namespace_prefix + namespaces[0] + namespace_suffix

            self.view.set_status("pg_pep_view_namespace", view_namespace)

        except Exception as e:
            print(f"(Pep) Show view namespace status failed.", traceback.format_exc())


class PgPepAnnotateCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        try:

            def finding_region(finding):
                line_start = finding["row"] - 1
                line_end = (finding.get("end-row") or finding.get("row")) - 1
                col_start = finding["col"] - 1
                col_end = (finding.get("end-col") or finding.get("col")) - 1

                pa = self.view.text_point(line_start, col_start)
                pb = self.view.text_point(line_end, col_end)

                return sublime.Region(pa, pb)

            def finding_minihtml(finding):
                return f"""
                <body>
                <div">
                    <span style="font-size:{annotation_font_size(self.view.window())}">{htmlify(finding["message"])}</span></div>
                </div>
                </body>
                """

            analysis = view_analysis(self.view.id())

            findings = analysis_findings(analysis)

            warning_region_set = []
            warning_minihtml_set = []

            error_region_set = []
            error_minihtml_set = []

            for finding in findings:
                try:

                    if finding["level"] == "error":
                        error_region_set.append(finding_region(finding))
                        error_minihtml_set.append(finding_minihtml(finding))
                    elif finding["level"] == "warning":
                        warning_region_set.append(finding_region(finding))
                        warning_minihtml_set.append(finding_minihtml(finding))

                except Exception as ex:
                    if is_debug(self.view.window()):
                        print(
                            "(Pep) Failed to annotate finding.",
                            {"error": ex, "finding": finding},
                        )

            # Erase regions from previous analysis.
            erase_analysis_regions(self.view)

            redish = self.view.style_for_scope("region.redish")["foreground"]
            orangish = self.view.style_for_scope("region.orangish")["foreground"]

            self.view.add_regions(
                "pg_pep_analysis_error",
                error_region_set,
                scope="region.redish",
                annotations=error_minihtml_set,
                annotation_color=redish,
                flags=(
                    sublime.DRAW_SQUIGGLY_UNDERLINE
                    | sublime.DRAW_NO_FILL
                    | sublime.DRAW_NO_OUTLINE
                ),
            )

            self.view.add_regions(
                "pg_pep_analysis_warning",
                warning_region_set,
                scope="region.orangish",
                annotations=warning_minihtml_set,
                annotation_color=orangish,
                flags=(
                    sublime.DRAW_SQUIGGLY_UNDERLINE
                    | sublime.DRAW_NO_FILL
                    | sublime.DRAW_NO_OUTLINE
                ),
            )

        except Exception as e:
            print(f"(Pep) Annotate failed.", traceback.format_exc())


class PgPepViewListener(sublime_plugin.ViewEventListener):
    """
    These 'actions' are configured via settings.

    You might want to disable running analyzes on load & save for instance.

    See Pep.sublime-settings.
    """

    @classmethod
    def is_applicable(_, settings):
        return settings.get("syntax") in {
            "Packages/Tutkain/EDN (Tutkain).sublime-syntax",
            "Packages/Tutkain/Clojure (Tutkain).sublime-syntax",
            "Packages/Tutkain/ClojureScript (Tutkain).sublime-syntax",
            "Packages/Tutkain/Clojure Common (Tutkain).sublime-syntax",
            "Packages/Clojure/Clojure.sublime-syntax",
            "Packages/Clojure/ClojureScript.sublime-syntax",
        }

    def __init__(self, view):
        self.view = view
        self.modified_time = None

    def on_activated_async(self):
        analyze = True

        if self.view.is_scratch():
            analyze = analyze_scratch_view(self.view.window())

        if analyze:
            analyze_view_async(
                self.view,
                on_completed=view_analysis_completed(self.view),
            )

    def on_modified_async(self):
        """
        The time of modification is recorded so it's possible
        to check how long ago the last change happened.

        It's very import for the view analysis. See `on_selection_modified_async`.
        """
        self.modified_time = time.time()

    def on_post_save_async(self):
        if setting(self.view.window(), "analyze_paths_on_post_save", False):
            analyze_paths_async(self.view.window())

    def on_selection_modified_async(self):
        """
        When the selection is modified, two actions might be triggered:
        - A region is highlighted;
        - Active view is analyzed.

        The view is analyzed (async) when its analysis data is staled
        and it passes a threshold (in seconds) of the last time the view was modified.
        """
        if automatically_highlight(self.view.window()):
            highlight_thingy(self.view)

        if self.modified_time:
            # Don't analyze when the programmer is editing the view.
            # (When last modification timestamp is less then threshold.)
            if staled_analysis(self.view) and (time.time() - self.modified_time) > 0.2:
                analyze = True

                if self.view.is_scratch():
                    analyze = analyze_scratch_view(self.view.window())

                if analyze:
                    analyze_view_async(
                        self.view,
                        on_completed=view_analysis_completed(self.view),
                    )

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
                print(f"(Pep) Clear project cache (Project: {project_path_})")

            set_paths_analysis(project_path_, {})
            set_classpath_analysis(project_path_, {})


# ---


def plugin_loaded():
    if window := sublime.active_window():
        if setting(window, "analyze_paths_on_plugin_loaded", False):
            analyze_paths_async(window)

        if setting(window, "analyze_classpath_on_plugin_loaded", False):
            analyze_classpath_async(window)
