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

        filename-hash (hash filename)
        filename-json (str filename-hash ".json")
        filename-file (io/file dir filename-json)

        sql (format sql filename-file)]

    (jdbc/execute! conn [sql row row])))

(defn select-definitions
  [conn dir prospect]
  (let [{prospect-semantic :_semantic
         prospect-to :to
         prospect-name :name
         prospect-id :id} prospect

        [sql & params] (case prospect-semantic
                         "local-usages"
                         ["SELECT
                               _semantic, name, filename, row, col
                            FROM
                               read_json_auto('%s', format='array')
                            WHERE
                               _semantic = 'locals'
                               AND id = ?"
                          prospect-id]

                         "namespace-usages"
                         ["SELECT
                               _semantic, filename, name, row, col
                            FROM
                               read_json_auto('%s', format='array')
                            WHERE
                               _semantic = 'namespace-definitions'
                               AND name = ?"
                          prospect-to]

                         "var-usages"
                         ["SELECT
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
                          prospect-to prospect-name])

        sql (format sql (io/file dir "*.json"))

        sqlparams (into [sql] params)]

    (jdbc/execute! conn sqlparams)))

(comment

  (io/file (cache-dir (System/getProperty "user.dir")) "*.json")

  )
