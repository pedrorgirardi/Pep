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

from urllib.parse import urlparse
from zipfile import ZipFile
from collections import defaultdict

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

TT_KEYWORD = "keyword"
TT_LOCAL_BINDING = "local_binding"
TT_LOCAL_USAGE = "local_usage"
TT_VAR_DEFINITION = "var_definition"
TT_VAR_USAGE = "var_usage"
TT_NAMESPACE_DEFINITION = "namespace_definition"
TT_NAMESPACE_USAGE = "namespace_usage"
TT_NAMESPACE_USAGE_ALIAS = "namespace_usage_alias"

OUTPUT_PANEL_NAME = "pep"
OUTPUT_PANEL_NAME_PREFIXED = f"output.{OUTPUT_PANEL_NAME}"


_view_analysis_ = {}

_paths_analysis_ = {}

_classpath_analysis_ = {}


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

                if namespace_usage.get("alias"):
                    alias_row = namespace_usage.get("alias-row")

                    nrn_usages_.setdefault(alias_row, []).append(namespace_usage)

    return {
        "nindex": nindex_,
        "nindex_usages": nindex_usages_,
        "nrn": nrn_,
        "nrn_usages": nrn_usages_,
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
    if thingy_data and (file := thingy_data.get("filename")):
        return {
            "resource": urlparse(file),
            "line": thingy_data.get("name-row") or thingy_data.get("row"),
            "column": thingy_data.get("name-col") or thingy_data.get("col"),
        }


def with_jar(filename, f):
    """
    Open JAR `filename` and call `f` with filename and a file-like object (ZipExtFile).

    Filename passed to `f` is a temporary file and it will be removed afterwards.
    """

    filename_split = filename.split(":")
    filename_jar = filename_split[0]
    filename_file = filename_split[1]

    with ZipFile(filename_jar) as jar:
        with jar.open(filename_file) as jar_file:

            file_extension = pathlib.Path(filename_file).suffix

            descriptor, tempath = tempfile.mkstemp(file_extension)

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
        resource = location["resource"]
        line = location["line"]
        column = location["column"]

        if ".jar:" in resource.path:

            def open_file(filename, file):
                view = window.open_file(f"{filename}:{line}:{column}", flags=flags)
                view.set_scratch(True)
                view.set_read_only(True)

            with_jar(resource.path, open_file)

        else:
            return window.open_file(f"{resource.path}:{line}:{column}", flags=flags)


def goto_definition(window, definition, side_by_side=False):
    flags = GOTO_SIDE_BY_SIDE_FLAGS if side_by_side else GOTO_DEFAULT_FLAGS

    goto(window, thingy_location(definition), flags=flags)


def namespace_quick_panel_item(thingy_data):
    namespace_name = thingy_data.get("name", thingy_data.get("to", ""))
    namespace_filename = thingy_data.get("filename", "")

    return sublime.QuickPanelItem(
        namespace_name,
        kind=(sublime.KIND_ID_NAMESPACE, "n", ""),
        annotation=pathlib.Path(namespace_filename).suffix.replace(".", ""),
    )


def var_quick_panel_item(thingy_data):
    var_namespace = thingy_data.get("ns", thingy_data.get("to", ""))
    var_name = thingy_data.get("name", "")
    var_arglist = thingy_data.get("arglist-strs", [])
    var_filename = thingy_data.get("filename", "")

    trigger = f"{var_namespace}/{var_name}"

    if var_arglist:
        return sublime.QuickPanelItem(
            trigger,
            kind=sublime.KIND_FUNCTION,
            details=" ".join(var_arglist),
            annotation=pathlib.Path(var_filename).suffix.replace(".", ""),
        )
    else:
        return sublime.QuickPanelItem(
            trigger,
            kind=sublime.KIND_VARIABLE,
            annotation=pathlib.Path(var_filename).suffix.replace(".", ""),
        )


def thingy_quick_panel_item(thingy_type, thingy_data):
    if (
        thingy_type == TT_NAMESPACE_DEFINITION
        or thingy_type == TT_NAMESPACE_USAGE
        or thingy_type == TT_NAMESPACE_USAGE_ALIAS
    ):
        return namespace_quick_panel_item(thingy_data)

    elif thingy_type == TT_VAR_DEFINITION or thingy_type == TT_VAR_USAGE:
        return var_quick_panel_item(thingy_data)


def var_goto_items(analysis):
    items_ = []

    for var_definition in var_definitions(analysis):
        var_namespace = var_definition.get("ns", "")
        var_name = var_definition.get("name", "")
        var_arglist = var_definition.get("arglist-strs", [])
        var_filename = var_definition.get("filename", "")

        trigger = f"{var_namespace}/{var_name}"

        items_.append(
            {
                "thingy_type": TT_VAR_DEFINITION,
                "thingy_data": var_definition,
                "quick_panel_item": var_quick_panel_item(var_definition),
            }
        )

    return items_


def keyword_goto_items(analysis):
    items_ = []

    for keywords_ in analysis_kindex(analysis).values():
        for keyword_ in keywords_:
            if reg := keyword_.get("reg", None):
                keyword_namespace = keyword_.get("ns", "")
                keyword_name = keyword_.get("name", "")
                keyword_filename = keyword_.get("filename", "")

                trigger = ":" + (
                    f"{keyword_namespace}/{keyword_name}"
                    if keyword_namespace
                    else keyword_name
                )

                items_.append(
                    {
                        "thingy_type": TT_KEYWORD,
                        "thingy_data": keyword_,
                        "quick_panel_item": sublime.QuickPanelItem(
                            trigger,
                            kind=sublime.KIND_KEYWORD,
                            details=reg,
                            annotation=pathlib.Path(keyword_filename).suffix.replace(
                                ".", ""
                            ),
                        ),
                    }
                )

    return items_


def namespace_goto_items(analysis):
    items_ = []

    for namespace_definition in namespace_definitions(analysis):

        namespace_name = namespace_definition.get("name", "")
        namespace_filename = namespace_definition.get("filename", "")

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

                with_jar(thingy_filename, read_jar_source)

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


def show_goto_thingy_quick_panel(window, items):
    def on_done(index):
        if index != -1:
            thingy_data_ = items[index]["thingy_data"]

            location = thingy_location(thingy_data_)

            goto(window, location)

    quick_panel_items = [item_["quick_panel_item"] for item_ in items]

    window.show_quick_panel(
        quick_panel_items,
        on_done,
    )


## ---


def settings():
    return sublime.load_settings("Pep.sublime-settings")


def debug():
    return settings().get("debug", False)


def automatically_highlight():
    return settings().get("automatically_highlight", False)


def annotate_view_analysis():
    return settings().get("annotate_view_analysis", False)


def set_view_name(view, name):
    if view:
        if view.is_loading():
            sublime.set_timeout(lambda: set_view_name(view, name), 100)
        else:
            view.set_name(name)


def view_text(view):
    return view.substr(sublime.Region(0, view.size()))


def clj_kondo_path():
    # Bundled:
    # os.path.join(sublime.packages_path(), "Pep", "bin", "clj-kondo")
    #
    # TODO: Setting to configure clj-kondo path.

    return "clj-kondo"


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

        classpath_completed_process = subprocess.run(
            classpath, cwd=project_path(window), text=True, capture_output=True
        )

        classpath_completed_process.check_returncode()

        return classpath_completed_process.stdout


## ---


def analyze_view(view, on_completed=None):
    is_debug = settings().get("debug", False)

    window = view.window()

    view_file_name = view.file_name()

    # Change count right before analyzing the view.
    # This will be stored in the analysis.
    view_change_count = view.change_count()

    project_file_name = window.project_file_name() if window else None

    # Setting the working directory is important because of clj-kondo's cache.
    cwd = None

    if project_file_name:
        cwd = os.path.dirname(project_file_name)
    elif view_file_name:
        cwd = os.path.dirname(view_file_name)

    analysis_config = "{:output {:analysis {:arglists true :locals true :keywords true} :format :json :canonical-paths true} \
                        :lint-as {reagent.core/with-let clojure.core/let}}"

    # --lint <file>: a file can either be a normal file, directory or classpath.
    # In the case of a directory or classpath, only .clj, .cljs and .cljc will be processed.
    # Use - as filename for reading from stdin.

    # --filename <file>: in case stdin is used for linting, use this to set the reported filename.

    analysis_subprocess_args = [
        clj_kondo_path(),
        "--config",
        analysis_config,
        "--lint",
        "-",
        "--filename",
        view_file_name or "-",
    ]

    if is_debug:
        print("(Pep) clj-kondo\n", pprint.pformat(analysis_subprocess_args))

    analysis_completed_process = subprocess.run(
        analysis_subprocess_args,
        cwd=cwd,
        text=True,
        capture_output=True,
        input=view_text(view),
    )

    output = None

    try:
        output = json.loads(analysis_completed_process.stdout)
    except:
        output = {}

    analysis = output.get("analysis", {})

    if is_debug:
        pprint.pp(analysis)

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

    view_analysis_ = {
        "view_change_count": view_change_count,
        "findings": output.get("findings", {}),
        "summary": output.get("summary", {}),
        "kindex": kindex,
        "krn": krn,
        "lindex": lindex,
        "lindex_usages": lindex_usages,
        "lrn": lrn,
        "lrn_usages": lrn_usages,
    }

    namespace_index_ = namespace_index(analysis)

    var_index_ = var_index(analysis)

    set_view_analysis(
        view.id(),
        {
            **namespace_index_,
            **var_index_,
            **view_analysis_,
        },
    )

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

    is_debug = settings().get("debug", False)

    if classpath := project_classpath(window):
        print(f"(Pep) Analyzing classpath... (Project: {project_path(window)})")

        analysis_config = (
            "{:output {:analysis {:arglists true} :format :json :canonical-paths true}}"
        )

        analysis_subprocess_args = [
            clj_kondo_path(),
            "--config",
            analysis_config,
            "--parallel",
            "--lint",
            classpath,
        ]

        if is_debug:
            print("(Pep) clj-kondo\n", pprint.pformat(analysis_subprocess_args))

        analysis_completed_process = subprocess.run(
            analysis_subprocess_args,
            cwd=project_path(window),
            text=True,
            capture_output=True,
        )

        output = None

        try:
            output = json.loads(analysis_completed_process.stdout)
        except:
            output = {}

        analysis = output.get("analysis", {})

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

        set_classpath_analysis(
            project_path(window),
            {
                **namespace_index_,
                **var_index_,
            },
        )

        print(
            f"(Pep) Classpath analysis is completed (Project: {project_path(window)})"
        )


def analyze_classpath_async(window):
    threading.Thread(target=lambda: analyze_classpath(window), daemon=True).start()


def analyze_paths(window):
    """
    Analyze paths to create indexes for var and namespace definitions, and keywords.
    """

    is_debug = settings().get("debug", False)

    if paths := project_data_paths(window):
        classpath = ":".join(paths)

        print(
            f"(Pep) Analyzing paths... (Project {project_path(window)}, Paths {paths})"
        )

        analysis_config = "{:output {:analysis {:arglists true :keywords true} :format :json :canonical-paths true}}"

        analysis_subprocess_args = [
            clj_kondo_path(),
            "--config",
            analysis_config,
            "--parallel",
            "--lint",
            classpath,
        ]

        if is_debug:
            print("(Pep) clj-kondo\n", pprint.pformat(analysis_subprocess_args))

        analysis_completed_process = subprocess.run(
            analysis_subprocess_args,
            cwd=project_path(window),
            text=True,
            capture_output=True,
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

        paths_analysis = {
            "kindex": kindex,
        }

        set_paths_analysis(
            project_path(window),
            {
                **paths_analysis,
                **namespace_index_,
                **var_index_,
            },
        )

        print(
            f"(Pep) Paths analysis is completed (Project {project_path(window)}, Paths {classpath})"
        )


def analyze_paths_async(window):
    threading.Thread(target=lambda: analyze_paths(window), daemon=True).start()


## ---


def clj_kondo_finding_message(finding):
    def group1(regex):
        matches = re.compile(regex).findall(finding["message"])

        return matches[0] if matches is not None else finding["message"]

    t = finding["type"]

    minihtml = ""

    if t == "unresolved-symbol":
        minihtml = "Unresolved: " + group1(r"^Unresolved symbol:\s+(?P<symbol>.*)")

    elif t == "unresolved-namespace":
        minihtml = "Unresolved: " + group1(r"^Unresolved namespace\s+([^\s]*)")

    elif t == "unused-binding":
        minihtml = "Unused: " + group1(r"^unused binding\s+(?P<symbol>.*)")

    elif t == "unused-namespace":
        minihtml = "Unused: " + group1(r"^namespace ([^\s]*)")

    elif t == "unused-referred-var":
        minihtml = "Unused: " + group1(r"^([^\s]*)")

    elif t == "missing-map-value":
        minihtml = finding["message"].capitalize()

    elif t == "refer-all":
        minihtml = finding["message"].capitalize()

    elif t == "duplicate-require":
        minihtml = "Duplicated require: " + group1(r"^duplicate require of ([^\s]*)")

    elif t == "cond-else":
        minihtml = "Use :else instead"

    elif t == "unreachable-code":
        minihtml = "Unreachable"

    elif t == "redundant-do":
        minihtml = "Redundant do"

    elif t == "redefined-var":
        minihtml = "Redefined: " + group1(r"^redefined var ([^\s]*)")

    else:
        minihtml = finding["message"]

    return minihtml


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
            "pg_pep_highligths",
            regions,
            scope="region.cyanish",
            flags=sublime.DRAW_NO_FILL,
        )


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
    def on_analyze_completed(self, analysis):
        summary = analysis.get("summary")

        errors = summary.get("error")

        warnings = summary.get("warning")

        sublime.status_message(f"Warnings: {warnings}, Errors: {errors}")

    def run(self, edit):
        analyze_view_async(self.view, on_completed=self.on_analyze_completed)


class PgPepGotoInViewCommand(sublime_plugin.TextCommand):
    """
    Goto thingy in view.
    """

    def run(self, edit):
        view_analysis_ = view_analysis(self.view.id())

        items_ = [
            *namespace_goto_items(view_analysis_),
            *var_goto_items(view_analysis_),
            *keyword_goto_items(view_analysis_),
        ]

        show_goto_thingy_quick_panel(self.view.window(), items_)


class PgPepGotoInPathsCommand(sublime_plugin.WindowCommand):
    """
    Goto thingy in paths.
    """

    def run(self):
        project_path_ = project_path(self.window)

        paths_analysis_ = paths_analysis(project_path_)

        items_ = [
            *namespace_goto_items(paths_analysis_),
            *var_goto_items(paths_analysis_),
            *keyword_goto_items(paths_analysis_),
        ]

        show_goto_thingy_quick_panel(self.window, items_)


class PgPepGotoInClasspathCommand(sublime_plugin.WindowCommand):
    """
    Goto thingy in classpath.
    """

    def run(self):
        project_path_ = project_path(self.window)

        classpath_analysis_ = classpath_analysis(project_path_)

        items_ = [
            *namespace_goto_items(classpath_analysis_),
            *var_goto_items(classpath_analysis_),
        ]

        show_goto_thingy_quick_panel(self.window, items_)


class PgPepGotoNamespaceCommand(sublime_plugin.WindowCommand):
    """
    Goto namespace in paths.
    """

    def run(self):
        project_path_ = project_path(self.window)

        paths_analysis_ = paths_analysis(project_path_)

        items_ = namespace_goto_items(paths_analysis_)

        # Sort by namespace name.
        items_ = sorted(items_, key=lambda d: d["thingy_data"]["name"])

        show_goto_thingy_quick_panel(self.window, items_)


class PgPepGotoVarCommand(sublime_plugin.WindowCommand):
    """
    Goto var in paths.
    """

    def run(self):
        project_path_ = project_path(self.window)

        paths_analysis_ = paths_analysis(project_path_)

        items_ = var_goto_items(paths_analysis_)

        show_goto_thingy_quick_panel(self.window, items_)


class PgPepGotoKeywordCommand(sublime_plugin.WindowCommand):
    """
    Goto keyword in paths.
    """

    def run(self):
        project_path_ = project_path(self.window)

        paths_analysis_ = paths_analysis(project_path_)

        items_ = keyword_goto_items(paths_analysis_)

        show_goto_thingy_quick_panel(self.window, items_)


class PgPepGotoSpecCommand(sublime_plugin.WindowCommand):
    """
    Goto keyword defined by Clojure Spec in paths.
    """

    def run(self):
        project_path_ = project_path(self.window)

        paths_analysis_ = paths_analysis(project_path_)

        items_ = keyword_goto_items(paths_analysis_)
        items_ = [
            item_
            for item_ in items_
            if item_["thingy_data"]["reg"] == "clojure.spec.alpha/def"
        ]

        show_goto_thingy_quick_panel(self.window, items_)


class PgPepShowDocCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        is_debug = debug()

        view_analysis_ = view_analysis(self.view.id())

        region = self.view.sel()[0]

        thingy = thingy_in_region(self.view, view_analysis_, region)

        if is_debug:
            print("(Pep) Thingy", thingy)

        if thingy is None:
            return

        thingy_type, _, thingy_data = thingy

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
            if is_debug:
                print("(Pep) Definition:\n", pprint.pformat(definition))

            # Name
            # ---

            name = definition.get("name", "")
            name = inspect.cleandoc(html.escape(name))

            ns = definition.get("ns", "")
            ns = inspect.cleandoc(html.escape(ns))

            filename = definition.get("filename")

            link = f"{ns}/{name}" if ns else name

            name_minihtml = f"""
            <p class="name">
                <a href="{filename}">{link}</a>
            </p>
            """

            # Arglists
            # ---

            arglists = definition.get("arglist-strs")

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

            location = thingy_location(definition)

            self.view.show_popup(
                content,
                location=-1,
                max_width=500,
                on_navigate=lambda href: goto(self.view.window(), location),
            )


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

                        {TT_NAMESPACE_USAGE, TT_NAMESPACE_USAGE_ALIAS}

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

        flags = sublime.COOPERATE_WITH_AUTO_COMPLETE | sublime.HIDE_ON_MOUSE_MOVE_AWAY

        self.view.show_popup(html, flags, -1, 500)


class PgPepGotoDefinitionCommand(sublime_plugin.TextCommand):
    def run(self, edit, side_by_side=False):
        is_debug = debug()

        analysis = view_analysis(self.view.id())

        region = self.view.sel()[0]

        thingy = thingy_in_region(self.view, analysis, region)

        if is_debug:
            print("(Pep) Thingy", thingy)

        if thingy is None:
            return

        thingy_type, _, thingy_data = thingy

        if thingy_type == TT_LOCAL_USAGE:
            if definition := find_local_binding(analysis, thingy_data):
                goto_definition(self.view.window(), definition, side_by_side)

        elif (
            thingy_type == TT_NAMESPACE_USAGE or thingy_type == TT_NAMESPACE_USAGE_ALIAS
        ):
            project_path_ = project_path(self.view.window())

            paths_analysis_ = paths_analysis(project_path_)

            classpath_analysis_ = classpath_analysis(project_path_)

            definition = (
                find_namespace_definition(analysis, thingy_data)
                or find_namespace_definition(paths_analysis_, thingy_data)
                or find_namespace_definition(classpath_analysis_, thingy_data)
            )

            if definition:
                goto_definition(self.view.window(), definition, side_by_side)

        elif thingy_type == TT_VAR_USAGE:
            namespace_ = thingy_data.get("to", None)
            name_ = thingy_data.get("name", None)

            print("(Pep) Goto var definition:", f"{namespace_}/{name_}")

            project_path_ = project_path(self.view.window())

            paths_analysis_ = paths_analysis(project_path_)

            classpath_analysis_ = classpath_analysis(project_path_)

            definition = (
                find_var_definition(analysis, thingy_data)
                or find_var_definition(paths_analysis_, thingy_data)
                or find_var_definition(classpath_analysis_, thingy_data)
            )

            if definition:
                goto_definition(self.view.window(), definition, side_by_side)

        elif thingy_type == TT_KEYWORD:
            keyword_namespace = thingy_data.get("ns", None)
            keyword_name = thingy_data.get("name", None)

            print(
                "(Pep) Goto keyword definition:",
                f"{keyword_namespace}/{keyword_name}"
                if keyword_namespace
                else keyword_name,
            )

            project_path_ = project_path(self.view.window())

            paths_analysis_ = paths_analysis(project_path_)

            definition = find_keyword_definition(
                analysis, thingy_data
            ) or find_keyword_definition(paths_analysis_, thingy_data)

            if definition:
                goto_definition(self.view.window(), definition, side_by_side)


class PgPepFindUsagesCommand(sublime_plugin.TextCommand):
    def run(self, edit, scope="view"):

        view_analysis_ = view_analysis(self.view.id())

        viewport_position = self.view.viewport_position()

        region = self.view.sel()[0]

        if thingy := thingy_in_region(self.view, view_analysis_, region):

            thingy_type, thingy_region, thingy_data = thingy

            project_path_ = project_path(self.view.window())

            paths_analysis_ = paths_analysis(project_path_)

            thingy_usages = None

            analysis_ = view_analysis_ if scope == "view" else paths_analysis_

            if thingy_type == TT_KEYWORD:
                # To be considered:
                # If the keyword is a destructuring key,
                # should it show its local usages?

                thingy_usages = find_keyword_usages(analysis_, thingy_data)

            elif thingy_type == TT_VAR_DEFINITION:
                thingy_usages = find_var_usages(analysis_, thingy_data)

            elif thingy_type == TT_VAR_USAGE:
                thingy_usages = find_var_usages(analysis_, thingy_data)

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

            if thingy_usages:

                if len(thingy_usages) == 1:
                    location = thingy_location(thingy_usages[0])

                    goto(self.view.window(), location)

                else:
                    quick_panel_items = []

                    for thingy_usage in thingy_usages:
                        trigger = thingy_usage.get("from") or os.path.basename(
                            thingy_usage.get("filename")
                        )
                        details = thingy_usage.get("filename", "")
                        annotation = f'Line {thingy_usage.get("row", "Row")}, Column {thingy_usage.get("col", "Col")}'

                        quick_panel_items.append(
                            sublime.QuickPanelItem(
                                trigger,
                                details,
                                annotation,
                                thingy_kind(thingy_type, thingy_data),
                            )
                        )

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
                        placeholder = f"{thingy_data.get('name')} is used {len(thingy_usages)} times"

                    self.view.window().show_quick_panel(
                        quick_panel_items,
                        on_done,
                        sublime.WANT_EVENT,
                        0,
                        on_highlighted,
                        placeholder,
                    )


class PgPepSelectCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        is_debug = debug()

        view_analysis_ = view_analysis(self.view.id())

        region = self.view.sel()[0]

        thingy = thingy_in_region(self.view, view_analysis_, region)

        if is_debug:
            print("(Pep) Thingy", thingy)

        if thingy:
            regions = find_thingy_regions(self.view, view_analysis_, thingy)

            self.view.sel().clear()
            self.view.sel().add_all(regions)


class PgPepHighlightCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        analysis = view_analysis(self.view.id())

        region = self.view.sel()[0]

        thingy = thingy_in_region(self.view, analysis, region)

        self.view.erase_regions("pg_pep_highligths")

        # We can't highlight if view was modified,
        # because regions might be different.
        if thingy and not staled_analysis(self.view):
            regions = find_thingy_regions(self.view, analysis, thingy)

            if regions:
                highlight_regions(self.view, self.view.sel(), regions)


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
                    <span>{htmlify(clj_kondo_finding_message(finding))}</span></div>
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
                if finding["level"] == "error":
                    error_region_set.append(finding_region(finding))
                    error_minihtml_set.append(finding_minihtml(finding))
                elif finding["level"] == "warning":
                    warning_region_set.append(finding_region(finding))
                    warning_minihtml_set.append(finding_minihtml(finding))

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

            summary_errors = analysis_summary(analysis).get("error", 0)
            summary_warnings = analysis_summary(analysis).get("warning", 0)

            status_messages = []
            status_messages.append(f"Errors: {summary_errors}")
            status_messages.append(f"Warnings: {summary_warnings}")

            sublime.status_message(", ".join(status_messages))

        except Exception as e:
            print(f"(Pep) Annotate failed.", traceback.format_exc())


class PgPepReportCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        try:

            def finding_str(finding):
                message = clj_kondo_finding_message(finding)

                return f'{finding["level"].capitalize()}: {message}\n[{finding["row"]}.{finding["col"]}:{finding["end-col"]}]'

            analysis = view_analysis(self.view.id())

            findings = analysis_findings(analysis)

            warning_str_set = []

            error_str_set = []

            for finding in findings:
                if finding["level"] == "error":
                    error_str_set.append(finding_str(finding))
                elif finding["level"] == "warning":
                    warning_str_set.append(finding_str(finding))

            descriptor, path = tempfile.mkstemp()

            try:
                with os.fdopen(descriptor, "w") as file:
                    s = (
                        f"File: {self.view.file_name()}\n\n"
                        if self.view.file_name() is not None
                        else ""
                    )
                    s += "\n\n".join(error_str_set + warning_str_set)

                    file.write(s)

                v = self.view.window().open_file(
                    path, flags=sublime.ADD_TO_SELECTION | sublime.SEMI_TRANSIENT
                )
                v.set_scratch(True)
                v.set_read_only(True)
                v.settings().set("word_wrap", "auto")
                v.settings().set("gutter", False)
                v.settings().set("line_numbers", False)
                v.settings().set("result_file_regex", r"^File: (\S+)")
                v.settings().set("result_line_regex", r"^\[(\d+).(\d+):(\d+)\]")

                # Trick to set the name of the view.
                set_view_name(v, "Analysis")
            finally:
                os.remove(path)

        except Exception as e:
            print(f"(Pep) Report failed.", traceback.format_exc())


# ---


class PgPepViewListener(sublime_plugin.ViewEventListener):
    """
    These 'actions' are configured via settings.

    You might want to disable running analyzes on load & save for instance.

    See Pep.sublime-settings.
    """

    @classmethod
    def is_applicable(_, settings):
        return settings.get("syntax") in {
            "Packages/Tutkain/Clojure (Tutkain).sublime-syntax",
            "Packages/Tutkain/ClojureScript (Tutkain).sublime-syntax",
            "Packages/Tutkain/Clojure Common (Tutkain).sublime-syntax",
            "Packages/Clojure/Clojure.sublime-syntax",
            "Packages/Clojure/ClojureScript.sublime-syntax",
        }

    def __init__(self, view):
        self.view = view
        self.modified_time = None

    def view_analysis_completed(self, analysis):
        if annotate_view_analysis():
            self.view.run_command("pg_pep_annotate")

    def on_activated_async(self):
        analyze_view_async(self.view, on_completed=self.view_analysis_completed)

    def on_modified_async(self):
        """
        The time of modification is recorded so it's possible
        to check how long ago the last change happened.

        It's very import for the view analysis. See `on_selection_modified_async`.
        """
        self.modified_time = time.time()

    def on_post_save_async(self):
        if settings().get("analyze_paths_on_post_save", False):
            analyze_paths_async(self.view.window())

    def on_selection_modified_async(self):
        """
        When the selection is modified, two actions might be triggered:
        - A region is highlighted;
        - Active view is analyzed.

        The view is analyzed (async) when its analysis data is staled
        and it passes a threshold (in seconds) of the last time the view was modified.
        """
        if automatically_highlight():
            sublime.set_timeout(lambda: self.view.run_command("pg_pep_highlight"), 0)

        if self.modified_time:
            # Don't analyze when the programmer is editing the view.
            # (When last modification timestamp is less then threshold.)
            if staled_analysis(self.view) and (time.time() - self.modified_time) > 0.2:
                analyze_view_async(self.view, on_completed=self.view_analysis_completed)

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
        if settings().get("analyze_paths_on_load_project", False):
            analyze_paths_async(window)

        if settings().get("analyze_classpath_on_load_project", False):
            analyze_classpath_async(window)

    def on_pre_close_project(self, window):
        project_path_ = project_path(window)

        print(f"(Pep) Clear project cache (Project: {project_path_})")

        set_paths_analysis(project_path_, {})
        set_classpath_analysis(project_path_, {})


# ---


def plugin_loaded():
    print("(Pep) Plugin loaded")

    if window := sublime.active_window():
        if settings().get("analyze_paths_on_plugin_loaded", False):
            analyze_paths_async(window)

        if settings().get("analyze_classpath_on_plugin_loaded", False):
            analyze_classpath_async(window)
