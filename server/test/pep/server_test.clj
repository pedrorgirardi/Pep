(ns pep.server-test
  (:require
   [clojure.test :refer [deftest is]]

   [pep.server :as server])

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
