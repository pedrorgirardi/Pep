(ns pep.sublime-test
  (:require
   [clojure.java.io :as io]
   [clojure.test :refer [deftest testing is]]

   [pep.sublime :as sublime]))

(deftest slurp-deps-test
  (is (= nil (sublime/slurp-deps "")))
  (is (= nil (sublime/slurp-deps "foo")))

  (testing "Pep's deps.edn"
    (is (sublime/slurp-deps nil))
    (is (sublime/slurp-deps "."))
    (is (= (sublime/slurp-deps nil) (sublime/slurp-deps ".")))))

(deftest deps-paths-test
  (is (= nil (sublime/deps-paths nil)))
  (is (= nil (sublime/deps-paths {})))
  (is (= [] (sublime/deps-paths {:paths []})))
  (is (= ["src"] (sublime/deps-paths {:paths ["src"]})))
  (is (= ["src"] (sublime/deps-paths {:paths ["src"] :aliases {:dev {:extra-paths nil}}})))
  (is (= ["src"] (sublime/deps-paths {:paths ["src"] :aliases {:dev {:extra-paths []}}})))
  (is (= ["src" "dev"] (sublime/deps-paths {:paths ["src"] :aliases {:dev {:extra-paths ["dev"]}}}))))

(deftest project-paths-test
  (is (= #{} (sublime/project-paths nil)))
  (is (= #{} (sublime/project-paths "")))

  (testing "Pep's project paths"
    (is (= #{(io/file "./src")
             (io/file "./test")}
          (sublime/project-paths ".")))))
