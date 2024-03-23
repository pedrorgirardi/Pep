(ns pep.handler
  (:require
   [clojure.java.io :as io]
   [clojure.pprint :as pprint]

   [next.jdbc :as jdbc]

   [pep.db :as db]
   [pep.op :as op]))

(set! *warn-on-reflection* true)

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
  {:success
   (op/v1-diagnostics context message)})

(defmethod handle "v1/analyze_paths"
  [context message]
  {:success
   (op/v1-analyze_paths context message)})

(defmethod handle "v1/analyze_text"
  [context message]
  {:success
   (op/v1-analyze_text context message)})

(defmethod handle "v1/namespaces"
  [context message]
  ;; TODO: Add namespaces to :namespaces
  {:success
   (op/v1-namespaces context message)})

(defmethod handle "v1/find_definitions"
  [context message]
  ;; TODO: Add definitions to :definitions
  {:success
   (op/v1-find_definitions context message)})

(defmethod handle "v1/find_references_in_file"
  [context message]
  {:success
   {:references (op/v1-find-references-in-file context message)}})
