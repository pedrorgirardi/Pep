(ns pep.ana-test
  (:require
   [clojure.test :refer [deftest testing is]]

   [pep.ana :as ana]))

(deftest filename->analysis-test
  (is (= {} (ana/filename->analysis nil)))
  (is (= {} (ana/filename->analysis [])))

  (is (= {"/home/user/foo.clj" [{:_sem :locals :filename "/home/user/foo.clj"}]}
        (ana/filename->analysis {:locals [{:filename "/home/user/foo.clj"}]}))))

(deftest dbfilename-test
  (testing "NullPointerException"
    (is (thrown? NullPointerException (ana/dbfilename nil))))

  (is (= ".json" (ana/dbfilename "")))

  (is (= "home_user_foo.clj.json" (ana/dbfilename "/home/user/foo.clj"))))
