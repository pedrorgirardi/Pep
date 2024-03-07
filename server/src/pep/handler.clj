(ns pep.handler
  (:require
   [clojure.java.io :as io]
   [clojure.data.json :as json]

   [next.jdbc :as jdbc]

   [pep.ana :as ana]
   [pep.db :as db]))

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
  [__ ]
  (throw (ex-info "Bad handler." {:foo :bar})))

(defmethod handle "diagnostics"
  [_ {:keys [root-path]}]
  {:success (ana/diagnostics root-path)})

(defmethod handle "analyze"
  [_ {:keys [root-path]}]
  (let [{:keys [summary analysis]} (ana/analyze-paths! root-path)

        index (ana/index analysis)]

    (when-not (.exists (io/file root-path ".pep"))
      (.mkdir (io/file root-path ".pep")))

    (doseq [[filename analysis] index]
      (let [f (io/file root-path ".pep" (format "%s.json" (hash filename)))]
        (spit f (json/write-str analysis))))

    {:success {:summary summary}}))

(defmethod handle "namespace-definitions"
  [{:keys [conn]} {:keys [root-path]}]
  {:success (db/select-namespace-definitions conn root-path)})

(defmethod handle "find-definitions"
  [{:keys [conn]} {:keys [root-path filename row col]}]
  (let [row-data (db/select-row conn root-path
                   {:filename filename
                    :row row})

        prospects (ana/within-range row-data
                    {:start col
                     :end col})

        prospects (into [] (filter (comp ana/DEFS :_semantic)) prospects)]

    (cond
      (seq prospects)
      (into []
        (map
          (fn [m]
            (into {} (remove (comp nil? val)) m)))
        prospects)

      :else
      nil)))

(comment

  (def root-path (System/getProperty "user.dir"))

  (require '[clojure.pprint :as pprint])

  (pprint/print-table [:column_name :column_type :null_percentage]
    (into []
      (map #(select-keys % [:column_name :column_type :null_percentage]))
      (with-open [conn (db/conn)]
        (jdbc/execute! conn
          [(format "SUMMARIZE SELECT * FROM '%s'"
             (io/file root-path ".pep" "*.json"))]))))


  (handle
    {:op "diagnostics"
     :root-path root-path})

  (handle
    {:op "analyze"
     :root-path root-path})

  (handle
    {:op "namespace-definitions"
     :root-path root-path})

  (handle
    {:op "find-definitions"
     :root-path root-path
     :filename "/Users/pedro/Library/Application Support/Sublime Text/Packages/Pep/server/src/pep/handler.clj"
     :row 48
     :col 12})


  (with-open [conn (db/conn)]
    (db/select-row conn root-path
      {:filename "/Users/pedro/Library/Application Support/Sublime Text/Packages/Pep/server/src/pep/handler.clj"
       :row 85}))

  (with-open [conn (db/conn)]
    (ana/within-range
      (db/select-row conn root-path
        {:filename "/Users/pedro/Library/Application Support/Sublime Text/Packages/Pep/server/src/pep/handler.clj"
         :row 48})
      {:start 12 :end 12}))


  )
