(ns pep.core
  (:require [clj-kondo.core :as clj-kondo]))

(comment
  
  (def analysis
    (clj-kondo/run! {:lint ["/Users/pedro/Developer/velos/rex.web/src"]
                     :cache-dir "/Users/pedro/Developer/velos/rex.web/.clj-kondo/.cache"
                     :config {:output {:analysis true}}}))
  
  (keys analysis)
  ;; => (:findings :config :summary :analysis)
  
  (:summary analysis)
  
  (:config analysis)
  
  (keys (:analysis analysis))
  ;; => (:namespace-definitions :namespace-usages :var-definitions :var-usages)
  
  (for [u (get-in analysis [:analysis :var-usages]) 
        :when (and 
                (= (:to u) 'rex.web.app.session)
                (= (:name u) '?session))]
    u)
  
  )