# CHANGELOG

All notable changes to this project will be documented in this file.

## 0.12.0 -
- Merged commands **Jump to Require** and **Jump to Import** into **Goto Require/Import in View**
- Renamed `Goto Analysis Finding` to `Goto Warning/Error in View`
- Added `side_by_side` arg to goto commands:
	- Goto side-by-side if set to true
- Refactor Find Usages
	- Removed scope
- New command: `Goto Namespace Usages in View`
- New command: `Browse Classpath`
- Removed duplicates in QuickPanel
- Improved `Replace` command

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
