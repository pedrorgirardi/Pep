(ns pep.handler
  (:require
   [clojure.java.io :as io]
   [clojure.data.json :as json]
   [clojure.pprint :as pprint]

   [next.jdbc :as jdbc]

   [pep.ana :as ana]
   [pep.db :as db]
   [pep.op :as op]))

(set! *warn-on-reflection* true)

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
  (let [cache-file (db/cache-json-file root-path filename)

        row-data (db/select-row conn cache-file {:row row})]
    (reduce
      (fn [_ data]
        (let [start (or (:name-col data) (:col data))
              end (or (:name-end-col data) (:end-col data))]
          (when (<= start col end)
            (reduced data))))
      nil
      row-data)))

(defn caret*
  [conn root-path {:keys [filename row col]}]
  (let [cache-file (db/cache-json-file root-path filename)

        row-data (db/select-row conn cache-file {:row row})]
    (reduce
      (fn [acc data]
        (let [start (or (:name-col data) (:col data))
              end (or (:name-end-col data) (:end-col data))]
          (if (<= start col end)
            (conj acc data)
            acc)))
      #{}
      row-data)))

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
  [context message]
  (try
    {:success
     (op/v1-diagnostics context message)}
    (catch Exception ex
      {:error
       {:message (ex-message ex)
        :data message}})))

(defmethod handle "v1/analyze_paths"
  [context message]
  (try
    {:success
     (op/v1-analyze_paths context message)}
    (catch Exception ex
      {:error
       {:message (ex-message ex)
        :data message}})))

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
  [context message]
  (try
    ;; TODO: Add namespaces to :namespaces
    {:success
     (op/v1-namespaces context message)}
    (catch Exception ex
      {:error
       {:message (ex-message ex)
        :data message}})))

(defmethod handle "v1/find_definitions"
  [context message]
  (try
    ;; TODO: Add definitions to :definitions
    {:success
     (op/v1-find_definitions context message)}
    (catch Exception ex
      {:error
       {:message (ex-message ex)
        :data message}})))

(defmethod handle "v1/find_references_in_file"
  [context message]
  (try
    {:success
     {:references (op/v1-find-references-in-file context message)}}
    (catch Exception ex
      {:error
       {:message (ex-message ex)
        :data message}})))

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
