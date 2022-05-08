(ns pep.core
  (:require
   [quickdoc.api :as quickdoc]))

(defn quickdoc [{:keys [input output]}]
  (quickdoc/quickdoc
    {:source-paths [input]
     :outfile output}))


(comment

  (quickdoc
    {:input "/Users/pedro/Library/Application Support/Sublime Text/Packages/Pep/clojure/src/pep/core.clj"
     :output "API.md"})


  )
