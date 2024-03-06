(ns pep.specs
  (:require
   [clojure.spec.alpha :as s]))

(s/def :pep/_semantic #{"namespace-definitions"})

(s/def :pep/name string?)

(s/def :pep/row pos-int?)
(s/def :pep/end-row pos-int?)

(s/def :pep/col pos-int?)
(s/def :pep/end-col pos-int?)

(s/def :pep/filename string?)

(s/def :pep/namespace-definition
  (s/keys :req-un [:pep/_semantic
                   :pep/name
                   :pep/row
                   :pep/end-row
                   :pep/col
                   :pep/end-col
                   :pep/filename]))

;; Successful response of pep.handler/handle "namespace-definitions".
(s/def :pep/namespace-definitions-handler-success
  (s/map-of #{:success} (s/coll-of :pep/namespace-definition)))
