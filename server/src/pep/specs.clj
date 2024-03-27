(ns pep.specs
  (:require
   [clojure.string :as str]
   [clojure.spec.alpha :as s]))

(s/def ::not-blank-string (s/and string? (complement str/blank?)))

(s/def :pep/text ::not-blank-string)

(s/def :pep/root-path ::not-blank-string)

(s/def :pep/_semantic #{"namespace-definitions"})

(s/def :pep/name ::not-blank-string)

(s/def :pep/row pos-int?)

(s/def :pep/end-row pos-int?)

(s/def :pep/col pos-int?)

(s/def :pep/end-col pos-int?)

(s/def :pep/filename ::not-blank-string)

(s/def :pep/_loc_row pos-int?)

(s/def :pep/_loc_col_start pos-int?)

(s/def :pep/_loc_col_end pos-int?)

(s/def :pep/_loc
  (s/keys
    :req-un
    [:pep/_loc_row
     :pep/_loc_col_start
     :pep/_loc_col_end]))

(s/def :pep/position
  (s/keys
    :req-un
    [:pep/row
     :pep/col]))

(s/def :pep.region/start :pep/position)

(s/def :pep.region/end :pep/position)

(s/def :pep/region
  (s/keys
    :req-un
    [:pep.region/start
     :pep.region/end]))

(s/def :pep/text ::not-blank-string)

(s/def :pep/namespace-definition
  (s/keys :req-un [:pep/_semantic
                   :pep/name
                   :pep/row
                   :pep/end-row
                   :pep/col
                   :pep/end-col
                   :pep/filename]))


;; -- HANDLER MESSAGE & RESPONSE
;; -----------------------------

;; -- "v1/diagnostics"

(s/def :pep.handler.v1.diagnostics/message
  (s/keys :req-un [:pep/root-path]))


;; -- "v1/under_caret"

(s/def :pep.handler.v1.under-caret/message
  (s/keys
    :req-un [:pep/root-path
             :pep/filename
             :pep/row
             :pep/col]))


;; -- "v1/under_caret_reference_regions"

(s/def :pep.handler.v1.under-caret-reference-regions/message
  (s/keys
    :req-un [:pep/root-path
             :pep/filename
             :pep/row
             :pep/col]))

(s/def :pep.handler.v1.under-caret-reference-regions.response/regions
  (s/nilable (s/coll-of :pep/region)))

(s/def :pep.handler.v1.under-caret-reference-regions.response/success
  (s/map-of #{:success} (s/keys :req-un [:pep.handler.v1.under-caret-reference-regions.response/regions])))


;; -- "v1/analyze_paths"
;;
(s/def :pep.handler.v1.analyze-paths/message
  (s/keys :req-un [:pep/root-path]))


;; -- "v1/analyze_text"
;;
(s/def :pep.handler.v1.analyze-text/message
  (s/keys :req-un [:pep/root-path
                   :pep/filename
                   :pep/text]))


;; -- "v1/namespaces"

(s/def :pep.handler.v1.namespaces/message
  (s/keys :req-un [:pep/root-path]))

(s/def :pep.handler.v1.namespaces.response/success
  (s/map-of #{:success} (s/coll-of :pep/namespace-definition)))


;; -- "v1/find_definitions"

(s/def :pep.handler.v1.find-definitions/message
  (s/keys
    :req-un [:pep/root-path
             :pep/filename
             :pep/row
             :pep/col]))


;; -- "v1/find_references_in_file"

(s/def :pep.handler.v1.find-references-in-file/message
  (s/keys
    :req-un [:pep/root-path
             :pep/filename
             :pep/row
             :pep/col]))
