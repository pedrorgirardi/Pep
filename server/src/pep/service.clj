(ns pep.service
  (:require
   [clojure.pprint :as pprint]

   [io.pedestal.http :as http]
   [io.pedestal.http.route :as route]
   [io.pedestal.http.body-params :as body-params]

   [pep.ana :as ana]))

(defn handler-diagnostics
  [req]
  (try
    {:status 200
     :body (ana/diagnostics (get-in req [:query-params :project_path]))}
    (catch Exception ex
      {:status 500
       :body {:error {:message (ex-message ex)}}})))

(defn ping [_]
  {:status 200
   :body "Pong"})

(defn echo [request]
  (let [echo (select-keys request
               [:user-agent
                :headers
                :uri
                :query-string
                :path-params
                :context-path
                :request-method
                :json-params])]
    {:status 200
     :body (with-out-str (pprint/pprint echo))}))

(defn routes []

  ;; Rotas definidas em 'terse syntax'
  ;; http://pedestal.io/reference/routing-quick-reference#_terse_syntax

  [[["/ping"
     {:get `ping}]

    ["/echo"
     ^:interceptors
     [(body-params/body-params)]
     {:get [:route/echo-GET `echo]
      :put [:route/echo-PUT `echo]
      :post [:route/echo-POST `echo]
      :delete [:route/echo-DELETE `echo]}]

    ["/diagnostics"
     ^:interceptors
     [`http/json-body]
     {:get `handler-diagnostics}]]])

(defn initialize
  "The service map provides a configuration that Pedestal turns into a service function,
   server function, chain provider, router, routes, and default set of interceptors.

  http://pedestal.io/reference/service-map"
  [{:keys [port join?]}]
  (let [service-map {::http/type :jetty
                     ::http/host "0.0.0.0"
                     ::http/port port
                     ::http/join? join?
                     ::http/allowed-origins {:creds true :allowed-origins (constantly true)}
                     ::http/resource-path "public"
                     ::http/routes #(route/expand-routes (routes))}

        service-map (-> service-map
                      http/default-interceptors
                      http/dev-interceptors)]

    (http/create-server service-map)))

