(ns pep.handler-test
  (:require
   [clojure.test :refer [deftest is]]

   [pep.server :as server])

  (:import
   (java.nio.channels SocketChannel)
   (java.net UnixDomainSocketAddress)))

(set! *warn-on-reflection* true)

(deftest handle-default-test
  (let [address (server/random-address)

        stop (server/start {:address address})]

    (is (= {:result "nop"}
          (with-open [c (SocketChannel/open ^UnixDomainSocketAddress address)]
            (server/write! c {:op "Hello!"})
            (server/with-timeout #(server/read! c) 2))))

    (stop)))
