(ns pep.handler
  (:require
   [pep.ana :as ana]))

(defmulti handle :op)

(defmethod handle :default
  [_]
  {:result "nop"})

(defmethod handle "error"
  [_]
  (throw (ex-info "Bad handler." {})))

(defmethod handle "diagnostics"
  [{:keys [root-path]}]
  {:result (ana/diagnostics root-path)})

(comment

  (handle
    {:op "diagnostics"
     :root-path "/Users/pedro/Library/Application Support/Sublime Text/Packages/Pep/server"})

  )
