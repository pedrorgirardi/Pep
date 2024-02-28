(ns pep.handler-test
  (:require
   [clojure.java.io :as io]
   [clojure.test :refer [deftest is]]

   [pep.server :as server])

  (:import
   (java.nio.channels SocketChannel)
   (java.net UnixDomainSocketAddress)))

(set! *warn-on-reflection* true)

(deftest handle-default-test
  (let [file (io/file (System/getProperty "java.io.tmpdir") (format "pep_%s.socket" (str (random-uuid))))

        address (UnixDomainSocketAddress/of (.getPath file))

        stop (server/start {:address address})]

    (is (= {:result "nop"}
          (with-open [c (SocketChannel/open ^UnixDomainSocketAddress address)]
            (server/write! c {:op "Hello!"})
            (server/with-timeout #(server/read! c) 2))))

    (stop)))
