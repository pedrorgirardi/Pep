(ns user
  "Pep example namespace."
  (:require [clojure.pprint :as pp :refer [pprint]]))

(pp/pprint {:a 1})

(pprint nil)

(require '[clojure.string :as str])

(str/blank? "Pep")

(let [{:person/keys [age]} {:person/age 33}]
  
  :person/age
  
  age)

{:person/age 33}


(let [x 1]
  x)


(def a 1)(def b 2)


(defn f "Docstring." [x] x)


(f 1)


(let [f (fn f [x] x)]
  (f)
  (f))


(inc "")


(map inc 1)
