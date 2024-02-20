(ns pep.sublime-test
  (:require
   [clojure.test :refer [deftest testing is]]

   [pep.sublime :as sublime]))

(deftest namespace-index-test
  (let [{:keys [analysis]} (with-in-str (slurp "src/pep/sublime.bb")
                             (sublime/lint-stdin!))

        {:keys [nindex nrn]} (sublime/namespace-index analysis)

        pep-sublime-namespace-definition {:_semantic "namespace_definition"
                                          :col 1
                                          :end-col 44
                                          :end-row 4
                                          :name 'pep.sublime
                                          :name-col 5
                                          :name-end-col 16
                                          :name-end-row 1
                                          :name-row 1
                                          :row 1}]

    (testing "Namespace definitions"
      (is (= {'pep.sublime #{pep-sublime-namespace-definition}}
            (into {}
              (map
                (fn [[namespace-name namespace-definitions]]
                  [namespace-name (into #{}
                                    (map #(dissoc % :filename))
                                    namespace-definitions)]))
              nindex))))

    (testing "Namespace definitions locs"
      (is (= {1 #{pep-sublime-namespace-definition}}
            (into {}
              (map
                (fn [[namespace-name-row namespace-definitions]]
                  [namespace-name-row (into #{}
                                        (map #(dissoc % :filename))
                                        namespace-definitions)]))
              nrn))))))
