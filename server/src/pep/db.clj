(ns pep.db
  (:require
   [clojure.java.io :as io]

   [next.jdbc :as jdbc]
   [next.jdbc.result-set :as rs]))

(set! *warn-on-reflection* true)

;; Reference:
;; https://cljdoc.org/d/com.github.seancorfield/next.jdbc/1.3.925/doc/getting-started/result-set-builders#readablecolumn
(extend-protocol rs/ReadableColumn
  org.duckdb.DuckDBArray
  (read-column-by-label [^org.duckdb.DuckDBArray o]
    (vec (.getArray o)))

  (read-column-by-index [^org.duckdb.DuckDBArray o _2 _3]
    (vec (.getArray o))))

(defn cache-dir
  ^java.io.File [root-path]
  (io/file root-path ".pep"))

(defn filename-cache-hash
  "Returns a hash for filename that will be used in cache."
  [filename]
  (hash filename))

(defn filename-cache
  "Returns filename as used in cache.

  Filenames in the cache directory are hashed and added a .json extension."
  [filename]
  (str (filename-cache-hash filename) ".json"))

(defn cache-json-file
  ^java.io.File [root-path filename]
  (io/file (cache-dir root-path) (filename-cache filename)))

(defn cache-*json-file
  ^java.io.File [root-path]
  (io/file (cache-dir root-path) "*.json"))

(defn locs [prospect]
  (into []
    (comp
      (map
        (fn [[start end]]
          [(get prospect start) (get prospect end)]))
      (filter
        (fn [[start end]]
          (and start end))))
    (cond
      (#{"locals"
         "local-usages"
         "keywords"} (:_semantic prospect))
      [[:col :end-col]]

      (#{"namespace-definitions"
         "var-definitions"
         "var-usages"} (:_semantic prospect))
      [[:name-col :name-end-col]]

      (#{"namespace-usages"} (:_semantic prospect))
      [[:name-col :name-end-col]
       [:alias-col :alias-end-col]])))

(defn conn ^java.sql.Connection []
  (doto
    (jdbc/get-connection "jdbc:duckdb:")
    (jdbc/execute! ["INSTALL json; LOAD json;"])))

(defn select-namespaces
  [conn json]
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

        sql (format sql json)]

    (jdbc/execute! conn [sql])))

(defn select-row
  [conn json {:keys [row]}]
  (let [;; It's fine to 'select *' because we're looking at a single file.
        ;; (`json` is specific for a single file instead of *.json)
        sql "SELECT
                *
             FROM
                 read_json_auto('%s', format='array')
             WHERE
                 %s"

        r1 (try
             (jdbc/execute! conn [(format sql json "\"row\" = ?") row])
             (catch Exception _
               []))

        r2 (try
             (jdbc/execute! conn [(format sql json "\"name-row\" = ?") row])
             (catch Exception _
               []))

        r3 (try
             (jdbc/execute! conn [(format sql json "\"alias-row\" = ?") row])
             (catch Exception _
               []))]

    (into #{} cat [r1 r2 r3])))

(defn select-under-caret
  [conn json {:keys [filename row col]}]
  (reduce
    (fn [acc data]
      (if (some
            (fn [[start end]]
              (<= start col end))
            (locs data))
        (conj acc data)
        acc))
    #{}
    (select-row conn json {:row row})))

(defn select-var-definitions-sqlparams
  [json {var-ns :ns var-name :name}]
  (let [sql "SELECT
                 _semantic,
                  ns,
                  name,
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

        sql (format sql json)]

    [sql var-ns var-name]))

(defn select-var-definitions
  [conn json {var-ns :ns
              var-name :name}]
  (jdbc/execute! conn
    (select-var-definitions-sqlparams json
      {:ns var-ns
       :name var-name})))

(defn select-var-usages-sqlparams
  [json {var-ns :ns var-name :name}]
  (let [sql "SELECT
               \"_semantic\",
                \"from\",
                \"to\",
                \"name\",
                \"filename\",
                \"row\",
                \"col\",
                \"name-row\",
                \"name-end-row\",
                \"name-col\",
                \"name-end-col\"
            FROM
               read_json_auto('%s', format='array')
            WHERE
               \"_semantic\" = 'var-usages'
               AND \"to\" = ?
               AND \"name\" = ?"

        sql (format sql json)]

    [sql var-ns var-name]))

(defn select-var-usages
  [conn json {var-ns :ns
              var-name :name}]
  (jdbc/execute! conn
    (select-var-usages-sqlparams json
      {:ns var-ns
       :name var-name})))


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

        filename-json (filename-cache prospect-filename)
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

        filename-json (filename-cache prospect-filename)
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
  (let [filename (io/file dir "*.json")]
    (select-var-definitions-sqlparams filename
      {:ns prospect-ns
       :name prospect-name})))

(defmethod select-definitions-sqlparams "var-usages"
  [dir {prospect-to :to
        prospect-name :name}]
  (let [filename (io/file dir "*.json")]
    (select-var-definitions-sqlparams filename
      {:ns prospect-to
       :name prospect-name})))

(defn select-definitions
  [conn dir prospect]
  (let [sqlparams (select-definitions-sqlparams dir prospect)]
    (jdbc/execute! conn sqlparams)))


;; -- References

(defn select-local-references
  "Select `locals` and `local-usages` by ID."
  [conn json {local-id :id}]
  (let [sql "SELECT
                \"_semantic\",
                \"name\",
                \"filename\",
                \"row\",
                \"end-row\",
                \"col\",
                \"end-col\"
              FROM
                 read_json_auto('%s', format='array')
              WHERE
                 \"id\" = ?"

        sql (format sql json)]

    (jdbc/execute! conn [sql local-id])))

(defn select-keyword-references
  "Select `keywords` by namespace and name."
  [conn json {keyword-ns :ns
              keyword-name :name}]
  (let [sql "SELECT
                 \"_semantic\",
                  \"ns\",
                  \"name\",
                  \"filename\",
                  \"row\",
                  \"end-row\",
                  \"col\",
                  \"end-col\"
              FROM
                 read_json_auto('%s', format='array')
              WHERE
                \"_semantic\" = 'keywords'
                 %s"]
    (cond
      keyword-ns
      (jdbc/execute! conn
        [(format sql json "AND \"ns\" = ? AND \"name\" = ?")
         keyword-ns
         keyword-name])

      :else
      (jdbc/execute! conn
        [(format sql json "AND \"name\" = ?")
         keyword-name]))))

(defn select-var-references
  "Select `var-definitions` and `var-usages` by namespace and name."
  [conn json {var-ns :ns
              var-name :name}]
  (let [definitions (select-var-definitions conn json
                      {:ns var-ns
                       :name var-name})

        usages (select-var-usages conn json
                 {:ns var-ns
                  :name var-name})]

    (into [] cat [definitions usages])))

(defmulti select-references
  (fn [_conn _json prospect]
    (:_semantic prospect)))

(defmethod select-references "keywords"
  [conn json {keyword-ns :ns
              keyword-name :name}]
  (select-keyword-references conn json
    {:ns keyword-ns
     :name keyword-name}))

(defmethod select-references "locals"
  [conn json {local-id :id}]
  (select-local-references conn json {:id local-id}))

(defmethod select-references "local-usages"
  [conn json {local-id :id}]
  (select-local-references conn json {:id local-id}))

(defmethod select-references "var-definitions"
  [conn json {var-ns :ns
              var-name :name}]
  (select-var-references conn json
    {:ns var-ns
     :name var-name}))

(defmethod select-references "var-usages"
  [conn json {var-ns :to
              var-name :name}]
  (select-var-references conn json
    {:ns var-ns
     :name var-name}))


(comment

  (io/file (cache-dir (System/getProperty "user.dir")) "*.json")

  )
