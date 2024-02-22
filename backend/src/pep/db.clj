(ns pep.db
  (:require
   [clojure.string :as str]
   [clojure.data.json :as json]

   [next.jdbc :as jdbc]
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

(defn query [sqlparams]
  (with-open [db (jdbc/get-connection "jdbc:duckdb:")]
    (jdbc/execute! db ["INSTALL json; LOAD json;"])
    (jdbc/execute! db sqlparams)))

(comment

  (def q
    "SELECT
       ns, name, filename
     FROM
       '/var/folders/33/kv329l5x2nbglsc_2f2z6pw40000gn/T/pep/db/data90/*.json'
     WHERE
      _sem = 'var-definitions'
      AND filename like '%.clj'")

  (time (dbq q))
  ;; Elapsed time: 68.789125 msecs


  (time (query [q]))
  ;; Elapsed time: 45.964917 msecs


  )
