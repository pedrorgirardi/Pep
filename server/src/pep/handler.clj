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

(defmethod handle "v1/namespace_definitions"
  [{:keys [conn]} {:keys [root-path]}]
  (let [definitions (db/select-namespace-definitions conn (db/cache-dir root-path))

        ;; Into a set to remove duplicates (CLJC):
        definitions (into #{} definitions)

        definitions (sort-by (juxt :filename :row :col) definitions)]

    {:success definitions}))

(defmethod handle "v1/find_definitions"
  [{:keys [conn]} {:keys [root-path filename row col]}]
  (if-let [prospect (caret conn root-path
                      {:filename filename
                       :row row
                       :col col})]
    (let [dir (db/cache-dir root-path)

          definitions (db/select-definitions conn dir prospect)

          ;; Into a set to remove duplicates (CLJC):
          definitions (into #{} xform-kv-not-nillable definitions)

          definitions (sort-by (juxt :filename :row :col) definitions)]
      {:success definitions})

    ;; Nothing found under caret.
    {:success #{}}))

(comment

  (def root-path (System/getProperty "user.dir"))

  (pprint/print-table [:column_name :column_type :null_percentage]
    (sort-by :column_name
      (into []
        (map #(select-keys % [:column_name :column_type :null_percentage]))
        (with-open [conn (db/conn)]
          (jdbc/execute! conn
            [(format "SUMMARIZE SELECT * FROM read_json_auto('%s', format='array', union_by_name=true)"
               (io/file #_root-path "/Users/pedro/Developer/Velos/rex.system" ".pep" "*.json"))])))))


  (handle {}
    {:op "v1/diagnostics"
     :root-path root-path})

  (handle {}
    {:op "v1/analyze_paths"
     :root-path root-path})

  (with-open [conn (db/conn)]
    (handle {:conn conn}
      {:op "v1/namespace-definitions"
       :root-path root-path}))

  (with-open [conn (db/conn)]
    (handle {:conn conn}
      {:op "v1/find-definitions"
       :root-path root-path
       :filename "/Users/pedro/Library/Application Support/Sublime Text/Packages/Pep/server/src/pep/handler.clj"
       :row 9
       :col 18}))

  )
