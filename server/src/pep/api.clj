(ns pep.api
  (:require
   [clojure.java.io :as io]
   [clojure.data.json :as json])

  (:import
   (java.nio.file Files)
   (java.nio.channels ServerSocketChannel)
   (java.net StandardProtocolFamily)
   (java.net UnixDomainSocketAddress)
   (java.util.concurrent Executors ExecutorService)))

(set! *warn-on-reflection* true)

(def ^ExecutorService acceptor
  (Executors/newSingleThreadExecutor))

(def ^ExecutorService handler
  (Executors/newFixedThreadPool 4))

(defmacro submit
  "Given a ExecutorService thread pool and a body of forms, .submit the body
  (with binding conveyance) into the thread pool."
  [thread-pool & body]
  `(let [^Callable f# (bound-fn [] ~@body)] (.submit ~thread-pool f#)))

(defmulti handle :op)

(defmethod handle :default
  [message]
  (tap> message))

(comment

  (let [^UnixDomainSocketAddress address (UnixDomainSocketAddress/of "/tmp/pep.socket")]

    (with-open [server-channel (ServerSocketChannel/open StandardProtocolFamily/UNIX)]

      (.bind server-channel address)

      (with-open [client-channel (.accept server-channel)]
        (let [buffer (java.nio.ByteBuffer/allocate 1024)]

          (.read client-channel buffer)
          (.flip buffer)

          (let [bytes (byte-array (.remaining buffer))]

            (.get buffer bytes)

            (with-open [reader (io/reader bytes)]
              (let [message (json/read reader :key-fn keyword)]
                (submit handler (handle message))))))))

    (Files/deleteIfExists (.getPath address)))


  ;; nc -U /tmp/pep.socket
  ;; {"op": "hello"}

  )
