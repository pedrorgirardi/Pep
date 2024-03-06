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

(defn at-row [conn {:keys [root-path filename name-row]}]
  (let [sql "SELECT
              \"_semantic\",
              \"name\",
		      \"filename\",

              \"row\",
              \"end-row\",
              \"col\",
              \"end-col\",

              \"name-row\",
              \"name-end-row\",
              \"name-col\",
              \"name-end-col\",

              \"alias-row\",
              \"alias-end-row\",
              \"alias-col\",
              \"alias-end-col\"

            FROM
              '%s'

            WHERE
              \"filename\" = ?
              AND \"name-row\" = ?"

        sql (format sql (io/file (cache-dir root-path) "*.json"))]

    (jdbc/execute! conn [sql filename name-row])))

(comment

  (io/file (cache-dir (System/getProperty "user.dir")) "*.json")

  )
