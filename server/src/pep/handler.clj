(ns pep.handler
  (:require
   [clojure.java.io :as io]
   [clojure.data.json :as json]

   [pep.ana :as ana]))

(defmulti handle
  "Multimethod to handle client requests.

  Dispatched by `:op`.

  Returns a map with either `:success` or `:error`."
  :op)

(defmethod handle :default
  [_]
  {:success "nop"})

(defmethod handle "error"
  [_]
  (throw (ex-info "Bad handler." {:foo :bar})))

(defmethod handle "diagnostics"
  [{:keys [root-path]}]
  {:success (ana/diagnostics root-path)})

(defmethod handle "analyze"
  [{:keys [root-path]}]
  (let [{:keys [summary analysis]} (ana/analyze-paths! root-path)

        index (ana/index analysis)]

    (when-not (.exists (io/file root-path ".pep"))
      (.mkdir (io/file root-path ".pep")))

    (doseq [[filename analysis] index]
      (let [f (io/file root-path ".pep" (format "%s.json" (hash filename)))]
        (spit f (json/write-str analysis))))

    {:success {:summary summary}}))

(comment

  (handle
    {:op "diagnostics"
     :root-path "/Users/pedro/Library/Application Support/Sublime Text/Packages/Pep/server"})

  (handle
    {:op "analyze"
     :root-path "/Users/pedro/Library/Application Support/Sublime Text/Packages/Pep/server"})

  )
