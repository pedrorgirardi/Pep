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

(defn address ^UnixDomainSocketAddress []
  (UnixDomainSocketAddress/of "/tmp/pep.socket"))

(defmacro submit
  "Given a ExecutorService thread pool and a body of forms, .submit the body
  (with binding conveyance) into the thread pool."
  [thread-pool & body]
  `(let [^Callable f# (bound-fn [] ~@body)] (.submit ~thread-pool f#)))

(defn task! [^Callable f timeout]
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

(defn accept [^ServerSocketChannel server-channel]
  (let [*timeout? (atom nil)

        timeout-chan (async/timeout 10000)

        socket-chan (async/thread
                      (let [^SocketChannel client-channel (.accept server-channel)]
                        (log/info "Accept timeout" @*timeout?)

                        (if @*timeout?
                          (do
                            (log/info "Accept took too long; Closing channel...")
                            (try
                              (.close client-channel)
                              (catch Exception ex
                                (log/error ex "Failed to close channel."))))
                          client-channel)))

        [v ch] (async/alts!! [socket-chan timeout-chan])]

    (log/info "Accept" v (if (= ch timeout-chan) :timeout-chan :socket-chan))

    (reset! *timeout? (= ch timeout-chan))

    v))

(defn accept2 [^ServerSocketChannel server-channel]
  (let [executor (Executors/newSingleThreadExecutor)

        f (.submit executor
            ^Callable
            (fn []
              (.accept server-channel)))]

    (try
      (.get f 5 java.util.concurrent.TimeUnit/SECONDS)
      (catch Exception _
        (log/warn "Accept timeout"))
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
  (let [^String s (json/write-str m)
        ^ByteBuffer buffer (ByteBuffer/wrap (.getBytes s))]
    (.write c buffer)))

(defn start [{:keys [address]}]
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

        (when-let [^SocketChannel client-channel (.accept server-channel)]
          (log/info "Server: Accepted connection 🔌")

          (let [c (async/chan 1)]

            ;; -- Consumer
            (async/thread
              (log/info "Handler: Started 🟢")

              (loop []
                (when-some [message (async/<!! c)]
                  (log/debug "Handler: Take" message)

                  (try
                    (let [response (handle message)]
                      (write! client-channel response))
                    (catch Exception ex
                      (write! client-channel {:error {:message (ex-message ex)}})))

                  (recur)))

              (log/info "Handler: Stopped 🔴"))

            ;; -- Producer
            (async/thread
              (log/info "Acceptor: Started 🟢")

              (with-open [client-channel client-channel]
                (loop [message (read! client-channel)]
                  (when message
                    (async/>!! c message)

                    (recur (read! client-channel))))

                (log/info "Acceptor: Client is disconnected 🟠"))

              (async/close! c)

              (log/info "Acceptor: Stopped 🔴")))))

      (Files/deleteIfExists (.getPath ^UnixDomainSocketAddress address))

      (log/info "Server: Stopped 🔴"))))


(comment

  (def addr (address))

  (Files/deleteIfExists (.getPath addr))

  (def task (start {:address addr}))

  (reset! *stop? false)
  (reset! *stop? true)


  (with-open [client-channel (SocketChannel/open ^UnixDomainSocketAddress address)]
    (write! client-channel {:op "Hello!"}))


  (def client-1 (SocketChannel/open ^UnixDomainSocketAddress address))

  (write! client-1 {:op "Hello 1!"})

  (task! #(read! client-1) 2)

  (.close client-1)

  )
