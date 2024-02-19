(ns pep.sublime
  (:require
   [clojure.pprint :as pprint]
   [pod.borkdude.clj-kondo :as clj-kondo]))

(def TT_NAMESPACE_DEFINITION "namespace_definition")
(def TT_NAMESPACE_USAGE "namespace_usage")

(def stdin-lint-config
  {:analysis
   {:var-definitions true
    :var-usages true
    :arglists true
    :locals true
    :keywords true
    :symbols true
    :java-class-definitions false
    :java-class-usages true
    :java-member-definitions false
    :instance-invocations true}

   :output
   {:canonical-paths true}})


(defn namespace-index
  "Index namespace definitions and usages.

  Definitions are indexed by name and file extension.

  Usages are indexed by name.

  Returns a map with keys 'nindex', 'nindex_usages', 'nrn', 'nrn_usages'."
  ([analysis]
   (namespace-index analysis
     {:nindex true
      :nindex_usages true
      :nrn true
      :nrn_usages true}))
  ([analysis {:keys [nindex
                     nindex_usages
                     nrn
                     nrn_usages]}]
   (let [{:keys [namespace-definitions
                 namespace-usages]} analysis

         index1 (reduce
                  (fn [index namespace-definition]
                    (let [namespace-definition (assoc namespace-definition :_semantic TT_NAMESPACE_DEFINITION)

                          index (if nindex
                                  (update-in index [:nindex (:name namespace-definition)] (fnil conj []) namespace-definition)
                                  index)

                          index (if nrn
                                  (update-in index [:nrn (:name-row namespace-definition)] (fnil conj []) namespace-definition)
                                  index)]
                      index))
                  {:nindex {}
                   :nrn {}}
                  namespace-definitions)

         index2 (reduce
                  (fn [index namespace-usage]
                    (let [namespace-usage (assoc namespace-usage :_semantic TT_NAMESPACE_USAGE)

                          index (if nindex_usages
                                  (update-in index [:nindex_usages (:to namespace-usage)] (fnil conj []) namespace-usage)
                                  index)

                          index (if nrn_usages
                                  (let [index (update-in index [:nrn_usages (:name-row namespace-usage)] (fnil conj []) namespace-usage)]
                                    (if-let [alias-row (:alias-row namespace-usage)]
                                      (update-in index [:nrn_usages alias-row] (fnil conj []) namespace-usage)
                                      index))
                                  index)]
                      index))
                  {:nindex_usages {}
                   :nrn_usages {}}
                  namespace-usages)]

     (merge index1 index2))))

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
    (pprint/pprint
      (namespace-index (:analysis result)))))


;; cat /Users/pedro/Library/Application\ Support/Sublime\ Text/Packages/Pep/bb/src/pep/sublime.clj | bb -x pep.sublime/analyze-stdin! | pbcopy
