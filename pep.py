import html
import inspect
import subprocess
import os
import re
import tempfile
import json
import traceback
import itertools
import pprint
import threading

from urllib.parse import urlparse
from zipfile import ZipFile

import sublime_plugin
import sublime


GOTO_DEFAULT_FLAGS = sublime.ENCODED_POSITION

GOTO_USAGE_FLAGS = sublime.ENCODED_POSITION | sublime.SEMI_TRANSIENT | sublime.ADD_TO_SELECTION | sublime.REPLACE_MRU

GOTO_SIDE_BY_SIDE_FLAGS = sublime.ENCODED_POSITION | sublime.SEMI_TRANSIENT | sublime.ADD_TO_SELECTION | sublime.CLEAR_TO_RIGHT


_view_analysis_ = {}

_paths_analysis_ = {}

_project_analysis_ = {}


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


def set_project_analysis(project_path, analysis):
    """
    Updates analysis for project.
    """
    global _project_analysis_
    _project_analysis_[project_path] = analysis


def project_analysis(project_path):
    """
    Returns analysis for project.
    """
    global _project_analysis_
    return _project_analysis_.get(project_path, {})


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


def analysis_findings(analysis):
    return analysis.get("findings", {})


def analysis_summary(analysis):
    return analysis.get("summary", {})


def analysis_vindex(analysis):
    """
    Returns a dictionary of locals by ID.

    This index can be used to find a local in constant time if you know its ID.

    When finding usages from a usage itself, the first step is to find the usage,
    once you have found it, you can use its ID to find the local.

    Locals and usages have the same ID, 
    so it's possible to corretale a usage with a local.

    'lindex' stands for 'local index'.
    """
    return analysis.get("vindex", {})


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


# ---


def view_navigation(view_state):
    return view_state.get("navigation", {})


def set_view_navigation(view_state, navigation):
    view_state["navigation"] = navigation


def project_path(window):
    return window.extract_variables().get("project_path")

def classpath_project_data(window):
    """
    Example:

    ["clojure", "-Spath"]
    """
    return window.project_data().get("pep", {}).get("classpath")


def paths_project_data(window):
    """
    Example:

    ["src", "test"]
    """
    return window.project_data().get("pep", {}).get("paths")


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


def parse_location(thingy_data):
    """
    Thingy (data) is one of: Var definition, Var usage, local binding, or local usage.
    """
    if thingy_data and (file := thingy_data.get("filename")):
        return {
            "resource": urlparse(file),
            "line": thingy_data.get("name-row") or thingy_data.get("row"),
            "column": thingy_data.get("name-col") or thingy_data.get("col"),
        }


def goto(window, location, flags=sublime.ENCODED_POSITION):
    if location:
        resource = location["resource"]
        line = location["line"]
        column = location["column"]

        if ".jar:" in resource.path:
            parts = resource.path.split(":")
            jar_url = urlparse(parts[0])
            # If the path after the : starts with a forward slash, strip it. ZipFile can't
            # find the file inside the archive otherwise.
            path = parts[1][1:] if parts[1].startswith("/") else parts[1]
            archive = ZipFile(jar_url.path, "r")
            source_file = archive.read(path)
            descriptor, path = tempfile.mkstemp()

            try:
                with os.fdopen(descriptor, "w") as file:
                    file.write(source_file.decode())
                
                view = window.open_file(f"{path}:{line}:{column}", flags=flags)
                view.assign_syntax("Clojure (Tutkain).sublime-syntax")
                view.set_scratch(True)
                view.set_read_only(True)

                set_view_name(view, resource.path)

                return view
            finally:
                os.remove(path)

        else:
            return window.open_file(f"{resource.path}:{line}:{column}", flags=flags)


## ---

def settings():
    return sublime.load_settings("Pep.sublime-settings")

def debug():
    return sublime.load_settings("Pep.sublime-settings").get("debug", False)

def set_view_name(view, name):
    if view:
        if view.is_loading():
            sublime.set_timeout(lambda: set_view_name(view, name), 100)
        else:
            view.set_name(name)


def view_text(view):
    return view.substr(sublime.Region(0, view.size()))


def clj_kondo_path():
    return os.path.join(sublime.packages_path(), "Pep", "bin", "clj-kondo")


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
    if project_path(window):
        classpath_subprocess_args = classpath_project_data(window)

        if classpath_subprocess_args:
            classpath_completed_process = subprocess.run(
                classpath_subprocess_args, 
                cwd=project_path(window), 
                text=True, 
                capture_output=True
            )

            classpath_completed_process.check_returncode()

            return classpath_completed_process.stdout


## ---


def analyze_view(view):
    is_debug = settings().get("debug", False)

    window = view.window()

    view_file_name = view.file_name()

    project_file_name = window.project_file_name() if window else None

    # Setting the working directory is important because of the clj-kondo cache.
    cwd = None

    if project_file_name:
        cwd = os.path.dirname(project_file_name)
    elif view_file_name:
        cwd = os.path.dirname(view_file_name)

    analysis_config = "{:output {:analysis {:arglists true :locals true} :format :json :canonical-paths true} \
                        :lint-as {reagent.core/with-let clojure.core/let}}"

    analysis_subprocess_args = [clj_kondo_path(), 
                                "--config", analysis_config,
                                "--lint", view_file_name or "-"]

    if is_debug:
        print("(Pep) clj-kondo\n", pprint.pformat(analysis_subprocess_args))

    analysis_completed_process = subprocess.run(analysis_subprocess_args, cwd=cwd, text=True, capture_output=True)

    output = None

    try:
        output = json.loads(analysis_completed_process.stdout)
    except:
        output = {}

    analysis = output.get("analysis", {})

    # Vars indexed by row.
    vrn = {}

    # Vars indexed by name - tuple of namespace and name.
    vindex = {}

    for var_definition in analysis.get("var-definitions", []):
        ns = var_definition.get("ns")
        name = var_definition.get("name")
        name_row = var_definition.get("name-row")

        vrn.setdefault(name_row, []).append(var_definition)

        vindex[(ns, name)] = var_definition

    # Var usages indexed by row.
    vrn_usages = {}

    # Var usages indexed by name - var name to a set of var usages.
    vindex_usages = {}

    for var_usage in analysis.get("var-usages", []):
        ns = var_usage.get("to")
        name = var_usage.get("name")
        name_row = var_usage.get("name-row")

        vindex_usages.setdefault((ns, name), []).append(var_usage)

        vrn_usages.setdefault(name_row, []).append(var_usage)

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

    
    set_view_analysis(view.id(), { "findings": output.get("findings", {}),
                                   "summary": output.get("summary", {}),
                                   "vindex": vindex,
                                   "vindex_usages": vindex_usages,
                                   "vrn": vrn,
                                   "vrn_usages": vrn_usages,
                                   "lindex": lindex,
                                   "lindex_usages": lindex_usages,
                                   "lrn": lrn,
                                   "lrn_usages": lrn_usages })


def analyze_view_async(view):
    threading.Thread(target=lambda: analyze_view(view), daemon=True).start()


def analyze_classpath(window):
    is_debug = settings().get("debug", False)

    print(f"(Pep) Analyzing classpath... (Project: {project_path(window)})")

    sublime.status_message("Analyzing classpath... (This might take a moment)")

    classpath = project_classpath(window)

    if classpath:
        analysis_config = "{:output {:analysis {:arglists true} :format :json :canonical-paths true}}"

        analysis_subprocess_args = [clj_kondo_path(), 
                                    "--config", analysis_config,
                                    "--parallel", 
                                    "--lint", classpath]

        if is_debug:
            print("(Pep) clj-kondo\n", pprint.pformat(analysis_subprocess_args))

        analysis_completed_process = subprocess.run(analysis_subprocess_args, cwd=project_path(window), text=True, capture_output=True)

        output = None

        try:
            output = json.loads(analysis_completed_process.stdout)
        except:
            output = {}

        analysis = output.get("analysis", {})

        var_definitions = analysis.get("var-definitions", [])

        var_usages = analysis.get("var-usages", [])

        # Var definitions indexed by (namespace, name) tuple.
        vindex = {}

        for var_definition in var_definitions:
            ns = var_definition.get("ns")
            name = var_definition.get("name")

            vindex[(ns, name)] = var_definition


        # Var usages indexed by name - var name to a set of var usages.
        vindex_usages = {}

        for var_usage in var_usages:
            ns = var_usage.get("to")
            name = var_usage.get("name")
            name_row = var_usage.get("name-row")

            vindex_usages.setdefault((ns, name), []).append(var_usage)

        analysis = {"vindex": vindex,
                    "vindex_usages": vindex_usages}

        set_project_analysis(project_path(window), analysis)

        print(f"(Pep) Classpath analysis is completed (Project: {project_path(window)})")


def analyze_classpath_async(window):
    threading.Thread(target=lambda: analyze_classpath(window), daemon=True).start()


def analyze_paths(window):
    is_debug = settings().get("debug", False)

    if (paths := paths_project_data(window)):
        classpath = ":".join(paths)

        print(f"(Pep) Analyzing paths... (Project {project_path(window)}, Paths {paths})")

        analysis_config = "{:output {:analysis {:arglists true} :format :json :canonical-paths true}}"

        analysis_subprocess_args = [clj_kondo_path(), 
                                    "--config", analysis_config,
                                    "--parallel", 
                                    "--lint", classpath]

        if is_debug:
            print("(Pep) clj-kondo\n", pprint.pformat(analysis_subprocess_args))

        analysis_completed_process = subprocess.run(analysis_subprocess_args, cwd=project_path(window), text=True, capture_output=True)

        output = None

        try:
            output = json.loads(analysis_completed_process.stdout)
        except:
            output = {}

        analysis = output.get("analysis", {})

        var_definitions = analysis.get("var-definitions", [])

        var_usages = analysis.get("var-usages", [])

        # Var definitions indexed by (namespace, name) tuple.
        vindex = {}

        for var_definition in var_definitions:
            ns = var_definition.get("ns")
            name = var_definition.get("name")

            vindex[(ns, name)] = var_definition


        # Var usages indexed by name - var name to a set of var usages.
        vindex_usages = {}

        for var_usage in var_usages:
            ns = var_usage.get("to")
            name = var_usage.get("name")
            name_row = var_usage.get("name-row")

            vindex_usages.setdefault((ns, name), []).append(var_usage)

        analysis = {"vindex": vindex,
                    "vindex_usages": vindex_usages}

        set_paths_analysis(project_path(window), analysis)

        print(f"(Pep) Paths analysis is completed (Project {project_path(window)}, Paths {classpath})")


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


def erase_usage_regions(view):
    view.erase_regions("pg_pep_find_local_binding")
    view.erase_regions("pg_pep_find_local_usage")


# ---


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

    name_row_start = var_usage["name-row"]
    name_col_start = var_usage["name-col"]

    name_row_end = var_usage["name-end-row"]
    name_col_end = var_usage["name-end-col"]

    name_start_point = view.text_point(name_row_start - 1, name_col_start - 1)
    name_end_point = view.text_point(name_row_end - 1, name_col_end - 1)

    return sublime.Region(name_start_point, name_end_point)


# ---


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


def thingy_in_region(view, state, region):
    """
    Thingy is not a good name, but what to call something that
    can be a local binding, local usage, Var definition, or Var usage?

    It's difficult to find a good name for it.

    A thingy is a triple:
        - Type:
            - local binding
            - local usage
            - Var definition
            - Var usage

        - Region for the symbol

        - The thingy itself - clj-kondo data.
    """

    # 1. Try local usages.
    thingy_region, thingy_data = local_usage_in_region(view, state.get("lrn_usages", {}), region) or (None, None)

    if thingy_data:
        return ("local_usage", thingy_region, thingy_data)

    # 2. Try Var usages. 
    thingy_region, thingy_data = var_usage_in_region(view, state.get("vrn_usages", {}), region) or (None, None)

    if thingy_data:
        return ("var_usage", thingy_region, thingy_data)

    # 3. Try local bindings. 
    thingy_region, thingy_data = local_binding_in_region(view, state.get("lrn", {}), region) or (None, None)

    if thingy_data:
        return ("local_binding", thingy_region, thingy_data)

    # 4. Try Var definitions. 
    thingy_region, thingy_data = var_definition_in_region(view, state.get("vrn", {}), region) or (None, None)

    if thingy_data:
        return ("var_definition", thingy_region, thingy_data)


# ---

def find_local_binding(analysis, local_usage):
    return analysis_lindex(analysis).get(local_usage.get("id"))


def find_local_usages(analysis, local_binding_or_usage):
    return analysis.get("lindex_usages", {}).get(local_binding_or_usage.get("id"), [])


def find_var_definition(analysis, var_usage):
    var_qualified_name = (var_usage.get("to"), var_usage.get("name"))

    return analysis_vindex(analysis).get(var_qualified_name)


def find_var_usages(analysis, var_definition):
    var_qualified_name = (var_definition.get("ns"), var_definition.get("name"))

    return analysis.get("vindex_usages", {}).get(var_qualified_name, [])


def find_var_usages_with_usage(analysis, var_usage):
    var_qualified_name = (var_usage.get("to"), var_usage.get("name"))

    return analysis.get("vindex_usages", {}).get(var_qualified_name, [])


# ---


def present_local(view, local_binding_region, local_usages_regions, select):
    if select:
        view.sel().clear()
        view.sel().add(local_binding_region)
        view.sel().add_all(local_usages_regions)
    else:
        region_flags = (sublime.DRAW_NO_FILL)

        view.add_regions("pg_pep_find_local_binding", [local_binding_region], scope="region.cyanish", flags=region_flags)
        view.add_regions("pg_pep_find_local_usage", local_usages_regions, scope="region.cyanish", flags=region_flags)


def present_var(view, data):
    thingy = data["thingy"]
    thingy_type, thingy_region, thingy_data = thingy

    var_definition = data["var_definition"]
    var_definition_region = data["var_definition_region"]
    var_usages = data["var_usages"]
    var_usages_regions = data["var_usages_regions"]
    select = data["select"]

    if select:
        view.sel().clear()

        # Var definition is optional - it's valid to find Var usages from a different namespace.
        if var_definition_region:
            view.sel().add(var_definition_region)

        view.sel().add_all(var_usages_regions)
    else:
        var_set = []
        var_regions = []

        if var_definition:
            var_set.append(var_definition)
            var_regions.append(var_definition_region)

        var_set.extend(var_usages)
        var_regions.extend(var_usages_regions)

        quick_panel_items = []

        region_index = 0
        selected_index = 0

        for var_region in var_regions:
            # Find thingy index because we don't want to show a different region.
            if var_region == thingy_region:
                selected_index = region_index

            region_row, region_col = view.rowcol(var_region.begin())

            var_ = var_set[region_index]

            is_definition = bool(var_.get("defined-by"))

            trigger = "Definiton" if is_definition else "Usage"
            details = f"Line {region_row + 1}, Column {region_col + 1}"
            annotation = ""
            kind = sublime.KIND_AMBIGUOUS

            quick_panel_items.append(sublime.QuickPanelItem(trigger, details, annotation, kind))

            region_index += 1


        def on_done(selected_index, _):
            if selected_index == -1:
                region = data["region"]

                view.sel().clear()
                view.sel().add(region)
                view.show(region)

        def on_highlighted(index):
            region = var_regions[index]

            view.sel().clear()
            view.sel().add(region)
            view.show(region)

        var_name = thingy_data.get("name")

        placeholder = None

        if len(var_usages) == 1:
            placeholder = f"{var_name} is used 1 time"
        else:
            placeholder = f"{var_name} is used {len(var_usages)} times"

        view.window().show_quick_panel( quick_panel_items, 
                                        on_done, 
                                        sublime.WANT_EVENT, 
                                        selected_index, 
                                        on_highlighted, 
                                        placeholder )


def find_with_local_binding(view, state, thingy, select):
    _, thingy_region, thingy_data  = thingy    

    local_usages = find_local_usages(state, thingy_data)

    local_usages_regions = []

    for local_usage in local_usages:
        local_usages_regions.append(local_usage_region(view, local_usage))

    present_local(view, thingy_region, local_usages_regions, select)


def find_with_local_usage(view, state, thingy, select):
    _, _, thingy_data  = thingy    

    local_binding = find_local_binding(state, thingy_data)

    # It's possible to have a local usage without a local binding.
    # (It looks like a clj-kondo bug.)
    if local_binding is None:
        return

    local_binding_region_ = local_binding_region(view, local_binding)

    local_usages = find_local_usages(state, local_binding)
    local_usages_regions = []

    for local_usage in local_usages:
        local_usages_regions.append(local_usage_region(view, local_usage))

    present_local(view, local_binding_region_, local_usages_regions, select)


def find_with_var_definition(view, analysis, region, thingy, select):
    _, thingy_region, thingy_data  = thingy

    var_usages = find_var_usages(analysis, thingy_data)

    var_usages_regions = []

    for var_usage in var_usages:
        var_usages_regions.append(var_usage_region(view, var_usage))

    present_var(view, { "region": region,
                        "thingy": thingy,
                        "var_definition": thingy_data,
                        "var_definition_region": thingy_region,
                        "var_usages": var_usages,
                        "var_usages_regions": var_usages_regions,
                        "select": select })


def find_with_var_usage(view, state, region, thingy, select):
    is_debug = debug()

    _, thingy_region, thingy_data  = thingy

    var_definition = find_var_definition(state, thingy_data)
    var_definition_region_ = None

    var_usages = []

    if var_definition:
        var_definition_region_ = var_definition_region(view, var_definition)
        var_usages.extend(find_var_usages(state, var_definition))
    else:
        if is_debug:
            print("(Pep) Find Var usages with usage:", thingy_data)

        var_usages.extend(find_var_usages_with_usage(state, thingy_data))

    var_usages_regions = []

    for var_usage in var_usages:
        var_usages_regions.append(var_usage_region(view, var_usage))

    present_var(view, { "region": region,
                        "thingy": thingy,
                        "var_definition": var_definition,
                        "var_definition_region": var_definition_region_,
                        "var_usages": var_usages,
                        "var_usages_regions": var_usages_regions,
                        "select": select })


# ---


class PgPepEraseAnalysisRegionsCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        erase_analysis_regions(self.view)


class PgPepEraseUsageRegionsCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        erase_usage_regions(self.view)


class PgPepAnalyzeClasspathCommand(sublime_plugin.WindowCommand):

    def run(self):
        analyze_classpath_async(self.window)


class PgPepAnalyzePathsCommand(sublime_plugin.WindowCommand):

    def run(self):
        analyze_paths_async(self.window)


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

        thingy_type, _, thingy_data  = thingy

        var_key = None

        if thingy_type == "var_definition":
            var_key = (thingy_data.get("ns"), thingy_data.get("name"))

        elif thingy_type == "var_usage":
            var_key = (thingy_data.get("to"), thingy_data.get("name"))
            
        project_path_ = project_path(self.view.window())

        paths_analysis_ = paths_analysis(project_path_)

        project_analysis_ = project_analysis(project_path_)

        # Try to find Var definition in view first,
        # only if not found try paths and project analysis.
        definition = (analysis_vindex(view_analysis_).get(var_key) or 
                        analysis_vindex(paths_analysis_).get(var_key) or 
                        analysis_vindex(project_analysis_).get(var_key))

        if definition:
            if is_debug:
                print("(Pep) Var definition:\n", pprint.pformat(definition))

            # Name
            # ---

            name = definition.get("name", "")
            name = inspect.cleandoc(html.escape(name))

            ns = definition.get("ns", "")
            ns = inspect.cleandoc(html.escape(ns))

            filename = definition.get("filename")

            name_minihtml = f"""
            <p class="name">
                <a href="{filename}">{ns}/{name}</a>
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

            location = parse_location(definition)

            self.view.show_popup(
                content, 
                location=-1, 
                max_width=500,
                on_navigate=lambda href: goto(self.view.window(), location)
            )


class PgPepNavigateCommand(sublime_plugin.TextCommand):

    def initialize_thingy_navigation(self, navigation, thingy_id, thingy_findings):
        navigation["thingy_id"] = thingy_id
        navigation["thingy_findings"] = thingy_findings

    def find_position(self, thingy_findings, thingy_data):
        for position, finding in enumerate(thingy_findings):
            if finding == thingy_data:
                return position

        return -1

    def navigate(self, state, direction, findings_position):
        navigation = view_navigation(state)

        findings_position_after = findings_position

        if direction == "forward":
            if findings_position < len(navigation["thingy_findings"]) - 1:
                findings_position_after = findings_position + 1

        elif direction == "back":
            if findings_position > 0:
                findings_position_after = findings_position - 1

        if findings_position != findings_position_after:
            finding_at_position = navigation["thingy_findings"][findings_position_after]

            region = local_binding_region(self.view, finding_at_position)
            region = sublime.Region(region.begin(), region.begin())

            self.view.sel().clear()
            self.view.sel().add(region)
            self.view.show(region)


    def run(self, edit, direction):
        is_debug = debug()

        state = view_analysis(self.view.id())

        region = self.view.sel()[0]

        thingy = thingy_in_region(self.view, state, region)

        if is_debug:
            print("(Pep) Thingy", thingy)

        if thingy is None:
            return

        thingy_type, thingy_region, thingy_data  = thingy

        # Navigation is a dictionary with keys:
        # - thingy_id
        # - thingy_findings
        navigation = view_navigation(state)

        if thingy_type == "local_binding":
            # Find local usages for this local binding (thingy).
            local_usages = find_local_usages(state, thingy_data)

            thingy_findings = [thingy_data]
            thingy_findings.extend(local_usages)

            thingy_id = thingy_data.get("id")

            if thingy_id:
                if thingy_id != navigation.get("thingy_id"):
                    self.initialize_thingy_navigation(navigation, thingy_id, thingy_findings)

                    set_view_navigation(state, navigation)

                position = self.find_position(thingy_findings, thingy_data)

                if position != -1:
                    self.navigate(state, direction, position)

        elif thingy_type == "local_usage":
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
                if thingy_id != navigation.get("thingy_id"):
                    self.initialize_thingy_navigation(navigation, thingy_id, thingy_findings)

                    set_view_navigation(state, navigation)

                position = self.find_position(thingy_findings, thingy_data)

                if position != -1:
                    self.navigate(state, direction, position)

        elif thingy_type == "var_definition":
            # Find Var usages for this Var definition (thingy).
            var_usages = find_var_usages(state, thingy_data)

            thingy_findings = [thingy_data]
            thingy_findings.extend(var_usages)

            thingy_id = (thingy_data.get("ns"), thingy_data.get("name"))

            if thingy_id:
                if thingy_id != navigation.get("thingy_id"):
                    self.initialize_thingy_navigation(navigation, thingy_id, thingy_findings)

                    set_view_navigation(state, navigation)

                position = self.find_position(thingy_findings, thingy_data)

                if position != -1:
                    self.navigate(state, direction, position)

        elif thingy_type == "var_usage":
            # Find Var definition for this Var usage (thingy).
            var_definition = find_var_definition(state, thingy_data)

            var_usages = find_var_usages_with_usage(state, thingy_data)

            thingy_findings = [var_definition] if var_definition else []
            thingy_findings.extend(var_usages)

            thingy_id = (thingy_data.get("to"), thingy_data.get("name"))

            if thingy_id:
                if thingy_id != navigation.get("thingy_id"):
                    self.initialize_thingy_navigation(navigation, thingy_id, thingy_findings)

                    set_view_navigation(state, navigation)

                position = self.find_position(thingy_findings, thingy_data)

                if position != -1:
                    self.navigate(state, direction, position)


class PgPepShowThingy(sublime_plugin.TextCommand):

    def run(self, edit):
        region = self.view.sel()[0]

        analysis = view_analysis(self.view.id())

        thingy = thingy_in_region(self.view, analysis, region)

        if thingy is None:
            return

        thingy_type, _, thingy_data  = thingy

        items_html = ""

        for k,v in thingy_data.items():
            items_html += f"<li>{k}: {v}</li>"

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

        flags = ( sublime.COOPERATE_WITH_AUTO_COMPLETE | 
                  sublime.HIDE_ON_MOUSE_MOVE_AWAY )

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

        thingy_type, _, thingy_data  = thingy

        if thingy_type == "local_usage":
            if (definition := find_local_binding(analysis, thingy_data)):
                if (goto_region := local_binding_region(self.view, definition)):
                    goto_region = sublime.Region(goto_region.begin(), goto_region.begin())

                    self.view.sel().clear()
                    self.view.sel().add(goto_region)
                    self.view.show(goto_region)

        elif thingy_type == "var_usage":
            project_path_ = project_path(self.view.window())

            paths_analysis_ = paths_analysis(project_path_)

            project_analysis_ = project_analysis(project_path_)

            definition = (find_var_definition(analysis, thingy_data) or 
                            find_var_definition(paths_analysis_, thingy_data) or 
                            find_var_definition(project_analysis_, thingy_data))

            if definition:
                global GOTO_SIDE_BY_SIDE_FLAGS
                global GOTO_DEFAULT_FLAGS

                flags = GOTO_SIDE_BY_SIDE_FLAGS if side_by_side else GOTO_DEFAULT_FLAGS

                goto(self.view.window(), parse_location(definition), flags=flags)


class PgPepFindUsagesCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        is_debug = debug()

        analysis = view_analysis(self.view.id())

        region = self.view.sel()[0]

        thingy = thingy_in_region(self.view, analysis, region)

        if is_debug:
            print("(Pep) Thingy", thingy)

        if thingy is None:
            return

        thingy_type, _, thingy_data  = thingy

        project_path_ = project_path(self.view.window())

        paths_analysis_ = paths_analysis(project_path_)

        thingy_usages = None

        if thingy_type == "local_binding":
            thingy_usages = find_local_usages(analysis, thingy_data)

        elif thingy_type == "local_usage":
            thingy_usages = find_local_usages(analysis, thingy_data)

        elif thingy_type == "var_definition":
            thingy_usages = find_var_usages(paths_analysis_, thingy_data)

        elif thingy_type == "var_usage":
            thingy_usages = find_var_usages_with_usage(paths_analysis_, thingy_data)


        if thingy_usages:

            if len(thingy_usages) == 1:
                location = parse_location(thingy_usages[0])

                goto(self.view.window(), location)
                
            else:
                quick_panel_items = []

                for thingy_usage in thingy_usages:
                    trigger = thingy_usage.get("from", "Usage")
                    details = f'Line {thingy_usage.get("row", "Row")}, Column {thingy_usage.get("col", "Col")}'
                    annotation = ""
                    kind = sublime.KIND_AMBIGUOUS

                    quick_panel_items.append(sublime.QuickPanelItem(trigger, details, annotation, kind))

                def on_done(selected_index, _):
                    if selected_index == -1:
                        goto(self.view.window(), parse_location(thingy_data))

                def on_highlighted(index):
                    location = parse_location(thingy_usages[index])

                    global GOTO_USAGE_FLAGS

                    goto(self.view.window(), location, flags=GOTO_USAGE_FLAGS)

                placeholder = f"{thingy_data.get('name')} is used {len(thingy_usages)} times"

                self.view.window().show_quick_panel(quick_panel_items, 
                                                    on_done, 
                                                    sublime.WANT_EVENT, 
                                                    0, 
                                                    on_highlighted, 
                                                    placeholder)
            


class PgPepFindCommand(sublime_plugin.TextCommand):

    def run(self, edit, select=False):
        is_debug = debug()

        analysis = view_analysis(self.view.id())

        region = self.view.sel()[0]

        thingy = thingy_in_region(self.view, analysis, region)

        if is_debug:
            print("(Pep) Thingy", thingy)

        if thingy is None:
            return

        thingy_type, _, _  = thingy

        if thingy_type == "local_binding":
            find_with_local_binding(self.view, analysis, thingy, select)

        elif thingy_type == "local_usage":
            find_with_local_usage(self.view, analysis, thingy, select)

        elif thingy_type == "var_definition":
            find_with_var_definition(self.view, analysis, region, thingy, select)

        elif thingy_type == "var_usage":
            find_with_var_usage(self.view, analysis, region, thingy, select)


class PgPepAnalyzeCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        analyze_view_async(self.view)


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
                    <span>{clj_kondo_finding_message(finding)}</span></div>
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

            redish = self.view.style_for_scope('region.redish')['foreground']
            orangish = self.view.style_for_scope('region.orangish')['foreground']

            self.view.add_regions(
                "pg_pep_analysis_error",
                error_region_set,
                scope="region.redish",
                annotations=error_minihtml_set,
                annotation_color=redish,
                flags=(sublime.DRAW_SQUIGGLY_UNDERLINE |
                       sublime.DRAW_NO_FILL |
                       sublime.DRAW_NO_OUTLINE))

            self.view.add_regions(
                "pg_pep_analysis_warning",
                warning_region_set,
                scope="region.orangish",
                annotations=warning_minihtml_set,
                annotation_color=orangish,
                flags=(sublime.DRAW_SQUIGGLY_UNDERLINE |
                       sublime.DRAW_NO_FILL |
                       sublime.DRAW_NO_OUTLINE))

            summary_errors =  analysis_summary(analysis).get("error", 0)
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
                    s = f"File: {self.view.file_name()}\n\n" if self.view.file_name() is not None else ""
                    s += "\n\n".join(error_str_set + warning_str_set)

                    file.write(s)

                v = self.view.window().open_file(path, flags=sublime.ADD_TO_SELECTION | sublime.SEMI_TRANSIENT)
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
        return settings.get('syntax') in {"Packages/Tutkain/Clojure (Tutkain).sublime-syntax",
                                          "Packages/Tutkain/ClojureScript (Tutkain).sublime-syntax",
                                          "Packages/Tutkain/Clojure Common (Tutkain).sublime-syntax",
                                          "Packages/Clojure/Clojure.sublime-syntax",
                                          "Packages/Clojure/ClojureScript.sublime-syntax"}

    def analyze_view(self):
        return set(settings().get("analyze_view", {}))

    def analyze_paths(self):
        return set(settings().get("analyze_paths", {}))

    def on_load_async(self):
        if "on_load_async" in self.analyze_view():
            analyze_view_async(self.view)

    def on_activated_async(self):
        if "on_activated_async" in self.analyze_view():
            analyze_view_async(self.view)

    def on_post_save(self):
        if "on_post_save" in self.analyze_view():
            analyze_view_async(self.view)

    def on_post_save_async(self):
        if "on_post_save_async" in self.analyze_view():
            analyze_view_async(self.view)

        if "on_post_save_async" in self.analyze_paths():
            analyze_paths_async(self.view.window())

    def on_selection_modified(self):
        if settings().get("clear_usages_on_selection_modified", False):
            self.view.run_command("pg_pep_erase_usage_regions")

    def on_close(self):
        """
        It's important to delete a view's state on close.
        """
        set_view_analysis(self.view.id(), {})


class PgPepEventListener(sublime_plugin.EventListener):

    def on_pre_close_project(self, window):
        project_path = window.extract_variables().get("project_path")

        print("(Pep) Clear project cache:", project_path)

        set_project_analysis(project_path, {})


# ---


def plugin_loaded():
    print("Pep coding!")