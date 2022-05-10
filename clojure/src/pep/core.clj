(ns pep.core
  (:require
   [quickdoc.api :as quickdoc]
   [markdown.core :as md]))

(defn quickdoc [{:keys [filepath]}]
  (let [{:keys [markdown]} (quickdoc/quickdoc
                             {:source-paths [filepath]
                              :outfile false})]
    (md/md-to-html-string markdown)))


(comment

  (quickdoc
    {:filepath "/Users/pedro/Library/Application Support/Sublime Text/Packages/Pep/clojure/src/pep/core.clj"})


  )
