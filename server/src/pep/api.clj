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

(defn start [{:keys [path]}]
  (let [^UnixDomainSocketAddress address (UnixDomainSocketAddress/of ^String path)]
    (submit acceptor
      (with-open [server-channel (ServerSocketChannel/open StandardProtocolFamily/UNIX)]

        ;; Binds the channel's socket to a local address and configures the socket to listen for connections.
        (.bind server-channel ^UnixDomainSocketAddress address)

        (println "Started 🟢")

        (while (not @*stop?)
          (println "Waiting for connection ⌛️")

          ;; Accepts a connection made to this channel's socket.
          ;;
          ;; The socket channel returned by this method, if any,
          ;; will be in blocking mode regardless of the blocking mode of this channel.
          (let [client-channel (.accept server-channel)]

            (println "Accepted connection ✅")

            (future
              (with-open [client-channel client-channel]
                (while (.isConnected client-channel)
                  (let [buffer (java.nio.ByteBuffer/allocate 1024)]

                    ;; Reads a sequence of bytes from this channel into the given buffer.
                    ;;
                    ;; An attempt is made to read up to r bytes from the channel,
                    ;; where r is the number of bytes remaining in the buffer, that is, dst.remaining(),
                    ;; at the moment this method is invoked.
                    (.read client-channel buffer)

                    (let [_ (.flip buffer)
                          bytes (byte-array (.remaining buffer))
                          _ (.get buffer bytes)]
                      (with-open [reader (io/reader bytes)]
                        (let [message (json/read reader :key-fn keyword)]
                          (submit handler (handle message))

                          (println "Handled ✅"))))))

                (println "Client disconnected 🟠")))))

        (Files/deleteIfExists (.getPath address))

        (println "Stopped 🔴")))))

(comment

  (def path "/tmp/pep.socket")

  (def address (UnixDomainSocketAddress/of path))

  (Files/deleteIfExists (.getPath (UnixDomainSocketAddress/of path)))

  (def task (start {:path path}))

  (reset! *stop? false)
  (reset! *stop? true)


  (with-open [client-channel (SocketChannel/open ^UnixDomainSocketAddress address)]
    (.write client-channel
      (ByteBuffer/wrap
        (.getBytes (json/write-str {:op "Hello!"})))))

  (def client-1 (SocketChannel/open ^UnixDomainSocketAddress address))
  (def client-2 (SocketChannel/open ^UnixDomainSocketAddress address))

  (.write client-1
      (ByteBuffer/wrap
        (.getBytes (json/write-str {:op "Hello 1!"}))))

  (.close client-1)


  (.write client-2
      (ByteBuffer/wrap
        (.getBytes (json/write-str {:op "Hello 2!"}))))

  (.close client-2)


  ;; nc -U /tmp/pep.socket
  ;; {"op": "hello"}

  )
