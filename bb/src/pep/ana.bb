(ns pep.ana)

(defn filename->analysis
  "Returns a mapping of filename to its analysis data."
  [analysis]
  (let [;; Map different analysis data eg. locals, keywords to a vector.
        xform (mapcat
                (fn [[sem data]]
                  (into [] (map #(assoc % :_sem sem)) data)))]
    (group-by :filename (into [] xform analysis))))


(comment

  ;; cat /Users/pedro/Library/Application\ Support/Sublime\ Text/Packages/Pep/bb/src/pep/sublime.bb | bb -x pep.sublime/analyze-stdin! | pbcopy

  (require '[babashka.fs :as fs])

  fs/file-separator
  fs/path-separator
  fs/temp-dir


  (require '[clojure.string :as str])
  (str/replace "/private/var/folders/33/kv329l5x2nbglsc_2f2z6pw40000gn/T/pep1341669416854084134.bb" fs/file-separator "_")

  (let [{:keys [analysis]} (with-in-str (slurp "src/pep/sublime.bb") (lint-stdin!))]
    (filename->analysis analysis))

  )
