(ns pep.handler
  (:require
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

(comment

  (handle
    {:op "diagnostics"
     :root-path "/Users/pedro/Library/Application Support/Sublime Text/Packages/Pep/server"})

  )
