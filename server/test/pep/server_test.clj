(ns pep.server-test
  (:require
   [clojure.test :refer [deftest is]]

   [pep.server :as server])

  (:import
   (java.nio.channels SocketChannel)
   (java.util.concurrent Executors)))

(set! *warn-on-reflection* true)

(defn client-channel ^SocketChannel []
  (SocketChannel/open (server/address)))

(defn submit-with-timeout [^Callable f timeout]
  (let [executor (Executors/newSingleThreadExecutor)]
    (try
      (.get (.submit executor f) timeout java.util.concurrent.TimeUnit/SECONDS)
      (catch Exception _
        (throw (ex-info "Task timed out" {:timeout timeout})))
      (finally
        (.shutdownNow executor)))))

(deftest handle-default-test
  (with-open [c (client-channel)]
    (server/write! c {:op "foo"})

    (is (= {:result "default"} (submit-with-timeout #(server/read! c) 1)))))
