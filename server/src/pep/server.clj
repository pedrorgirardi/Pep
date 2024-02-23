(ns pep.server
  (:require
   [io.pedestal.http :as http]

   [pep.service :as service]))

(comment
  
  (def service-map
    (service/initialize
      {:port 0
       :join? false}))

  (http/start service-map)

  (http/stop service-map)

  (.getPort (.getURI (:io.pedestal.http/server service-map)))

  
  )
