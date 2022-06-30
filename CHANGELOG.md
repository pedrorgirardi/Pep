# CHANGELOG

All notable changes to this project will be documented in this file.

## 0.7.0 - Unreleased
- Don't trigger command to highlight region on selection modified
- [Goto Analysis Finding #55](https://github.com/pedrorgirardi/Pep/issues/55)
- Fix paths analysis on Windows
	- On Windows, path separator is `;`
	- On Linux and Mac is `:`

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
