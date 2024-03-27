(ns pep.talk.analysis
  "Namespace to serve as an example of clj-kondo data anlysis. (With some odd formatting.)"
  (:require
   [clojure.string
    :as str
    :refer [blank?]]))

(defn
  hello []
  (println "Hello, there!"))

'hello

`str/blank?

:person/name

(let [x 1]
  (inc x))

(defn increment "Increment `x`." [{:keys [x]}] (inc x))

(comment

  java.nio.file.Files/deleteIfExists

  (java.nio.file.Files/deleteIfExists "foo")
  
  (.toString {:a 1})

  (require '[clojure.java.io :as io])

  (.getParent (io/file (System/getProperty "user.dir")))

  )
