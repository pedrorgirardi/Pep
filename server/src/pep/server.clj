(ns pep.server
  (:require
   [clojure.tools.logging :as log]
   [clojure.java.io :as io]
   [clojure.data.json :as json]
   [clojure.core.async :as async]

   [pep.db :as db]
   [pep.handler :as handler])

  (:import
   (java.nio ByteBuffer)
   (java.nio.file Files)
   (java.nio.channels ServerSocketChannel SocketChannel)
   (java.net StandardProtocolFamily)
   (java.net UnixDomainSocketAddress)
   (java.util.concurrent Executors ExecutorService)))

(set! *warn-on-reflection* true)

(defn default-address
  "Returns the default UnixDomainSocketAddress for the server."
  ^UnixDomainSocketAddress []
  (let [file (io/file (System/getProperty "java.io.tmpdir") "pep.socket")]
    (UnixDomainSocketAddress/of (.getPath file))))

(defn random-address
  "Returns a random UnixDomainSocketAddress."
  ^UnixDomainSocketAddress []
  (let [file (io/file (System/getProperty "java.io.tmpdir") (format "pep_%s.socket" (str (random-uuid))))]
    (UnixDomainSocketAddress/of (.getPath file))))

(defmacro submit
  "Given a ExecutorService thread pool and a body of forms, .submit the body
  (with binding conveyance) into the thread pool."
  [thread-pool & body]
  `(let [^Callable f# (bound-fn [] ~@body)] (.submit ~thread-pool f#)))

(defn with-timeout [^Callable f timeout]
  (let [executor (Executors/newSingleThreadExecutor)]
    (try
      (.get (.submit executor f) timeout java.util.concurrent.TimeUnit/SECONDS)
      (catch Exception _
        (throw (ex-info "Task timed out" {:timeout timeout})))
      (finally
        (.shutdownNow executor)))))

(defn read! [^SocketChannel c]
  (when (.isConnected c)
    (let [buffer (java.nio.ByteBuffer/allocate 1024)

          ;; Reads a sequence of bytes from this channel into the given buffer.
          ;;
          ;; An attempt is made to read up to r bytes from the channel,
          ;; where r is the number of bytes remaining in the buffer, that is, dst.remaining(),
          ;; at the moment this method is invoked.
          ;;
          ;; The number of bytes read, possibly zero, or -1 if the channel has reached end-of-stream.
          n (.read c buffer)]

      (when-not (= -1 n)
        (try
          (let [_ (.flip buffer)
                bytes (byte-array (.remaining buffer))
                _ (.get buffer bytes)]
            (with-open [reader (io/reader bytes)]
              (json/read reader :key-fn keyword)))
          (catch Exception ex
            (log/error ex "An error occurred while reading/decoding message.")))))))

(defn write! [^SocketChannel c m]
  (when (.isConnected c)
    (let [outs (java.io.ByteArrayOutputStream.)]

      (with-open [^java.io.Writer writer (java.io.BufferedWriter. (java.io.OutputStreamWriter. outs "UTF-8"))]
        (json/write m writer)
        (.write writer "\n"))

      (.write c ^ByteBuffer (ByteBuffer/wrap (.toByteArray outs))))))

(defn start
  "Start the server.

  Returns a 'stop' (fn [] ...) which must be used to stop the server & release resources."
  [{:keys [^UnixDomainSocketAddress address]}]
  (let [^ExecutorService acceptor (Executors/newSingleThreadExecutor)

        server-channel (ServerSocketChannel/open StandardProtocolFamily/UNIX)

        *clients# (atom 0)

        conn (db/conn)]

    ;; Binds the channel's socket to a local address and configures the socket to listen for connections.
    (.bind server-channel address)

    (log/info "🟢 Server: Started" (.toString (.getPath address)))

    (submit acceptor

      ;; The server starts two threads per connection:
      ;; - for reading messages
      ;; - for processing messages

      (while true

        (log/info "⌛️ Server: Waiting for connection")

        (let [;; Accepts a connection made to this channel's socket.
              ;;
              ;; The socket channel returned by this method, if any,
              ;; will be in blocking mode regardless of the blocking mode of this channel.
              ^SocketChannel client-channel (.accept server-channel)

              message-chan (async/chan 1)]

          (swap! *clients# inc)

          (log/info (format "🔌 Server: Accepted connection; Client %d" @*clients#))

          ;; -- Handler
          ;; Process responsible for handling messages.
          (async/thread
            (log/info (format "🟢 Handler: Started; Client %d" @*clients#))

            (loop []
              (when-some [message (async/<!! message-chan)]
                (try
                  (write! client-channel (handler/handle {:conn conn} message))
                  (catch Exception ex
                    (write! client-channel
                      {:error
                       (merge {:message (ex-message ex)}
                         (when-let [data (ex-data ex)]
                           {:data data}))})))

                (recur)))

            (log/info (format "🔴 Handler: Stopped; Client %d" @*clients#)))

          ;; -- Acceptor
          ;; Process responsible for reading messages.
          (async/thread
            (log/info (format "🟢 Acceptor: Started; Client %d" @*clients#))

            (with-open [client-channel client-channel]
              (loop [message (read! client-channel)]
                (when message
                  (async/>!! message-chan message)

                  (recur (read! client-channel))))

              (log/info (format "🟠 Acceptor: Client is disconnected; Client %d" @*clients#)))

            (async/close! message-chan)

            (log/info (format "🔴 Acceptor: Stopped; Client %d" @*clients#))))))

    (let [^Runnable stop (fn stop []
                           (try
                             (log/info "⌛️ Shutting down server...")

                             (.close server-channel)

                             (.shutdownNow acceptor)

                             (Files/deleteIfExists (.getPath ^UnixDomainSocketAddress address))

                             (some-> conn .close)

                             (log/info "🔴 Server is down")

                             (catch Exception ex
                               (log/error ex "Stop error"))))]

      (.addShutdownHook (Runtime/getRuntime) (Thread. stop))

      stop)))

(defn start-dev [& _]
  (let [^UnixDomainSocketAddress address (default-address)]

    (Files/deleteIfExists (.getPath address))

    (let [stop (start {:address address})]

      (println (format "Server is ready to receive connection on: %s" (.getPath address)))

      stop)))

(comment

  (def addr (default-address))

  (Files/deleteIfExists (.getPath addr))


  (def stop (start {:address addr}))

  (stop)


  (with-open [c (SocketChannel/open ^UnixDomainSocketAddress addr)]
    (write! c {:op "Hello!"})
    (with-timeout #(read! c) 2))


  (def client-1 (SocketChannel/open ^UnixDomainSocketAddress addr))

  (write! client-1 {:op "Hello 1!"})

  (with-timeout #(read! client-1) 2)

  (.close client-1)


  (def stop (start-dev))

  (stop)
  

  (System/exit 0)

  )