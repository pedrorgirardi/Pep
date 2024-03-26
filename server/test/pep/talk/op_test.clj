(ns pep.talk.op-test
  (:require
   [clojure.java.io :as io]
   [clojure.test :refer [deftest testing is]]

   [pep.handler :as handler]))

(deftest handle-analyze-test
  (let [user-dir (System/getProperty "user.dir")

        response (handler/handle {}
                   {:op "v1/analyze_paths"
                    :root-path (.getPath (io/file user-dir "pep.talk"))})]

    (testing "Successful analysis"
      (is (contains? response :success)))))
