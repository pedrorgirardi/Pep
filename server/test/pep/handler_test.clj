(ns pep.handler-test
  (:require
   [clojure.spec.alpha :as s]
   [clojure.test :refer [deftest is]]

   [pep.specs]
   [pep.server :as server]
   [pep.handler :as handler])

  (:import
   (java.nio.channels SocketChannel)
   (java.net UnixDomainSocketAddress)))

(set! *warn-on-reflection* true)

(defn request [^SocketChannel c r]
  (server/write! c r)
  (server/with-timeout #(server/read! c) 2))

(deftest handle-default-test
  (let [address (server/random-address)

        stop (server/start {:address address})]

    (is (= {:success "nop"}
          (with-open [c (SocketChannel/open ^UnixDomainSocketAddress address)]
            (request c {:op "Hello!"}))))

    (stop)))

(deftest handle-error-test
  (let [address (server/random-address)

        stop (server/start {:address address})]

    (is (= {:error
            {:message "Bad handler."
             :data {:foo "bar"}}}
          (with-open [c (SocketChannel/open ^UnixDomainSocketAddress address)]
            (request c {:op "error"}))))

    (stop)))


(deftest handle-namespace-definitions-test
  (let [root-path (System/getProperty "user.dir")]

    (handler/handle
      {:op "analyze"
       :root-path root-path})

    (let [response (handler/handle
                     {:op "namespace-definitions"
                      :root-path root-path})]
      (is (s/valid? :pep/namespace-definitions-handler-success response)))))
