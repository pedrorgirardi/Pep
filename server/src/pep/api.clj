(ns pep.api
  (:require
   [clojure.java.io :as io]
   [clojure.data.json :as json])

  (:import
   (java.nio ByteBuffer)
   (java.nio.file Files)
   (java.nio.channels ServerSocketChannel SocketChannel)
   (java.net StandardProtocolFamily)
   (java.net UnixDomainSocketAddress)
   (java.util.concurrent Executors ExecutorService)))

(set! *warn-on-reflection* true)

(def *stop? (atom false))

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

  (def path "/tmp/pep.socket")

  (def address (UnixDomainSocketAddress/of path))

  (Files/deleteIfExists (.getPath address))


  (submit acceptor
    (with-open [server-channel (ServerSocketChannel/open StandardProtocolFamily/UNIX)]

      (.bind server-channel ^UnixDomainSocketAddress address)

      (loop []
        (println "Waiting for connection...")

        (with-open [client-channel (.accept server-channel)]

          (println "Accepted:" client-channel)

          (let [buffer (java.nio.ByteBuffer/allocate 1024)]

            (.read client-channel buffer)
            (.flip buffer)

            (let [bytes (byte-array (.remaining buffer))]

              (.get buffer bytes)

              (with-open [reader (io/reader bytes)]
                (let [message (json/read reader :key-fn keyword)]
                  (submit handler (handle message))

                  (println "Handled!"))))))

        (when-not @*stop?
          (recur)))

      (Files/deleteIfExists (.getPath address))

      (println "Stopped")))



  (reset! *stop? true)


  (with-open [client-channel (SocketChannel/open ^UnixDomainSocketAddress address)]
    (.write client-channel
      (ByteBuffer/wrap
        (.getBytes (json/write-str {:op "Hello!"})))))


  ;; nc -U /tmp/pep.socket
  ;; {"op": "hello"}

  )
