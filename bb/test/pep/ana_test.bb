(ns pep.ana-test
  (:require
   [clojure.test :refer [deftest is]]

   [pep.ana :as ana]))

(deftest filename->analysis-test
  (is (= {} (ana/filename->analysis nil)))
  (is (= {} (ana/filename->analysis [])))

  (is (= {"foo.clj" [{:_sem :locals :filename "foo.clj"}]}
        (ana/filename->analysis {:locals [{:filename "foo.clj"}]}))))
