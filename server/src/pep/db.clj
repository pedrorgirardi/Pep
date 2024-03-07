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

(defn find-row
  [conn root-path {:keys [filename row]}]
  (let [sql "SELECT
               *

             FROM
               '%s'

             WHERE
               filename = ?
               AND (\"name-row\" = ? OR row = ?)"

        sql (format sql (io/file (cache-dir root-path) "*.json"))]

    (jdbc/execute! conn [sql filename row row])))

(comment

  (io/file (cache-dir (System/getProperty "user.dir")) "*.json")

  )
