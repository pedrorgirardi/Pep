(ns pep.handler
  (:require
   [clojure.string :as str]
   [clojure.tools.logging :as log]
   [clojure.java.io :as io]
   [clojure.data.json :as json]
   [clojure.pprint :as pprint]

   [next.jdbc :as jdbc]

   [pep.ana :as ana]
   [pep.db :as db]))

(def xform-kv-not-nillable
  (map
    (fn [m]
      (into {} (remove (comp nil? val)) m))))

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

(defmethod handle "diagnostics"
  [_ {:keys [root-path]}]
  {:success (ana/diagnostics root-path)})

(defmethod handle "analyze"
  [_ {:keys [root-path filename text]}]
  (let [{:keys [summary analysis]} (cond
                                     (not (str/blank? text))
                                     (let [decoder (java.util.Base64/getDecoder)
                                           bytes (.decode decoder text)]
                                       (ana/analyze-text!
                                         {:text (String. bytes "UTF-8")
                                          :filename filename}))

                                     :else
                                     (ana/analyze-paths! root-path))

        index (ana/index analysis)

        paths-dir (db/cache-paths-dir root-path)]

    (when-not (.exists paths-dir)
      (.mkdirs paths-dir))

    (doseq [[filename analysis] index]
      (let [filename-hashed (db/filename-hash filename)
            f (io/file paths-dir (format "%s.json" filename-hashed))]
        (spit f (json/write-str analysis))))

    {:success {:summary summary}}))

(defmethod handle "namespace-definitions"
  [{:keys [conn]} {:keys [root-path]}]
  {:success (db/select-namespace-definitions conn (db/cache-paths-dir root-path))})

(defmethod handle "find-definitions"
  [{:keys [conn]} {:keys [root-path filename row col]}]
  (let [paths-dir (db/cache-paths-dir root-path)

        row-data (db/select-row conn (db/cache-paths-dir root-path)
                   {:filename filename
                    :row row})

        caret-data (reduce
                     (fn [_ data]
                       (let [start (or (:name-col data) (:col data))
                             end (or (:name-end-col data) (:end-col data))]
                         (when (<= start col end)
                           (reduced data))))
                     nil
                     row-data)

        definitions (db/select-definitions conn paths-dir caret-data)
        definitions (into [] xform-kv-not-nillable definitions)]

    {:success definitions}))

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
    {:op "diagnostics"
     :root-path root-path})

  (handle {}
    {:op "analyze"
     :root-path root-path})

  (with-open [conn (db/conn)]
    (handle {:conn conn}
      {:op "namespace-definitions"
       :root-path root-path}))

  (with-open [conn (db/conn)]
    (handle {:conn conn}
      {:op "find-definitions"
       :root-path root-path
       :filename "/Users/pedro/Library/Application Support/Sublime Text/Packages/Pep/server/src/pep/handler.clj"
       :row 9
       :col 18}))

  )
