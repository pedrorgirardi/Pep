(ns pep.core
  (:require [clj-kondo.core :as clj-kondo]))

(comment
  
  (def analysis
    (clj-kondo/run! {:lint ["/Users/pedro/Developer/velos/rex.web/src/rex/web/app.cljs"]
                     :cache-dir "/Users/pedro/Developer/velos/rex.web"
                     :config {:output {:analysis true}}}))
  
  (keys (:analysis analysis))
  
  )