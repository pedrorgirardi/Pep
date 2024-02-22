(ns pep.db-test
  (:require
   [clojure.test :refer [deftest is]]

   [pep.db :as db]))

(deftest filename->analysis-test
  (is (= {} (db/filename->analysis nil)))
  (is (= {} (db/filename->analysis [])))

  (is (= {"/home/user/foo.clj" [{:_sem :locals :filename "/home/user/foo.clj"}
                                {:_sem :keywords :filename "/home/user/foo.clj"}]}
        (db/filename->analysis {:locals [{:filename "/home/user/foo.clj"}]
                                :keywords [{:filename "/home/user/foo.clj"}]}))))

(deftest dbfilename-test
  (is (= "0.json" (db/dbfilename nil)))
  (is (= "0.json" (db/dbfilename "")))
  (is (= "-403949339.json" (db/dbfilename "/home/user/foo.clj"))))
