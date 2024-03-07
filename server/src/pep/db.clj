(ns pep.db
  (:require
   [clojure.java.io :as io]

   [next.jdbc :as jdbc]))

(set! *warn-on-reflection* true)

(defn cache-dir ^java.io.File [root-path]
  (io/file root-path ".pep"))

(defn conn ^java.sql.Connection []
  (doto
    (jdbc/get-connection "jdbc:duckdb:")
    (jdbc/execute! ["INSTALL json; LOAD json;"])))

(defn select-namespace-definitions
  [conn root-path]
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

        sql (format sql (io/file (cache-dir root-path) "*.json"))]

    (jdbc/execute! conn [sql])))

(defn select-row
  [conn root-path {:keys [filename row]}]
  (let [sql "SELECT
                 *
             FROM
                 read_json_auto('%s', format='array')
             WHERE
                 filename = ?
                 AND (\"name-row\" = ? OR row = ?)"

        sql (format sql (io/file (cache-dir root-path) "*.json"))]

    (jdbc/execute! conn [sql filename row row])))

(comment

  (io/file (cache-dir (System/getProperty "user.dir")) "*.json")

  )
