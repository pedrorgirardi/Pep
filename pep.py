import subprocess
import os
import re
import tempfile
import json
import traceback

import sublime_plugin
import sublime

from Tutkain.api import edn
from Tutkain.src.repl import views
from Tutkain.src import dialects

DEBUG = False


def program_path(program):
    return os.path.join(sublime.packages_path(), "Pep", "bin", program)


def clj_kondo_path():
    return program_path("clj-kondo")


def zprint_path():
    return program_path("zprint")


def clj_kondo_process_args(file_name=None):
    config = "{:lint-as {reagent.core/with-let clojure.core/let} \
               :output {:analysis true :format :json}}"

    # clj-kondo seems to use different analysis based on the file extension.
    # We might get false positives if we only read from stdin.

    return [clj_kondo_path(), "--config", config, "--lint", file_name or "-"]


def clj_kondo_analysis(view):
    window = view.window()
    view_file_name = view.file_name()
    project_file_name = window.project_file_name() if window else None

    cwd = None

    if project_file_name:
        cwd = os.path.dirname(project_file_name)
    elif view.file_name():
        cwd = os.path.dirname(view_file_name)

    global DEBUG
    if DEBUG:
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


def set_view_name(view, name):
    if view is not None:
        if view.is_loading():
            sublime.set_timeout(lambda: set_view_name(view, name), 100)
        else:
            view.set_name(name)


def view_text(view):
    return view.substr(sublime.Region(0, view.size()))


class PepFormatCommand(sublime_plugin.TextCommand):
    """
    Command to formnat Clojure and JSON.

    Clojure is formatted by zprint.
    JSON is formatted using the built-in Python JSON API.
    """

    def run(self, edit):
        syntax = self.view.syntax()

        for region in self.view.sel():
            region = sublime.Region(0, self.view.size()) if region.empty() else region

            if syntax.scope == 'source.clojure':
                self.format_clojure(edit, region)
            elif syntax.scope == 'source.json':
                self.format_json(edit, region)

    def format_json(self, edit, region):
        try:
            decoded = json.loads(self.view.substr(region))

            formatted = json.dumps(decoded, indent=4)

            self.view.replace(edit, region, formatted)
        except Exception as e:
            print(f"(Pep) Failed to format JSON: {e}")

    def format_clojure(self, edit, region):
        zprint_config = f"{{:style :respect-bl}}"

        process = subprocess.Popen(
            [zprint_path(), zprint_config],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        try:
            stdout, stderr = process.communicate(self.view.substr(region).encode())

            formatted = stdout.decode("utf-8")

            if formatted:
                self.view.replace(edit, region, formatted)

        except subprocess.TimeoutExpired as e:
            print(f"(Pep) Failed to format Clojure: {e}")

            process.kill()


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

    elif t == "redefined-var":
        minihtml = "Redefined: " + group1(r"^redefined var ([^\s]*)")

    else:
        minihtml = finding["message"]

    return minihtml


def erase_analysis_regions(view):
    view.erase_regions("analysis_error")
    view.erase_regions("analysis_warning")


class PgPepEraseAnalysisRegionsCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        erase_analysis_regions(self.view)


class PgPepAnalyzeCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        try:

            def finding_region(finding):
                line = int(finding["row"]) - 1
                col_start = int(finding["col"]) - 1
                col_end = int(finding["end-col"]) - 1

                pa = self.view.text_point(line, col_start)
                pb = self.view.text_point(line, col_end)

                return sublime.Region(pa, pb)

            def finding_minihtml(finding):
                return f"""
                <body>
                <div">
                    <span>{clj_kondo_finding_message(finding)}</span></div>
                </div>
                </body>
                """

            analysis = clj_kondo_analysis(self.view)

            findings = analysis.get("findings", [])

            # Pretty print clj-kondo analysis.
            global DEBUG
            if DEBUG:
                print(json.dumps(findings, indent=4))

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
                "analysis_error",
                error_region_set,
                scope="region.redish",
                annotations=error_minihtml_set,
                annotation_color=redish,
                flags=(sublime.DRAW_SQUIGGLY_UNDERLINE |
                       sublime.DRAW_NO_FILL |
                       sublime.DRAW_NO_OUTLINE))

            self.view.add_regions(
                "analysis_warning",
                warning_region_set,
                scope="region.orangish",
                annotations=warning_minihtml_set,
                annotation_color=orangish,
                flags=(sublime.DRAW_SQUIGGLY_UNDERLINE |
                       sublime.DRAW_NO_FILL |
                       sublime.DRAW_NO_OUTLINE))

        except Exception as e:
            print(f"(Pep) Analysis failed.", traceback.format_exc())


class PgPepReportCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        try:
            def finding_str(finding):
                message = clj_kondo_finding_message(finding)

                return f'{finding["level"].capitalize()}: {message}\n[{finding["row"]}.{finding["col"]}:{finding["end-col"]}]'

            analysis = clj_kondo_analysis(self.view)

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

    @classmethod
    def is_applicable(_, settings):
        return settings.get('syntax') in {"Packages/Tutkain/Clojure (Tutkain).sublime-syntax",
                                          "Packages/Tutkain/ClojureScript (Tutkain).sublime-syntax",
                                          "Packages/Clojure/Clojure.sublime-syntax",
                                          "Packages/Clojure/ClojureScript.sublime-syntax"}

    def on_load(self):
        self.view.run_command("pg_pep_analyze")

    def on_post_save(self):
        self.view.run_command("pg_pep_analyze")


class MyTutkainDisconnectCommand(sublime_plugin.WindowCommand):

    def run(self):
        if view := views.active_repl_view(self.window):
            active_view = self.window.active_view()
            host = view.settings().get("tutkain_repl_host")
            port = view.settings().get("tutkain_repl_port")
            dialect = edn.Keyword(view.settings().get("tutkain_repl_view_dialect"))
            dialect_name = dialects.name(dialect)

            ret = sublime.ok_cancel_dialog(
                f"Disconnect from {dialect_name} REPL at {host}:{port}?",
                "Disconnect"
            )

            if ret == sublime.DIALOG_YES:
                # inline.clear(active_view)
                test.progress.stop()
                view.close()

            self.window.focus_view(active_view)
