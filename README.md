# Pep

![Pep](logo.png)

**Pep** leverages [clj-kondo analysis data](https://github.com/clj-kondo/clj-kondo/tree/master/analysis) to provide code navigation, documentation and usages analysis.

[clj-kondo](https://github.com/clj-kondo/clj-kondo) is the sole dependency, and everything else is supplied by built-in [Sublime Text APIs](https://www.sublimetext.com/docs/api_reference.html).

> [!NOTE]
> I have worked on **Pep** for over two years, but I still consider it alpha.

| Command | Description |
| ------- | ----------- |
| `pg_pep_analyze` | Analyze view, paths or classpath |
| `pg_pep_outline` | Show symbols defined in the namespace - it might also be known as 'file structure' |
| `pg_pep_goto_anything_in_classpath` | Go to anything in the classpath |
| `pg_pep_goto_anything_in_view_paths` | Go to anything in view or paths |
| `pg_pep_goto_namespace` | Go to namespace in paths |
| `pg_pep_goto_definition` | Go to definition of symbol or keyword under the cursor |
| `pg_pep_goto_warning_error_in_view` | Go to clj-kondo analysis finding (warning or error) |
| `pg_pep_goto_require_import_in_view` | Go to require or import for symbol under the cursor |
| `pg_pep_goto_namespace_usage_in_view` | Go to usage of namespace in view |
| `pg_pep_show_doc` | Show documentation in a popup for symbol under the cursor |
| `pg_pep_jump` | Jump to occurrences of symbol or keyword under the cursor |
| `pg_pep_find_usages` | Find usages of symbol or keyword under the cursor |
| `pg_pep_select` | Select occurrences of symbol or keyword under the cursor |
| `pg_pep_replace` | Replace occurrences of symbol or keyword under the cursor |
| `pg_pep_highlight` | Highlight occurrences of symbol or keyword under the cursor |
| `pg_pep_copy_name` | Copy name of keyword or symbol to the clipboard |
| `pg_pep_show_name` | Show name of keyword or symbol in a popup |

**Pep** is part of my Clojure(Script) development setup, combined with [Tutkain](https://github.com/eerohele/Tutkain), so I think it's developed enough to be helpful.

You're welcome to try it, and I would be happy to hear if it works for you. If it doesn't work for you, I ask you to please create an issue, and I will do my best to address it.

## Installation

Pep is available on [PackageControl](https://packagecontrol.io/packages/Pep).


## Annotate (Lint)

![Pep Annotate](docs/Annotate.png)

## Highlight

Highlight the symbol or keyword under the cursor and its usage.

![Pep Highlight](docs/Highlight.png)

## Documentation

Show documentation for var under the cursor.

![Pep Show documentation](docs/Documentation.png)

## Jump

Jump to occurrences of symbol or keyword under cursor.

![Pep Jump](docs/Jump.gif)

## Find Usages

Find usages of symbol or keyword under cursor.

![Pep Find Usages](docs/FindUsages.png)

## Select

Select occurrences of symbol or keyword under cursor. 

![Pep Select](docs/Select.gif)

It behaves like an 'intelligent multi cursor, and you can use it to rename symbols.

## Goto Definition

Goto definition of a local binding, var, spec, re-frame handler.

## Settings

### Default settings

```jsonc
{
    "debug": false,

    "clj_kondo_path": "clj-kondo",

    "analysis_applicable_to": ["Packages/Clojure/Clojure.sublime-syntax",
                               "Packages/Clojure/ClojureScript.sublime-syntax",
                               "Packages/Tutkain/EDN (Tutkain).sublime-syntax",
                               "Packages/Tutkain/Clojure (Tutkain).sublime-syntax",
                               "Packages/Tutkain/ClojureScript (Tutkain).sublime-syntax",
                               "Packages/Tutkain/Clojure Common (Tutkain).sublime-syntax",
                               "Packages/Tutkain/Babashka (Tutkain).sublime-syntax",
                               "Packages/Clojure Sublimed/Clojure (Sublimed).sublime-syntax"],

    // Number of seconds to delay the analysis after a view is modified.
    "analysis_delay": 0.6,

    // It's unlikely to need to analyze scratch views,
    // but you can run the command to analyze a view if you need it.
    "analyze_scratch_view": false,

    // True if you would like to analyse your project's sources when the plugin is loaded.
    // (Doesn't do anything if there isn't a *.sublime-project file.)
    "analyze_paths_on_plugin_loaded": true,

    // True if you would like to analyze your project's sources when the project is loaded.
    // (Doesn't do anything if there isn't a *.sublime-project file.)
    "analyze_paths_on_load_project": true,

    // True if you would like to analyse your project's classpath when the plugin is loaded.
    // (Doesn't do anything if there isn't a *.sublime-project file.)
    "analyze_classpath_on_plugin_loaded": true,

    // True if you would like to analyze your project's classpath when the project is loaded.
    // (Doesn't do anything if there isn't a *.sublime-project file.)
    "analyze_classpath_on_load_project": true,

    // True if warnings/errors should be displayed right after the analysis is completed.
    // It's a 'tighter feedback loop' to display warnings/errors after the analysis, but some might find it distracting.
    "annotate_view_after_analysis": false,

    // True if warnings/errors should be displayed only when a view is saved.
    "annotate_view_on_save": false,

    // The font-size used by view analysis annotations.
    "annotation_font_size": "0.9em",

    // True if you would like to see the number of clj-kondo errors, if any, in the status bar.
    "view_status_show_errors": false,

    // True if you would like to see the number of clj-kondo warnings, if any, in the status bar.
    "view_status_show_warnings": false,

    // True if you would like to see the number of highlighted regions in the status bar.
    "view_status_show_highlighted": false,

    // If you would like to add a custom prefix to the number of highlighted regions in the status bar.
    "view_status_show_highlighted_prefix": "Highlighted: ",

    // If you would like to add a custom suffix to the number of highlighted regions in the status bar.
    "view_status_show_highlighted_suffix": "",

    // True if you would like to highlight vars, local bindings and keywords usages.
    "automatically_highlight": false,

    // True if you would like to highlight the region under the cursor.
    "highlight_self": true,

    // True if you would like to highlight the region with an outline.
    "highlight_region": true,

    // True if you would like to highlight the gutter.
    "highlight_gutter": false,
}
```

#### Recommended settings

```jsonc
{
    // True if warnings/errors should be displayed right after the analysis is completed.
    "annotate_view_after_analysis": true,

    // True if you would like to see the number of clj-kondo errors, if any, in the status bar.
    "view_status_show_errors": true,

    // True if you would like to see the number of clj-kondo warnings, if any, in the status bar.
    "view_status_show_warnings": true,

    // True if you would like to highlight vars, local bindings and keywords usages.
    "automatically_highlight": true
}
```

## Sublime Project

To analyse your project's classpath and paths (your files), you need to configure Pep in your Sublime Project.

If you configure `paths`, you can go to definition, show documentation and find usages across files in your project.
A paths analysis usually doesn't take long and will run when Pep is loaded or a project is loaded - see **Settings** `"analyze_paths"`.

If you configure `classpath`, you can go to definition and show documentation of vars defined in libraries.
Classpath analysis takes a little longer and will run when Pep is loaded, or a project is loaded - see **Settings** `"analyze_classpath"`.

Sublime Project example:

```json
{
    "pep": {
        "paths": ["src"],
        "classpath": "clojure -Spath"
    }
}
```


## Acknowledgements

- Eero and [Tutkain](https://github.com/eerohele/Tutkain); without Eero and Tutkain, I would not have started this project.
- Michiel Borkent and [clj-kondo](https://github.com/clj-kondo/clj-kondo); this project wouldn't be possible without clj-kondo.
- Peter and [Calva](https://calva.io/); Peter was too kind and allowed me to contribute to Calva in the early days and showed me how fun it is to work on these things.
- The Sublime Text Discord community, a magnificent bunch of volunteers and Sublime HQ employees tirelessly helping people with questions related to Sublime Text. (Copied from Tutkain because I could not say it better.)
