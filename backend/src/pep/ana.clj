(ns pep.ana
  (:require
   [clojure.string :as str]
   [clojure.data.json :as json]

   [babashka.fs :as fs]
   [babashka.process :refer [shell]]))

(defn filename->analysis
  "Returns a mapping of filename to its analysis data."
  [analysis]
  (let [;; Map different analysis data eg. locals, keywords to a vector.
        xform (mapcat
                (fn [[sem data]]
                  (into [] (map #(assoc % :_sem sem)) data)))]
    (group-by :filename (into [] xform analysis))))

(defn dbdir [project_base_name]
  (fs/file (fs/temp-dir) "pep" "db" project_base_name))

(defn dbfilename [filename]
  (format "%s.json" (hash filename)))

(defn dbsave! [project_base_name {:keys [analysis]}]
  (when-not (fs/exists? (dbdir project_base_name))
    (fs/create-dir (dbdir project_base_name)))

  (reduce
    (fn [F [filename analysis]]
      (let [f (fs/file (dbdir project_base_name) (dbfilename filename))]
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

  (require '[clojure.pprint :as pprint])

  (def q
    "SELECT
       ns, name, filename
     FROM
       '/var/folders/33/kv329l5x2nbglsc_2f2z6pw40000gn/T/pep/db/rex.system/*.json'
     WHERE
      _sem = 'var-definitions'
      AND ns = 'clojure.set'
      AND filename like '%.clj'")

  (time (pprint/print-table (json/read-str (dbq q))))
  ;; Elapsed time: 881.967916 msecs

  (time (dbq q))
  ;; Elapsed time: 881.24075 msecs

  (require '[next.jdbc :as jdbc])

  (defn in-memory-db
    "Retorna uma conexão para um banco de dados em memória.

  https://duckdb.org/docs/api/java"
  ^org.duckdb.DuckDBConnection []
  (jdbc/get-connection "jdbc:duckdb:"))


  (with-open [db (in-memory-db)]
    (jdbc/execute! db ["INSTALL json; LOAD json;"])
    (jdbc/execute! db [q]))
  ;; Elapsed time: 210.58975 msecs


  )
