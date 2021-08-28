# Pep

Status: in development

Pep is fundamentally a clj-kondo client for Sublime Text. It leverages clj-kondo analysis data to provide code navigation, documentation and usages analysis.

clj-kondo is the sole dependency, and everything else is supplied by built-in Sublime Text APIs.

## Highlight

Highlight symbol or keyword under cursor and its usages.

![Pep Highlight](docs/Highlight.png)

## Documentation

Show documentation.

![Pep Show documentation](docs/Documentation.png)

## Jump

Jump to occurrences of symbol under cursor. 

![Pep Jump](docs/Jump.gif)

It works for locals, vars and keywords.

## Select

Select occurrences of symbol under cursor. 

![Pep Select](docs/Select.gif)

It works for locals, vars and keywords.

It behaves like a 'smart multi-cursor' and you can use it to rename symbols.

## Goto Definition

Goto definition of local or var.

## Settings

```json
{
    "debug": false,

    "analyze_view": ["on_activated_async", "on_post_save_async"],

    "analyze_paths": ["plugin_loaded", "on_load_project_async", "on_post_save_async"],

    "analyze_classpath": ["plugin_loaded", "on_load_project_async"],

    "automatically_highlight": false
}
```

## Sublime Project

To analyze your project's classpath and paths (your own files), you need to configure Pep in your Sublime Project.

If you configure `paths`, you will be able to go to definition, show documentation and find usages of Vars in your project.
A paths analysis usually doesn't take long and it will run whenever you save a file - see **Settings** `"analyze_paths"`.

If you configure `classpath`, you will be able to go to definition and show documentation of Vars defined in libraries.
Classpath analysis does take a little longer and it doesn't run automatically, you need to invoke a command (`pg_pep_analyze_classpath`).

```json
{
    "pep": {
        "classpath": ["clojure", "-Spath"],
        
        "paths": ["src"]
    }
}
```


## Acknowledgements

- Eero and [Tutkain](https://github.com/eerohele/Tutkain); without Eero and Tutkain I would have not started this project.
- Michiel Borkent and [clj-kondo](https://github.com/clj-kondo/clj-kondo); because this project wouldn't be possible without clj-kondo.
- Peter and [Calva](https://calva.io/); Peter was too kind and allowed me to contribute to Calva on the early days and showed me how fun it is to work on these things.
- The Sublime Text Discord community; a magnificent bunch of volunteers and Sublime HQ employees tirelessly helping people with questions related to Sublime Text. (Copied from Tutkain because I could not say it better.)
