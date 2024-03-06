(ns pep.handler
  (:require
   [clojure.java.io :as io]
   [clojure.data.json :as json]

   [next.jdbc :as jdbc]

   [pep.ana :as ana]))

(defmulti handle
  "Multimethod to handle client requests.

  Dispatched by `:op`.

  Returns a map with either `:success` or `:error`."
  :op)

(defmethod handle :default
  [_]
  {:success "nop"})

(defmethod handle "error"
  [_]
  (throw (ex-info "Bad handler." {:foo :bar})))

(defmethod handle "diagnostics"
  [{:keys [root-path]}]
  {:success (ana/diagnostics root-path)})

(defmethod handle "analyze"
  [{:keys [root-path]}]
  (let [{:keys [summary analysis]} (ana/analyze-paths! root-path)

        index (ana/index analysis)]

    (when-not (.exists (io/file root-path ".pep"))
      (.mkdir (io/file root-path ".pep")))

    (doseq [[filename analysis] index]
      (let [f (io/file root-path ".pep" (format "%s.json" (hash filename)))]
        (spit f (json/write-str analysis))))

    {:success {:summary summary}}))

(defmethod handle "namespace-definitions"
  [{:keys [root-path]}]
  (let [query "SELECT
                  \"_semantic\",
                  \"name\",
                  \"row\",
                  \"end-row\",
                  \"col\",
                  \"end-col\",
                  \"filename\"
                FROM
                  '%s'
                WHERE
                  _semantic = 'namespace-definitions'
                ORDER BY
                  \"name\""

        query (format query (io/file root-path ".pep" "*.json"))

        rows (with-open [db (jdbc/get-connection "jdbc:duckdb:")]
               (jdbc/execute! db ["INSTALL json; LOAD json;"])
               (jdbc/execute! db [query]))]

    {:success rows}))

(comment

  (def root-path (System/getProperty "user.dir"))

  (handle
    {:op "diagnostics"
     :root-path root-path})

  (handle
    {:op "analyze"
     :root-path root-path})

  (handle
    {:op "namespace-definitions"
     :root-path root-path})

  )
