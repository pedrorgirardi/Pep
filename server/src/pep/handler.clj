(ns pep.handler
  (:require
   [clojure.spec.alpha :as s]

   [pep.specs]
   [pep.op :as op]))

(set! *warn-on-reflection* true)

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
  (s/assert :pep.handler.v1.diagnostics/message message)

  {:success
   (op/v1-diagnostics context message)})

(defmethod handle "v1/under_caret"
  [context message]
  (s/assert :pep.handler.v1.under-caret/message message)

  {:success
   (op/v1-under-caret context message)})

(defmethod handle "v1/under_caret_reference_regions"
  [context message]
  (s/assert :pep.handler.v1.under-caret-reference-regions/message message)

  (s/assert :pep.handler.v1.under-caret-reference-regions.response/success
    {:success
     {:regions (op/v1-under-caret-reference-regions context message)}}))

(defmethod handle "v1/analyze_paths"
  [context message]
  (s/assert :pep.handler.v1.analyze-paths/message message)

  {:success
   (op/v1-analyze_paths context message)})

(defmethod handle "v1/analyze_text"
  [context message]
  (s/assert :pep.handler.v1.analyze-text/message message)

  {:success
   (op/v1-analyze_text context message)})

(defmethod handle "v1/namespaces"
  [context message]
  (s/assert :pep.handler.v1.namespaces/message message)

  ;; TODO: Add namespaces to :namespaces

  (s/assert :pep.handler.v1.namespaces.response/success
    {:success
     (op/v1-namespaces context message)}))

(defmethod handle "v1/find_definitions"
  [context message]
  (s/assert :pep.handler.v1.find-definitions/message message)

  ;; TODO: Add definitions to :definitions
  {:success
   (op/v1-find_definitions context message)})

(defmethod handle "v1/find_references_in_file"
  [context message]
  (s/assert :pep.handler.v1.find-references-in-file/message message)

  {:success
   {:references (op/v1-find-references-in-file context message)}})
