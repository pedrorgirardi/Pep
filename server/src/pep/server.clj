(ns pep.server
  (:require
   [clojure.tools.logging :as log]
   [clojure.java.io :as io]
   [clojure.data.json :as json]
   [clojure.core.async :as async])

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

(defmacro submit
  "Given a ExecutorService thread pool and a body of forms, .submit the body
  (with binding conveyance) into the thread pool."
  [thread-pool & body]
  `(let [^Callable f# (bound-fn [] ~@body)] (.submit ~thread-pool f#)))

(defmulti handle :op)

(defmethod handle :default
  [message]
  (log/info "Default handler" message)

  {:result :default})

(defn read-message [^SocketChannel client-channel]
  (when (.isConnected client-channel)
    (let [buffer (java.nio.ByteBuffer/allocate 1024)

          ;; Reads a sequence of bytes from this channel into the given buffer.
          ;;
          ;; An attempt is made to read up to r bytes from the channel,
          ;; where r is the number of bytes remaining in the buffer, that is, dst.remaining(),
          ;; at the moment this method is invoked.
          ;;
          ;; The number of bytes read, possibly zero, or -1 if the channel has reached end-of-stream.
          n (.read client-channel buffer)]

      (when-not (= -1 n)
        (try
          (let [_ (.flip buffer)
                bytes (byte-array (.remaining buffer))
                _ (.get buffer bytes)]
            (with-open [reader (io/reader bytes)]
              (json/read reader :key-fn keyword)))
          (catch Exception ex
            (log/error ex "An error occurred while reading/decoding message.")))))))

(defn start [{:keys [path]}]
  (let [^UnixDomainSocketAddress address (UnixDomainSocketAddress/of ^String path)]
    (submit acceptor
      (with-open [server-channel (ServerSocketChannel/open StandardProtocolFamily/UNIX)]

        ;; Binds the channel's socket to a local address and configures the socket to listen for connections.
        (.bind server-channel ^UnixDomainSocketAddress address)

        (log/info "Server: Started 🟢" address)

        (while (not @*stop?)
          (log/info "Server: Waiting for connection ⌛️")

          ;; Accepts a connection made to this channel's socket.
          ;;
          ;; The socket channel returned by this method, if any,
          ;; will be in blocking mode regardless of the blocking mode of this channel.
          (let [client-channel (.accept server-channel)

                c (async/chan 1)]

            (log/info "Server: Accepted connection ✅")

            ;; -- Consumer
            (async/thread
              (log/info "Handler: Started 🟢")

              (loop []
                (when-some [message (async/<!! c)]
                  (log/debug "Handler: Take" message)

                  (handle message)

                  (recur)))

              (log/info "Handler: Stopped 🔴"))

            ;; -- Producer
            (async/thread
              (log/info "Acceptor: Started 🟢")

              (with-open [client-channel client-channel]
                (loop [message (read-message client-channel)]
                    (log/info "Received" message)

                    (when message
                      (async/>!! c message)

                      (recur (read-message client-channel))))

                (log/info "Acceptor: Client is disconnected 🟠"))

              (async/close! c)

              (log/info "Acceptor: Stopped 🔴"))))

        (Files/deleteIfExists (.getPath address))

        (log/info "Server: Stopped 🔴")))))


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

  )
