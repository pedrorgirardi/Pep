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

(defn address ^UnixDomainSocketAddress []
  (UnixDomainSocketAddress/of "/tmp/pep.socket"))

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

(defmulti handle :op)

(defmethod handle :default
  [_]
  {:result :default})

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
  (let [^String s (json/write-str m)

        ;; Wraps a byte array into a buffer.
        ;;
        ;; The new buffer will be backed by the given byte array;
        ;; that is, modifications to the buffer will cause the array to be modified and vice versa.
        ;;
        ;; The new buffer's capacity and limit will be array.length,
        ;; its position will be zero, its mark will be undefined,
        ;; and its byte order will be BIG_ENDIAN.

        ;; Its backing array will be the given array,
        ;; and its array offset will be zero.
        ^ByteBuffer buffer (ByteBuffer/wrap (.getBytes s))]

    ;; Writes a sequence of bytes to this channel from the given buffer.
    ;; An attempt is made to write up to r bytes to the channel,
    ;; where r is the number of bytes remaining in the buffer, that is, src.remaining(),
    ;; at the moment this method is invoked.
    ;;
    ;; Returns the number of bytes written, possibly zero.
    (.write c buffer)))

(defn start [{:keys [^UnixDomainSocketAddress address]}]
  (let [^ExecutorService acceptor (Executors/newSingleThreadExecutor)

        server-channel (ServerSocketChannel/open StandardProtocolFamily/UNIX)

        *conn# (atom 0)]

    ;; Binds the channel's socket to a local address and configures the socket to listen for connections.
    (.bind server-channel ^UnixDomainSocketAddress address)

    (log/info "🟢 Server: Started" (.toString (.getPath address)))

    (submit acceptor
      (while true

        (log/info "⌛️ Server: Waiting for connection")

        (let [;; Accepts a connection made to this channel's socket.
              ;;
              ;; The socket channel returned by this method, if any,
              ;; will be in blocking mode regardless of the blocking mode of this channel.
              ^SocketChannel client-channel (.accept server-channel)

              c (async/chan 1)]

          (swap! *conn# inc)

          (log/info (format "🔌 Server: Accepted connection; Client %d" @*conn#))

          ;; -- Consumer
          (async/thread
            (log/info (format "🟢 Handler: Started; Client %d" @*conn#))

            (loop []
              (when-some [message (async/<!! c)]
                (try
                  (let [response (handle message)]
                    (write! client-channel response))
                  (catch Exception ex
                    (write! client-channel {:error {:message (ex-message ex)}})))

                (recur)))

            (log/info (format "🔴 Handler: Stopped; Client %d" @*conn#)))

          ;; -- Producer
          (async/thread
            (log/info (format "🟢 Acceptor: Started; Client %d" @*conn#))

            (with-open [client-channel client-channel]
              (loop [message (read! client-channel)]
                (when message
                  (async/>!! c message)

                  (recur (read! client-channel))))

              (log/info (format "🟠 Acceptor: Client is disconnected; Client %d" @*conn#)))

            (async/close! c)

            (log/info (format "🔴 Acceptor: Stopped; Client %d" @*conn#))))))

    (fn stop []
      (try
        (log/info "⌛️ Shutting down server...")

        (.close server-channel)

        (Files/deleteIfExists (.getPath ^UnixDomainSocketAddress address))

        (.shutdownNow acceptor)

        (log/info "🔴 Server is down")

        (catch Exception ex
          (log/error ex "Stop error"))))))


(comment

  (def addr (address))

  (Files/deleteIfExists (.getPath addr))


  (def stop (start {:address addr}))

  (stop)


  (with-open [client-channel (SocketChannel/open ^UnixDomainSocketAddress addr)]
    (write! client-channel {:op "Hello!"}))


  (def client-1 (SocketChannel/open ^UnixDomainSocketAddress addr))

  (write! client-1 {:op "Hello 1!"})

  (with-timeout #(read! client-1) 2)

  (.close client-1)

  )
