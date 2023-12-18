# CHANGELOG

All notable changes to this project will be documented in this file.

## 0.22.0 - in development
- `PgPepInspect` now shows data in a popup
- New Command `PgPepGotoUsageInViewCommand`

Breaking:
- Delete `PgPepTraceUsagesCommand`

## 0.21.0 - 2023-11-06
- [PgPepFindUsagesCommand Output #69](https://github.com/pedrorgirardi/Pep/issues/69)

## 0.20.0 - 2023-11-04
New:
- [Command to Toggle View Annotations #70](https://github.com/pedrorgirardi/Pep/issues/70)

Breaking:
- Removed Command `PgPepClearAnnotationsCommand`
- Removed Command `PgPepAnnotateCommand`
- Removed Commands `PgPepClearHighlightedCommand` and `PgPepToggleHighlightCommand`
- Removed Command `PgPepViewNamespaceStatusCommand` and its settings:
	- `view_status_show_namespace`
	- `view_status_show_namespace_prefix`
	- `view_status_show_namespace_suffix`

## 0.19.0 - 2023-10-31
There were many internal changes in this version and I'm sorry I made some breaking changes.

Breaking:
- `pg_pep_find` is now `pg_pep_find_usages`
- `pg_pep_goto_definition2` is now the default, but as `pg_pep_goto_definition`

New:
- `pg_pep_goto_usage`

Other:
- Tweak documentation UI - add a line break after function arity
- Status messages: 'Analyzing classpath...', 'Anayzing paths...'
- Fix Java static class method usage

## 0.18.0 - 2023-04-05
- New **Goto Definition** command `pg_pep_goto_definition2` to handle multiple definitions
- Fix warning/error annotation color - fallback to orange and red, respectively.

## 0.17.0 - 2023-02-25
- Goto Symbol definition
- Find Symbol usages
- Show Symbol documentation

## 0.16.1 - 2022-12-22
- Fix None Window in `project_path`
- Fix **Trace Usages** Window flags

## 0.16.0 - 2022-11-25
- Support Clojure Sublimed

## 0.15.0 - 2022-11-01
- Fixed a bug in show documentation
- Improved `annotate_view_on_save`

## 0.14.1 - 2022-10-05
- Fix `project_data` for `None` Window

## 0.14.0 - 2022-10-05
- New command: **Annotate View** (`pg_pep_annotate_view`)
- New command: **Clear View Annotations** (`pg_pep_clear_view_annotations`)
- New setting: `annotate_view_on_save`
	- True if warnings/errors should be displayed only when a view is saved. See `Pep.sublime-settings`
- Breaking change: renamed setting `annotate_view_analysis` to `annotate_view_after_analysis`
	- True if warnings/errors should be displayed right after the analysis is completed. See `Pep.sublime-settings`

## 0.13.0 - 2022-09-29
- Fix `pg_pep_show_doc` `side_by_side`;
- Show documentation: added support for multiple cursors;
- Highlight symbol/keyword after analysis;
- New setting `analysis_delay`;

## 0.12.0 - 2022-09-07
- Merged commands **Jump to Require** and **Jump to Import** into **Goto Require/Import in View** (`pg_pep_goto_require_import_in_view`)
- Renamed **Goto Analysis Finding** to **Goto Warning/Error in View** (`pg_pep_goto_warning_error_in_view`)
- Added `side_by_side` arg to goto commands:
	- Goto side-by-side if set to true
- Refactor Find Usages
	- Removed scope
- New command: **Goto Namespace Usage in View** (`pg_pep_goto_namespace_usage_in_view`)
- New command: **Browse Classpath** (`pg_pep_browse_classpath`)
- Removed duplicates in QuickPanel
- Improved `Replace` command (`pg_pep_replace`)
- Analyze Babashka files

## 0.11.0 - 2022-07-26
- Changed default setting `view_status_show_highlighted_prefix`:
	- Prefix is now set to `Highlighted: `
- Improved region highlighting:
	- Fix flickery when moving the cursor within a highligted region

## 0.10.0 - 2022-07-23
- Renamed command ~~Goto Require~~ to **Jump to Require**
- Renamed command ~~Goto Import~~ to **Jump to Import**

## 0.9.0 - 2022-07-23
- Added a new Goto command: Goto Require (Fixes [#28](https://github.com/pedrorgirardi/Pep/issues/28))
- Added a new Goto command: Goto Import (Fixes [#62](https://github.com/pedrorgirardi/Pep/issues/62))
- Goto Analysis Finding - Removed file path from Quick Panel Item
- Added a new setting 'analysis_applicable_to' to set applicable analysis syntaxes

## 0.8.1 - 2022-07-21
- Use KIND_ID_ prefix to support older versions of Sublime Text

## 0.8.0 - 2022-07-20
- Tweaked error logs
- Improved paths indexing
	- Removed "analyze_paths_on_post_save" setting because it's no longer needed;
- Improved view analysis & annotations

## 0.7.0 - 2022-07-04
- Don't trigger command to highlight region on selection modified
	- Call function directly instead of invoking command
- [Goto Analysis Finding #55](https://github.com/pedrorgirardi/Pep/issues/55)
- Fix paths analysis on Windows
	- On Windows, path separator is `;`
	- On Linux and Mac is `:`
- Rework commands to prompt for scope
- New command `pg_pep_rename` to rename in view

## 0.6.0 - 2022-06-17
- New command **Pep: Outline**
- Added command **Pep: Settings** to Command Palette
- Added command **Pep: Show Documentation** to Command Palette
- Added command **Pep: Show Documentation Side by Side** to Command Palette
- Added support for project specific settings [#51](https://github.com/pedrorgirardi/Pep/issues/53)
- Added ⚠ to error or warning status
- Added support for finding usages of locals
- Improved finding annotation error handling
- Windows: Fixed clj-kondo subprocess launch
- Fixes [#58](https://github.com/pedrorgirardi/Pep/issues/58)
- Improve paths analysis performance
	- Use `:var-definitions {:shallow true}` config
- Show namespace docstring in QuickPanel

## 0.5 - 2022-04-08
- Revert scratch change
- Internal: rename function `open_jar`
- Fix QuickPanelItem file type annotation
- New settings:
	- `show_view_namespace`
	- `view_namespace_prefix`
	- `view_namespace_suffix`
- Add commands to Command Palette:
	- Most of Pep commands are now available in the **Command Palette**;
- Analyze Java class usages
	- Now `Pep: Find Usages` (in view or path) works for Java classes too;

## 0.4 - 2022-03-25
- Improvement: Goto always sets view as scratch

## 0.3 - 2022-03-24
- New setting `clj_kondo_path`

## 0.2 - 2022-03-01
- New setting `annotation_font_size`
- Rename command `pg_pep_show_name`

## 0.1 - 2022-02-26
- Initial release
