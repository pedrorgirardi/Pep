(ns pep.ana
  (:require
   [clojure.string :as str]

   [babashka.fs :as fs]
   [pod.borkdude.clj-kondo :as clj-kondo]
   [cheshire.core :as json]))

(def lint-config
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

(defn lint-stdin!
  ([]
   (lint-stdin! {:config lint-config}))
  ([{:keys [config]}]
   (try
     (let [f (doto
               (java.io.File/createTempFile "pep_" ".clj")
               (spit (slurp *in*)))

           result (clj-kondo/run!
                    {:lint [(.getPath f)]
                     :config config})]

       (try
         (.delete f)
         (catch Exception _
           nil))

       result)
     (catch Exception _
       ;; TODO: Logging

       nil))))

(defn filename->analysis
  "Returns a mapping of filename to its analysis data."
  [analysis]
  (let [;; Map different analysis data eg. locals, keywords to a vector.
        xform (mapcat
                (fn [[sem data]]
                  (into [] (map #(assoc % :_sem sem)) data)))]
    (group-by :filename (into [] xform analysis))))

(defn dbdir []
  (fs/file (fs/temp-dir) "pep"))

(defn dbfilename [filename]
  (str
    (str/join "_"
      (into []
        (remove str/blank?)
        (str/split filename (re-pattern fs/file-separator))))
    ".json"))

(defn dbfile [filename]
  (fs/file (dbdir) (dbfilename filename)))

(defn persist! [{:keys [analysis]}]
  (when-not (fs/exists? (dbdir))
    (fs/create-dir (dbdir)))

  (doseq [[filename analysis] (filename->analysis analysis)]
    (spit (dbfile filename) (json/generate-string analysis))))

(comment

  (persist!
    (clj-kondo/run!
      {:lint ["src/pep/ana.bb"]
       :config lint-config}))


  (persist!
    (clj-kondo/run!
      {:lint ["/Users/pedro/Developer/Velos/rex.system/rex.ingestion/src/rex/ingestion.clj"]
       :config lint-config}))



  )
