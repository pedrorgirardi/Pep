import subprocess
import os
import re
import tempfile
import json
import traceback
import itertools

import sublime_plugin
import sublime


_state_ = {"view": {}}


def settings():
    return sublime.load_settings("Pep.sublime-settings")


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
    view.erase_regions("pg_pep_usages")


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

def view_state(view_id):
    global _state_
    return _state_.get("view", {}).get(view_id, {})

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


def is_name_under_caret(col, n):
    """
    Returns true if col is within col range of `n`.

    `n` is a dictionary with `col` and `end-col` keys.
    """
    col_start = n.get("name-col") or n.get("col")
    col_end = n.get("name-end-col") or n.get("end-col")

    return col >= col_start and col <= col_end


def find_under_caret(index, row, col):
    """
    Find name under caret in index by row.
    """
    for n in index.get(row, []):
        if is_name_under_caret(col, n):
            return n


def find_local(lrn, row, col):
    """
    Find local definition under caret.
    """
    for n in lrn.get(row, []):
        if is_name_under_caret(col, n):
            return n


def find_local_usage(lrn_usages, row, col):
    """
    Find local usage under caret.
    """
    for n in lrn_usages.get(row, []):
        if is_name_under_caret(col, n):
            return n

def find_var(vrn, row, col):
    """
    Find Var definition under caret.
    """
    return find_under_caret(vrn, row, col)

def find_var_usage(vrn_usages, row, col):
    """
    Find Var usage under caret.
    """
    return find_under_caret(vrn_usages, row, col)


def name_region(view, data):
    name_row_start = data["name-row"]
    name_col_start = data["name-col"]

    name_row_end = data["name-end-row"]
    name_col_end = data["name-end-col"]

    name_start_point = view.text_point(name_row_start - 1, name_col_start - 1)
    name_end_point = view.text_point(name_row_end - 1, name_col_end - 1)

    return sublime.Region(name_start_point, name_end_point)


def local_usage_in_region(view, lrn_usages, region):
    region_begin_row, _ = view.rowcol(region.begin())

    usages = lrn_usages.get(region_begin_row + 1)

    for usage in usages:        
        usage_region = name_region(view, usage)

        if usage_region.contains(region):
            return usage


def thingy_in_region(view, state, region):

    thingy_data = local_usage_in_region(view, state.get("lrn_usages", {}), region)

    if thingy_data:
        return (thingy_data, "local_usage")


def make_region(view, d):
    """
    Usages have row and col for name - name-row, name-col, name-end-col.

    Usage entails more than the location of a symbol,
    it extends row and col based on how a symbol
    is used in a particular location.

    Example:

    (fn [f] (f|))

    `f` usage data will extend row and col to match the parenthesis.

    Var or local definition doesn't have row and col for name - it's simply row and col.
    """
    line = (d.get("name-row") or d.get("row")) - 1
    col_start = (d.get("name-col") or d.get("col")) - 1
    col_end = (d.get("name-end-col") or d.get("end-col")) - 1

    text_point_a = view.text_point(line, col_start)
    text_point_b = view.text_point(line, col_end)

    return sublime.Region(text_point_a, text_point_b)

class PgPepFindCommand(sublime_plugin.TextCommand):

    def run(self, edit, select=False):
        state = view_state(self.view.id())

        sel_region = self.view.sel()[0]

        thingy = thingy_in_region(self.view, state, sel_region)

        print("thingy", thingy)


class PgPepFindUsagesCommand(sublime_plugin.TextCommand):

    def var_quick_panel(self, caret_region, var_under_caret, var_definition_and_usages):
        var_quick_panel_items = []

        quick_panel_selected_index = 0

        var_definition_usages_index = 0

        for var_definition_or_usage in var_definition_and_usages:
            if var_definition_or_usage == var_under_caret:
                quick_panel_selected_index = var_definition_usages_index

            var_definition_usages_index += 1

            is_definition = bool(var_definition_or_usage.get("defined-by"))

            trigger = f"{'Definition' if is_definition else 'Usage'}"
            details = ""
            annotation = f"{var_definition_or_usage['name-row']}:{var_definition_or_usage['name-col']}"
            kind = sublime.KIND_VARIABLE

            var_quick_panel_items.append(sublime.QuickPanelItem(trigger, details, annotation, kind))


        def on_done(selected_index, _):
            if selected_index == -1:
                self.view.sel().clear()
                self.view.sel().add(caret_region)
                self.view.show_at_center(caret_region)

                return

        def on_highlighted(index):
            selected_var = var_definition_and_usages[index]

            selected_var_region = make_region(self.view, selected_var)

            self.view.sel().clear()
            self.view.sel().add(selected_var_region)
            self.view.show_at_center(selected_var_region)

        placeholder = f"{var_under_caret['name']} is used {len(var_definition_and_usages) - 1} times"

        self.view.window().show_quick_panel(var_quick_panel_items, 
                                            on_done, 
                                            sublime.WANT_EVENT, 
                                            quick_panel_selected_index, 
                                            on_highlighted, 
                                            placeholder)


    def run(self, edit, select=False):
        debug = settings().get("debug", False)

        # It's the last region because find usages is for a single name.
        region = self.view.sel()[-1]

        # Question: does it matter which one we use: a (start) or b (end)?
        row,col = self.view.rowcol(region.a)

        lrn = view_lrn(self.view.id())

        lrn_usages = view_lrn_usages(self.view.id())

        lindex = view_lindex(self.view.id())

        if debug:
            print(f"(Pep) View({self.view.id()}) lindex", lindex)
            print(f"(Pep) View({self.view.id()}) lrn", lrn)
            print(f"(Pep) View({self.view.id()}) lrn_usages", lrn_usages)

        local_under_caret = find_local(lrn, row + 1, col + 1)

        # Try local usages instead.
        if local_under_caret is None:

            # Potential local usage under caret.
            local_usage_under_caret = find_local_usage(lrn_usages, row + 1, col + 1)

            if local_usage_under_caret is not None:
                usage_id = local_usage_under_caret.get("id")

                if usage_id is not None:
                    # Get local by ID - local and usages share the same ID.
                    n = lindex.get(usage_id)

                    if n is not None and is_name_under_caret(n["col"] + 1, n):
                        local_under_caret = n

        # Try Vars instead.
        if local_under_caret is None:
            vrn = view_vrn(self.view.id())

            var_under_caret = find_var(vrn, row + 1, col + 1)

            if var_under_caret is None:
                vrn_usages = view_vrn_usages(self.view.id())

                var_under_caret = find_var_usage(vrn_usages, row + 1, col + 1)

            # Var definition nor usage is found. Interrupt execution.
            if var_under_caret is None:
                return

            is_var_under_caret_definition = bool(var_under_caret.get("defined-by"))
            
            var_under_caret_namespace = var_under_caret.get("ns") or var_under_caret.get("to")

            var_under_caret_name = var_under_caret["name"]

            # Var is indexed by its qualified name.
            qualified_name = (var_under_caret_namespace, var_under_caret_name)

            vindex = view_vindex(self.view.id())

            var_definition = var_under_caret if is_var_under_caret_definition else vindex[qualified_name]

            # A list of a Var definition and all its usages.
            var_definition_and_usages = [var_definition]

            analysis = view_analysis(self.view.id())

            for var_usage in analysis.get("var-usages", []):
                if var_usage.get("from") == var_under_caret_namespace and var_usage.get("name") == var_under_caret_name:
                    var_definition_and_usages.append(var_usage)

            # Var definition and usages are shown in a Quick Panel,
            # but if select arg is true, it will simply select the regions.
            
            if select:
                self.view.sel().clear()

                for var_definition_or_usage in var_definition_and_usages:
                    self.view.sel().add(make_region(self.view, var_definition_or_usage))
            else:
                self.var_quick_panel(region, var_under_caret, var_definition_and_usages)

            return

        analysis = view_analysis(self.view.id())

        usages = []

        for local_usage in analysis.get("local-usages", []):
            if debug:
                if local_usage.get("id") is None:
                    print("(Pep) Usage is missing ID:", local_usage)

            # Usage ID seems to be missing in some cases,
            # therefore it must be read as optional.
            if local_usage.get("id") == local_under_caret["id"]:
                usages.append(local_usage)

        # Include the local name region.
        usage_regions = [make_region(self.view, local_under_caret)]

        for usage in usages:
            usage_regions.append(make_region(self.view, usage))

        if usage_regions:
            if select:
                self.view.sel().clear()
                self.view.sel().add_all(usage_regions)
            else:
                self.view.add_regions(
                    "pg_pep_usages",
                    usage_regions,
                    scope="region.cyanish",
                    flags=(sublime.DRAW_NO_FILL)
                )


class PgPepAnalyzeCommand(sublime_plugin.TextCommand):

    def run(self, edit, annotate=False):
        global _state_

        debug = settings().get("debug", False)

        try:

            def finding_region(finding):
                line_start = finding["row"] - 1

                # Fallback to `row` if `end-row` doesn't exist.
                line_end = (finding.get("end-row") or finding.get("row")) - 1

                col_start = finding["col"] - 1
                col_end = finding["end-col"] - 1

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

            result = analize(self.view)

            # Pretty print clj-kondo result.
            if debug:
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

            # Region annotations (optional).
            if annotate:
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
            print(f"(Pep) Analysis failed.", traceback.format_exc())


class PgPepReportCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        try:
            def finding_str(finding):
                message = clj_kondo_finding_message(finding)

                return f'{finding["level"].capitalize()}: {message}\n[{finding["row"]}.{finding["col"]}:{finding["end-col"]}]'

            analysis = analize(self.view)

            findings = analysis["findings"] if "findings" in analysis else []

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
            print(f"(Pep) Analysis failed.", traceback.format_exc())


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

    def on_selection_modified(self):
        if settings().get("clear_usages_on_selection_modified", False):
            self.view.run_command("pg_pep_erase_usage_regions")

