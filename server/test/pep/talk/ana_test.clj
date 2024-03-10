(ns pep.talk.ana-test
  (:require
   [clojure.java.io :as io]
   [clojure.test :refer [deftest testing is]]

   [clj-kondo.core :as clj-kondo]

   [pep.ana :as ana]))

(deftest diagnostics*-test
  (let [user-dir (System/getProperty "user.dir")

        talk-dir (io/file user-dir "pep.talk" "src" "pep" "talk")

        result (clj-kondo/run!
                 {:lint [(io/file talk-dir "diagnostic.clj")]
                  :config ana/paths-config})

        {:keys [diagnostics summary]} (ana/diagnostics* result)]

    (testing "Summary"
      (is (= {:error 1
              :warning 1
              :info 0
              :type :summary
              :files 1 }
            (select-keys summary [:error :warning :info :files :type :summary]))))

    (testing "Diagnostics - Errors"
      (is (= #{{:col 6
                :end-col 9
                :end-row 3
                :langs '()
                :level :error
                :message "Expected: number, received: string."
                :row 3
                :type :type-mismatch}}
            (into #{}
              (map #(dissoc % :filename))
              (:error diagnostics)))))

    (testing "Diagnostics - Warnings"
      (is (= #{{:col 7
                :end-col 8
                :end-row 6
                :langs '()
                :level :warning
                :message "unused binding b"
                :row 6
                :type :unused-binding}}
            (into #{}
              (map #(dissoc % :filename))
              (:warning diagnostics)))))))
