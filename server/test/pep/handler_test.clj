(ns pep.handler-test
  (:require
   [clojure.spec.alpha :as s]
   [clojure.test :refer [deftest is]]

   [pep.specs]
   [pep.handler :as handler]))

(set! *warn-on-reflection* true)

(deftest handle-namespace-definitions-test
  (let [root-path (System/getProperty "user.dir")]

    (handler/handle
      {:op "analyze"
       :root-path root-path})

    (let [response (handler/handle
                     {:op "namespace-definitions"
                      :root-path root-path})]
      (is (s/valid? :pep/namespace-definitions-handler-success response)))))
