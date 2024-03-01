(ns pep.ana-test
  (:require
   [clojure.java.io :as io]
   [clojure.test :refer [deftest testing is]]

   [pep.ana :as ana]))

(deftest slurp-deps-test
  (is (= nil (ana/slurp-deps "")))
  (is (= nil (ana/slurp-deps "foo")))

  (testing "Pep's deps.edn"
    (is (ana/slurp-deps nil))
    (is (ana/slurp-deps "."))
    (is (= (ana/slurp-deps nil) (ana/slurp-deps ".")))))

(deftest deps-paths-test
  (is (= nil (ana/deps-paths nil)))
  (is (= nil (ana/deps-paths {})))
  (is (= [] (ana/deps-paths {:paths []})))
  (is (= ["src"] (ana/deps-paths {:paths ["src"]})))
  (is (= ["src"] (ana/deps-paths {:paths ["src"] :aliases {:dev {:extra-paths nil}}})))
  (is (= ["src"] (ana/deps-paths {:paths ["src"] :aliases {:dev {:extra-paths []}}})))
  (is (= ["src" "dev"] (ana/deps-paths {:paths ["src"] :aliases {:dev {:extra-paths ["dev"]}}}))))

(deftest project-paths-test
  (is (= #{} (ana/project-paths nil)))
  (is (= #{} (ana/project-paths "")))

  (testing "Pep's project paths"
    (is (= #{(io/file "./src")
             (io/file "./test")
             (io/file "./resources")}
          (ana/project-paths ".")))))
