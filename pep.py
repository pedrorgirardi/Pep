import subprocess
import os
import re
import tempfile
import json
import traceback
import itertools

import sublime_plugin
import sublime


debug = False


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
    global debug

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


def is_name_under_caret(col, n):
    """
    Returns true if col is within col range of `n`.

    `n` is a dictionary with `col` and `end-col` keys.
    """
    return col >= n["col"] and col <= n["end-col"]


def find_local(lrn, row, col):
    for n in lrn.get(row, []):
        if is_name_under_caret(col, n):
            return n


def find_local_usage(lrn_usages, row, col):
    for n in lrn_usages.get(row, []):
        if is_name_under_caret(col, n):
            return n


class PgPepFindUsagesCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        global debug

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

        # Potential local under caret.
        region_local = find_local(lrn, row + 1, col + 1)

        # Local not found. Try to find it in usages.
        if region_local is None:

            if debug:
                print("(Pep) Local not found. Try usages.")

            # Potential local usage under caret.
            region_local_usage = find_local_usage(lrn_usages, row + 1, col + 1)

            if region_local_usage is not None:
                usage_id = region_local_usage.get("id")

                if usage_id is not None:
                    # Get local by ID - local and usages share the same ID.
                    n = lindex.get(usage_id)

                    if n is not None and is_name_under_caret(n["col"] + 1, n):
                        region_local = n

        # Interrupt execution. Could not find local definition or usage.
        if region_local is None:
            return

        analysis = view_analysis(self.view.id())

        usages = []

        for local_usage in analysis.get("local-usages", []):
            if debug:
                if local_usage.get("id") is None:
                    print("(Pep) Usage is missing ID:", local_usage)

            # Usage ID seems to be missing in some cases,
            # therefore it must be read as optional.
            if local_usage.get("id") == region_local["id"]:
                usages.append(local_usage)

        def make_region(d):
            line = int(d["row"]) - 1
            col_start = int(d["col"]) - 1
            col_end = int(d["end-col"]) - 1

            pa = self.view.text_point(line, col_start)
            pb = self.view.text_point(line, col_end)

            return sublime.Region(pa, pb)

        # Include the local name region.
        usage_regions = [make_region(region_local)]

        for usage in usages:
            usage_regions.append(make_region(usage))

        if usage_regions:
            self.view.add_regions(
                "pg_pep_usages",
                usage_regions,
                scope="region.cyanish",
                flags=(sublime.DRAW_NO_FILL)
            )


class PgPepAnalyzeCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        global debug
        global _state_

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
            _state_.get("view", {})[self.view.id()] = {"result": result, "lindex": lindex, "lrn": lrn, "lrn_usages": lrn_usages}

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

            status_messages = []
            status_messages.append(f"Errors: {len(error_region_set)}")
            status_messages.append(f"Warnings: {len(warning_region_set)}")

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


class PgPepSelectCommand(sublime_plugin.TextCommand):

    def noop(*args):
        pass

    def run(self, edit):
        global _state_

        # Indexes by ID and row:
        lindex = view_lindex(self.view.id())
        lrn = view_lrn(self.view.id())
        lrn_usages = view_lrn_usages(self.view.id())


        # All locals that must be renamed.
        locals_to_rename = []


        caret_region = self.view.sel()[-1]
        caret_row, caret_col = self.view.rowcol(caret_region.a)

        caret_local = find_local(lrn, caret_row + 1, caret_col + 1)

        if caret_local is None:
            # Potential local usage under caret.
            caret_local_usage = find_local_usage(lrn_usages, caret_row + 1, caret_col + 1)

            if caret_local_usage is None:
                return

            local_usage_id = caret_local_usage.get("id")

            if local_usage_id is None:
                return

            # Locals and usages share the same ID.
            caret_local = lindex.get(local_usage_id)


        if caret_local is None:
            return

        locals_to_rename.append(caret_local)

        # TODO: Find all usages.

        for row in range(caret_local["row"] - 1, caret_local["scope-end-row"]):
            # Usages per row.
            usages = lrn_usages.get(row + 1)

            if usages:
                for usage in usages:
                    if usage.get("id") == caret_local.get("id"):
                        locals_to_rename.append(usage)

        selections = []

        for local in locals_to_rename:
            row = local["row"] - 1
            col_start = local["col"] - 1
            col_end = local["end-col"] - 1

            region = sublime.Region(
                self.view.text_point(row, col_start), 
                self.view.text_point(row, col_end)
            )

            selections.append(region)

        if selections:
            self.view.sel().clear()
            self.view.sel().add_all(selections)


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

