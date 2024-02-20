(ns pep.ana
  (:require
   [clojure.string :as str]
   [clojure.tools.deps :as deps]
   [clojure.data.json :as json]

   [babashka.fs :as fs]
   [babashka.process :refer [shell]]
   [clj-kondo.core :as clj-kondo]))

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

(defn dbdir [dbname]
  (fs/file (fs/temp-dir) "pep" "db" dbname))

(defn dbfilename [filename]
  (str
    (str/join "_"
      (into []
        (remove str/blank?)
        (str/split filename (re-pattern fs/file-separator))))
    ".json"))

(defn dbsave! [dbname {:keys [analysis]}]
  (when-not (fs/exists? (dbdir dbname))
    (fs/create-dir (dbdir dbname)))

  (reduce
    (fn [F [filename analysis]]
      (let [f (fs/file (dbdir dbname) (dbfilename filename))]
        (spit f (json/write-str analysis))

        (conj F f)))
    #{}
    (filename->analysis analysis)))

(defn- dbc
  "Executes DuckDB command."
  [command]
  (shell
    {:out :string
     :err :string
     :continue true}
    "duckdb"
    "-json"
    "-c" (str "INSTALL json; LOAD json; " command)))

(defn- dbq
  "Query DuckDB."
  [query]
  (let [{:keys [cmd out err]} (dbc query)]
    (if (str/blank? err)
      out
      (throw (ex-info err {:cmd cmd})))))

(comment

  (dbsave! "pep"
    (clj-kondo/run!
      {:config lint-config
       :lint
       ["src/pep/ana.bb"
        "src/pep/sublime.bb"]}))


  (dbsave! "rex.system"
    (clj-kondo/run!
      {:lint ["/Users/pedro/Developer/Velos/rex.system/rex.ingestion/src/rex/ingestion.clj"]
       :config lint-config}))

  (dbq
    "SELECT name FROM '/Users/pedro/Downloads/ingestion.clj.json' WHERE _sem = 'var-definitions'")


  (let [deps-file (fs/file "/Users/pedro/Developer/Velos/rex.system/rex.ingestion/deps.edn")
        deps-map (deps/slurp-deps deps-file)

        {:keys [classpath-roots]} (deps/create-basis {:projet deps-map})]
    (dbsave! "rex.system"
      (clj-kondo/run!
        {:lint classpath-roots
         :config lint-config})))


  (require '[clojure.pprint :as pprint])

  (pprint/print-table
    (json/read-str
      (dbq
        "SELECT
       ns, name, filename
     FROM
       '/var/folders/33/kv329l5x2nbglsc_2f2z6pw40000gn/T/pep/db/rex.system/*.json'
     WHERE
      _sem = 'var-definitions'
      AND ns = 'clojure.core'")))


  )
