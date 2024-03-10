(ns pep.handler
  (:require
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
  (let [cursor-row (db/select-row conn root-path
                     {:filename filename
                      :row row})

        prospects (ana/within-range cursor-row
                    {:start col
                     :end col})

        definitions (into [] (filter (comp ana/DEFS :_semantic)) prospects)

        definitions (cond
                      (seq definitions)
                      definitions

                      :else
                      (reduce
                        (fn [_ prospect]
                          (when-let [definitions (db/select-definitions conn root-path prospect)]
                            (reduced definitions)))
                        nil
                        prospects))

        definitions (into [] xform-kv-not-nillable definitions)]

    (log/debug
      (str "\n"
        (with-out-str
          (pprint/pprint
            {:cursor-row cursor-row
             :prospects prospects
             :definitions definitions}))))

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
