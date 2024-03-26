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
