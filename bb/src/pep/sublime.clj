(ns pep.sublime
  (:require
   [clojure.pprint :as pprint]
   [pod.borkdude.clj-kondo :as clj-kondo]))

(def stdin-lint-config
  {:analysis
   {:arglists true
    :locals true
    :keywords true
    :java-class-usages true}

   :output
   {:canonical-paths true}})

(defn lint-stdin!
  ([]
   (lint-stdin!
     {:filename "?"
      :config stdin-lint-config}))
  ([{:keys [filename config]}]
   (try
     (let [f (doto
               (java.io.File/createTempFile "pep" ".clj")
               (spit (slurp *in*)))

           result (clj-kondo/run!
                 {:lint [(.getPath f)]
                  :filename filename
                  :config config})]

       (try
         (.delete f)
         (catch Exception _
           nil))

       result)
     (catch Exception _
       ;; TODO: Logging

       nil))))

(defn analyze-stdin!
  [{:keys [filename]}]
  (when-let [result (lint-stdin!
                      {:filename filename
                       :config stdin-lint-config})]
    (pprint/pprint result)))


;; cat /Users/pedro/Library/Application\ Support/Sublime\ Text/Packages/Pep/bb/src/pep/sublime.clj | bb -x pep.sublime/analyze-stdin! | pbcopy
