(ns pep.handler)

(defmulti handle :op)

(defmethod handle :default
  [_]
  {:result "nop"})
