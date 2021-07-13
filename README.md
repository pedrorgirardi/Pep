# Pep

## Commands

`pg_pep_goto_definition`
- Status: stable

`pg_pep_navigate`
- Status: in development

`pg_pep_find_usages`
- Status: stable

`pg_pep_find_usages_in_project`
- Status: stable

`pg_pep_show_doc`
- Status: stable

`pg_pep_select`
- Status: stable

`pg_pep_report`
- Status: in development

`pg_pep_annotate`
- Status: in development

`pg_pep_analyze_view`
- Status: stable

`pg_pep_analyze_paths`
- Status: stable

`pg_pep_analyze_classpath`
- Status: stable

## Settings

```json
{
    "debug": false,

    "analyze_view": ["on_activated_async", "on_post_save_async"],

    "analyze_paths": ["on_post_save_async"],

    "automatically_highlight": false
}
```

## Sublime Project

To analyze your project's classpath and paths (your own files), you need to configure Pep in your Sublime Project.

If you configure `paths`, you will be able go to definition, show documentation and find usages of Vars in your project.
A paths analysis usually doesn't take long and it will run behind the scenes whenever you save a file - see **Settings** `"analyze_paths"`.

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
- The Sublime Text Discord community; a magnificent bunch of volunteers and Sublime HQ employees tirelessly helping people with questions related to Sublime Text. (Copied from Tutkain because I could not say it better.)
