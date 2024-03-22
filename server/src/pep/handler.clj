(ns pep.handler
  (:require
   [clojure.java.io :as io]
   [clojure.data.json :as json]
   [clojure.pprint :as pprint]

   [next.jdbc :as jdbc]

   [pep.ana :as ana]
   [pep.db :as db]))

(set! *warn-on-reflection* true)

(def xform-kv-not-nillable
  (map
    (fn [m]
      (into {} (remove (comp nil? val)) m))))

(defn persist-analysis!
  [root-path {:keys [analysis]}]
  (let [cache-dir (db/cache-dir root-path)]

    (when-not (.exists cache-dir)
      (.mkdirs cache-dir))

    (doseq [[filename analysis] (ana/index analysis)]
      (let [f (io/file cache-dir (db/filename-cache filename))]
        (spit f (json/write-str analysis))))))

(defn caret
  [conn root-path {:keys [filename row col]}]
  (let [selected-row (db/select-row conn (db/cache-dir root-path)
                       {:filename filename
                        :row row})]
    (reduce
      (fn [_ data]
        (let [start (or (:name-col data) (:col data))
              end (or (:name-end-col data) (:end-col data))]
          (when (<= start col end)
            (reduced data))))
      nil
      selected-row)))

(defn sort-by-filename-row-col
  "Sort by `:filename`, `row` and `col`."
  [coll]
  (sort-by (juxt :filename :row :col) coll))

(defmulti handle
  "Multimethod to handle client requests.

  Dispatched by `:op`.

  Returns a map with either `:success` or `:error`."
  (fn [_context {:keys [op]}]
    op))

(defmethod handle :default
  [_ _]
  {:success "nop"})

(defmethod handle "error"
  [_ _]
  (throw (ex-info "Bad handler." {:foo :bar})))

(defmethod handle "v1/diagnostics"
  [_ {:keys [root-path]}]
  {:success (ana/diagnostics root-path)})

(defmethod handle "v1/analyze_paths"
  [_ {:keys [root-path filename text]}]
  (let [result (ana/analyze-paths! root-path)]

    (persist-analysis! root-path result)

    {:success (ana/diagnostics* result)}))

(defmethod handle "v1/analyze_text"
  [_ {:keys [root-path filename text]}]
  (let [^java.util.Base64$Decoder decoder (java.util.Base64/getDecoder)

        bytes (.decode decoder ^String text)

        result (ana/analyze-text!
                 {:text (String. bytes "UTF-8")
                  :filename (or filename "-")})]

    (persist-analysis! root-path result)

    {:success (ana/diagnostics* result)}))

(defmethod handle "v1/namespaces"
  [{:keys [conn]} {:keys [root-path]}]
  (let [definitions (db/select-namespaces conn (db/cache-*json-file root-path))
        definitions (into #{} definitions)
        definitions (sort-by-filename-row-col definitions)]

    {:success definitions}))

(defmethod handle "v1/find_definitions"
  [{:keys [conn]} {:keys [root-path filename row col]}]
  (if-let [prospect (caret conn root-path
                      {:filename filename
                       :row row
                       :col col})]
    (let [dir (db/cache-dir root-path)

          definitions (db/select-definitions conn dir prospect)
          definitions (into #{} xform-kv-not-nillable definitions)
          definitions (sort-by-filename-row-col definitions)]
      
      {:success definitions})

    ;; Nothing found under caret.
    {:success #{}}))

(defmethod handle "v1/find_references_in_file"
  [{:keys [conn]} {:keys [root-path filename row col]}]
  (if-let [prospect (caret conn root-path
                      {:filename filename
                       :row row
                       :col col})]
    (let [cache-file (db/cache-json-file root-path filename)

          references (db/select-references conn cache-file prospect)
          references (into #{} xform-kv-not-nillable references)
          references (sort-by-filename-row-col references)]

      {:success
       {:references references}})

    ;; Nothing found under caret.
    {:success nil}))

(comment

  @(def root-path (.getParent (io/file (System/getProperty "user.dir"))))

  @(def filename (.getPath (io/file root-path ".pep" "*.json")))

  (defn summarize [sqlparams]
    (pprint/print-table [:column_name :column_type :null_percentage]
      (sort-by :null_percentage
        (into []
          (map #(select-keys % [:column_name :column_type :null_percentage]))
          (with-open [conn (db/conn)]
            (jdbc/execute! conn sqlparams))))))

  (summarize
    [(format "SUMMARIZE SELECT * FROM read_json_auto('%s', format='array')"
       filename)])

  (summarize
    [(format "SUMMARIZE SELECT * FROM read_json_auto('%s', format='array') WHERE _semantic = 'var-definitions'"
       filename)])

  (summarize
    [(format "SUMMARIZE SELECT * FROM read_json_auto('%s', format='array') WHERE _semantic = 'var-usages'"
       filename)])
  

  )
