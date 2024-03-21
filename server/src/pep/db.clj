(ns pep.db
  (:require
   [clojure.java.io :as io]

   [next.jdbc :as jdbc]))

(set! *warn-on-reflection* true)

(defn cache-dir
  ^java.io.File [root-path]
  (io/file root-path ".pep"))

(defn filename-hash
  [filename]
  (hash filename))

(defn conn ^java.sql.Connection []
  (doto
    (jdbc/get-connection "jdbc:duckdb:")
    (jdbc/execute! ["INSTALL json; LOAD json;"])))

(defn select-namespace-definitions
  [conn dir]
  (let [sql "SELECT
                  _semantic,
                  name,
                  doc,
                  filename,
                  row,
                  \"end-row\",
                  col,
                  \"end-col\",
                  \"name-row\",
                  \"name-end-row\",
                  \"name-col\",
                  \"name-end-col\"
              FROM
                  read_json_auto('%s', format='array')
              WHERE
                  _semantic = 'namespace-definitions'
              ORDER BY
                  name"

        sql (format sql (io/file dir "*.json"))]

    (jdbc/execute! conn [sql])))

(defn select-row
  [conn dir {:keys [filename row]}]
  (let [;; It's fine to 'select *' because we're looking at a single file.
        sql "SELECT
                *
             FROM
                 read_json_auto('%s', format='array')
             WHERE
                 \"name-row\" = ?
                 OR row = ?"

        filename-json (str (filename-hash filename) ".json")
        filename-file (io/file dir filename-json)

        sql (format sql filename-file)]

    (jdbc/execute! conn [sql row row])))

(defmulti select-definitions-sqlparams
  "Returns SQL & params to query definitions per semantic."
  (fn [_dir prospect]
    (:_semantic prospect)))

(defmethod select-definitions-sqlparams "locals"
  [dir {prospect-filename :filename
        prospect-id :id}]
  (let [sql "SELECT
                 _semantic, name, filename, row, col
              FROM
                 read_json_auto('%s', format='array')
              WHERE
                 _semantic = 'locals'
                 AND id = ?"

        filename-json (str (filename-hash prospect-filename) ".json")
        filename-file (io/file dir filename-json)

        sql (format sql filename-file)]

    [sql prospect-id]))

(defmethod select-definitions-sqlparams "local-usages"
  [dir {prospect-filename :filename
        prospect-id :id}]
  (let [sql "SELECT
                 _semantic, name, filename, row, col
              FROM
                 read_json_auto('%s', format='array')
              WHERE
                 _semantic = 'locals'
                 AND id = ?"

        filename-json (str (filename-hash prospect-filename) ".json")
        filename-file (io/file dir filename-json)

        sql (format sql filename-file)]

    [sql prospect-id]))

(defmethod select-definitions-sqlparams "namespace-definitions"
  [dir {prospect-name :name}]
  (let [sql "SELECT
                 _semantic, filename, name, row, col, \"name-row\", \"name-col\"
              FROM
                 read_json_auto('%s', format='array')
              WHERE
                 _semantic = 'namespace-definitions'
                 AND name = ?"

        sql (format sql (io/file dir "*.json"))]

    [sql prospect-name]))

(defmethod select-definitions-sqlparams "namespace-usages"
  [dir {prospect-to :to}]
  (let [sql "SELECT
                 _semantic, filename, name, row, col, \"name-row\", \"name-col\"
              FROM
                 read_json_auto('%s', format='array')
              WHERE
                 _semantic = 'namespace-definitions'
                 AND name = ?"

        sql (format sql (io/file dir "*.json"))]

    [sql prospect-to]))

(defmethod select-definitions-sqlparams "var-definitions"
  [dir {prospect-ns :ns
        prospect-name :name}]
  (let [sql "SELECT
                 _semantic,
                  ns,
                  name,
                  doc,
                  filename,
                  row,
                  col,
                  \"name-row\",
                  \"name-end-row\",
                  \"name-col\",
                  \"name-end-col\"
              FROM
                 read_json_auto('%s', format='array')
              WHERE
                 _semantic = 'var-definitions'
                 AND ns = ?
                 AND name = ?"

        sql (format sql (io/file dir "*.json"))]

    [sql prospect-ns prospect-name]))

(defmethod select-definitions-sqlparams "var-usages"
  [dir {prospect-to :to
        prospect-name :name}]
  (let [sql "SELECT
                 _semantic,
                  ns,
                  name,
                  doc,
                  filename,
                  row,
                  col,
                  \"name-row\",
                  \"name-end-row\",
                  \"name-col\",
                  \"name-end-col\"
              FROM
                 read_json_auto('%s', format='array')
              WHERE
                 _semantic = 'var-definitions'
                 AND ns = ?
                 AND name = ?"

        sql (format sql (io/file dir "*.json"))]

    [sql prospect-to prospect-name]))

(defn select-definitions
  [conn dir prospect]
  (let [sqlparams (select-definitions-sqlparams dir prospect)]
    (jdbc/execute! conn sqlparams)))


(comment

  (io/file (cache-dir (System/getProperty "user.dir")) "*.json")

  )
