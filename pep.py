import subprocess
import os
import re
import tempfile
import json
import traceback
import itertools
import pprint

import sublime_plugin
import sublime


_state_ = {"view": {}}


def settings():
    return sublime.load_settings("Pep.sublime-settings")

def debug():
    return sublime.load_settings("Pep.sublime-settings").get("debug", False)

def set_view_name(view, name):
    if view is not None:
        if view.is_loading():
            sublime.set_timeout(lambda: set_view_name(view, name), 100)
        else:
            view.set_name(name)


def view_text(view):
    return view.substr(sublime.Region(0, view.size()))


def program_path(program):
    return os.path.join(sublime.packages_path(), "Pep", "bin", program)


def clj_kondo_path():
    return program_path("clj-kondo")


def clj_kondo_process_args(file_name=None):
    config = "{:lint-as {reagent.core/with-let clojure.core/let} \
               :output {:analysis {:locals true} :format :json}}"

    # clj-kondo seems to use different analysis based on the file extension.
    # We might get false positives if we only read from stdin.

    return [clj_kondo_path(), "--config", config, "--lint", file_name or "-"]


def analize(view):
    debug = settings().get("debug", False)

    window = view.window()
    view_file_name = view.file_name()
    project_file_name = window.project_file_name() if window else None

    cwd = None

    if project_file_name:
        cwd = os.path.dirname(project_file_name)
    elif view.file_name():
        cwd = os.path.dirname(view_file_name)

    if debug:
        print("(Pep) cwd", cwd)

    process = subprocess.Popen(
        clj_kondo_process_args(view.file_name()),
        cwd=cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    try:
        stdout, stderr = process.communicate(
            view_text(view).encode()) if view.file_name() is None else process.communicate()

        stderr_decoded = stderr.decode()

        # If clj-kondo had any sort of error, we need to raise an exception.
        # (It's up to the caller to handle it.)
        if stderr_decoded:
            raise Exception(stderr_decoded)

        return json.loads(stdout.decode())
    except subprocess.TimeoutExpired as e:
        process.kill()
        raise e


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


class PgPepEraseAnalysisRegionsCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        erase_analysis_regions(self.view)


class PgPepEraseUsageRegionsCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        erase_usage_regions(self.view)


def view_vindex(id):
    """
    Returns a dictionary of locals by ID.

    This index can be used to find a local in constant time if you know its ID.

    When finding usages from a usage itself, the first step is to find the usage,
    once you have found it, you can use its ID to find the local.

    Locals and usages have the same ID, 
    so it's possible to corretale a usage with a local.

    'lindex' stands for 'local index'.
    """
    global _state_
    return _state_.get("view", {}).get(id, {}).get("vindex", {})


def view_vrn(id):
    """
    Returns a dictionary of Vars by row.

    This index can be used to quicky find a Var definition by row.

    'vrn' stands for 'var row name'.
    """
    global _state_
    return _state_.get("view", {}).get(id, {}).get("vrn", {})


def view_vrn_usages(id):
    """
    Returns a dictionary of Var usages by row.

    This index can be used to quicky find a Var usage by row.

    'vrn' stands for 'var row name'.
    """
    global _state_
    return _state_.get("view", {}).get(id, {}).get("vrn_usages", {})


def view_lindex(id):
    """
    Returns a dictionary of locals by ID.

    This index can be used to find a local in constant time if you know its ID.

    When finding usages from a usage itself, the first step is to find the usage,
    once you have found it, you can use its ID to find the local.

    Locals and usages have the same ID, 
    so it's possible to corretale a usage with a local.

    'lindex' stands for 'local index'.
    """
    global _state_
    return _state_.get("view", {}).get(id, {}).get("lindex", {})


def view_lrn(id):
    """
    Returns a dictionary of locals by row.

    This index can be used to quicky find a local definition by row.

    Example: (let [a| 1] ...)

    'lrn' stands for 'local row name'.
    """
    global _state_
    return _state_.get("view", {}).get(id, {}).get("lrn", {})

def view_lrn_usages(id):
    """
    Returns a dictionary of local usages by row.

    This index can be used to quicky find a local usage by row.

    Example: (let [a 1] |a)

    'lrn' stands for 'local row name'.
    """
    global _state_
    return _state_.get("view", {}).get(id, {}).get("lrn_usages", {})


def view_analysis(id):
    """
    Returns clj-kondo analysis.
    """
    global _state_
    return _state_.get("view", {}).get(id, {}).get("result", {}).get("analysis", {})


def view_state(view_id):
    global _state_
    return _state_.get("view", {}).get(view_id, {})


def view_navigation(view_state):
    return view_state.get("navigation", {})

def set_view_navigation(view_state, navigation):
    view_state["navigation"] = navigation


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

    row_start = local_binding["row"]
    col_start = local_binding["col"]

    row_end = local_binding["end-row"]
    col_end = local_binding["end-col"]

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


def find_local_binding(state, local_usage):
    return state.get("lindex", {}).get(local_usage.get("id"))


def find_local_usages(state, local_binding):
    usages = []

    for local_usage in state.get("result", {}).get("analysis", {}).get("local-usages", []):
        if local_usage.get("id") == local_binding.get("id"):
            usages.append(local_usage)

    return usages


def find_var_definition(state, var_usage):
    var_qualified_name = (var_usage.get("to"), var_usage.get("name"))

    return state.get("vindex", {}).get(var_qualified_name)


def find_var_usages(state, var_definition):
    usages = []

    for var_usage in state.get("result", {}).get("analysis", {}).get("var-usages", []):
        if (var_usage.get("to") == var_definition.get("ns") and 
            var_usage.get("name") == var_definition.get("name")):
            usages.append(var_usage)

    return usages


def find_var_usages_with_usage(state, var_usage):
    usages = []

    for _var_usage in state.get("result", {}).get("analysis", {}).get("var-usages", []):
        if (_var_usage.get("from") == var_usage.get("from") and 
            _var_usage.get("to") == var_usage.get("to") and 
            _var_usage.get("name") == var_usage.get("name")):
            usages.append(_var_usage)

    return usages

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


def find_with_var_definition(view, state, region, thingy, select):
    _, thingy_region, thingy_data  = thingy

    var_usages = find_var_usages(state, thingy_data)

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

class PgPepNavigateCommand(sublime_plugin.TextCommand):

    def initialize_thingy_navigation(self, navigation, thingy_id, thingy_findings):
        navigation["thingy_id"] = thingy_id
        navigation["thingy_findings"] = thingy_findings

    def find_position(self, thingy_findings, thingy_data):
        findings_position = 0

        for finding in thingy_findings:
            if finding == thingy_data:
                return findings_position

            findings_position += 1

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

            self.view.sel().clear()
            self.view.sel().add(region)
            self.view.show(region)


    def run(self, edit, direction):
        is_debug = debug()

        state = view_state(self.view.id())

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

class PgPepShowThingy(sublime_plugin.TextCommand):

    def run(self, edit):
        state = view_state(self.view.id())

        region = self.view.sel()[0]

        thingy = thingy_in_region(self.view, state, region)

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


class PgPepFindCommand(sublime_plugin.TextCommand):

    def run(self, edit, select=False):
        is_debug = debug()

        state = view_state(self.view.id())

        region = self.view.sel()[0]

        thingy = thingy_in_region(self.view, state, region)

        if is_debug:
            print("(Pep) Thingy", thingy)

        if thingy is None:
            return

        thingy_type, _, _  = thingy

        if thingy_type == "local_binding":
            find_with_local_binding(self.view, state, thingy, select)

        elif thingy_type == "local_usage":
            find_with_local_usage(self.view, state, thingy, select)

        elif thingy_type == "var_definition":
            find_with_var_definition(self.view, state, region, thingy, select)

        elif thingy_type == "var_usage":
            find_with_var_usage(self.view, state, region, thingy, select)


class PgPepAnalyzeCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        global _state_

        is_debug = settings().get("debug", False)

        try:
            result = analize(self.view)

            # Pretty print clj-kondo result.
            if is_debug:
                print(json.dumps(result, indent=4))

            def result_locals(result):
                return result.get("analysis", {}).get("locals", [])

            def result_local_usages(result):
                return result.get("analysis", {}).get("local-usages", [])

            def result_vars(result):
                return result.get("analysis", {}).get("var-definitions", [])

            def result_var_usages(result):
                return result.get("analysis", {}).get("var-usages", [])

            # -- Var indexes

            # Vars indexed by row.
            vrn = {}

            for r,n in itertools.groupby(result_vars(result), lambda d: d["row"]):
                vrn[r] = list(n)

            # Vars indexed by name - tuple of namespace and name.
            vindex = {}

            for id,n in itertools.groupby(result_vars(result), lambda d: (d["ns"], d["name"])):
                vindex[id] = list(n)[0]

            # Var usages indexed by row.
            vrn_usages = {}

            for r,n in itertools.groupby(result_var_usages(result), lambda d: d["row"]):
                vrn_usages[r] = list(n)


            # -- Local indexes

            # Locals indexed by row.
            lrn = {}

            for r,n in itertools.groupby(result_locals(result), lambda d: d["row"]):
                lrn[r] = list(n)


            # Locals indexed by ID.
            lindex = {}

            for id,n in itertools.groupby(result_locals(result), lambda d: d["id"]):
                lindex[id] = list(n)[0]


            # Local usages indexed by row.
            lrn_usages = {}

            for r,n in itertools.groupby(result_local_usages(result), lambda d: d["row"]):
                lrn_usages[r] = list(n)

            # Update view analysis.
            _state_.get("view", {})[self.view.id()] = { "result": result,
                                                        "vindex": vindex, 
                                                        "vrn": vrn, 
                                                        "vrn_usages": vrn_usages,
                                                        "lindex": lindex, 
                                                        "lrn": lrn, 
                                                        "lrn_usages": lrn_usages }

        except Exception as e:
            print(f"(Pep) Analysis failed.", traceback.format_exc())


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

            state = view_state(self.view.id())

            result = state.get("result", {})

            findings = result.get("findings", [])

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

            summary_errors = result.get("summary", {}).get("error", 0)
            summary_warnings = result.get("summary", {}).get("warning", 0)

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


            state = view_state(self.view.id())

            result = state.get("result", {})

            findings = result.get("findings", [])

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


class PgPepListener(sublime_plugin.ViewEventListener):
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

    def analyze_on(self):
        return set(settings().get("analyze_on", {}))

    def on_load_async(self):
        if "on_load_async" in self.analyze_on():
            self.view.run_command("pg_pep_analyze")

    def on_activated_async(self):
        if "on_activated_async" in self.analyze_on():
            self.view.run_command("pg_pep_analyze")

    def on_post_save(self):
        if "on_post_save" in self.analyze_on():
            self.view.run_command("pg_pep_analyze")

    def on_post_save_async(self):
        if "on_post_save_async" in self.analyze_on():
            self.view.run_command("pg_pep_analyze")

    def on_selection_modified(self):
        if settings().get("clear_usages_on_selection_modified", False):
            self.view.run_command("pg_pep_erase_usage_regions")

    def on_close(self):
        """
        It's important to delete a view's state on close.
        """

        global _state_

        views_state = _state_.get("view", {})

        if self.view.id() in views_state:
            del views_state[self.view.id()]

