(ns pep.core
  (:require [clj-kondo.core :as clj-kondo]))

(comment
  
  (def a 1) (def b 2)
  
  (let [a 1]
    nil)
  
  (let [a 1]
    a
    a)
  
  (inc "")
  
  (map inc 1)
  
  (def analysis
    (clj-kondo/run! 
      {:lint ["/Users/pedro/Developer/velos/rex.web/src"]
       :cache-dir "/Users/pedro/Developer/velos/rex.web/.clj-kondo/.cache"
       :config {:output {:analysis {:arglists true}}}}))
  
  (keys analysis)
  ;; => (:findings :config :summary :analysis)

  (def var-definitions
    (group-by (juxt :ns :name) (get-in analysis [:analysis :var-definitions])))
  
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