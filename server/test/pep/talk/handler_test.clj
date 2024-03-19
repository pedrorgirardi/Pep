(ns pep.talk.handler-test
  (:require
   [clojure.java.io :as io]
   [clojure.test :refer [deftest testing is]]

   [pep.db :as db]
   [pep.handler :as handler]))

(deftest handle-analyze-test
  (let [user-dir (System/getProperty "user.dir")

        response (handler/handle {}
                   {:op "analyze"
                    :root-path (io/file user-dir "pep.talk")})]

    (testing "Successful analysis"
      (is (contains? response :success)))))

(deftest handle-namespace-definitions-test
  (let [user-dir (System/getProperty "user.dir")

        {:keys [success]} (with-open [conn (db/conn)]
                            (handler/handle {:conn conn}
                              {:op "namespace-definitions"
                               :root-path (io/file user-dir "pep.talk")}))]

    (testing "Successful analysis"
      (is (= #{{:_semantic "namespace-definitions" :name "pep.talk.diagnostic"}
               {:_semantic "namespace-definitions" :name "pep.talk.reference"}
               {:_semantic "namespace-definitions" :name "pep.talk.common"}}
            (into #{}
              (map #(select-keys % [:_semantic :name]))
              success))))))

(deftest handle-find-definitions-test
  (let [user-dir (System/getProperty "user.dir")

        root-path (io/file user-dir "pep.talk")

        reference-clj-filename (.getPath (io/file user-dir "pep.talk" "src" "pep" "talk" "reference.clj"))]

    (testing "Local binding"
      (let [{:keys [success]} (with-open [conn (db/conn)]
                                (handler/handle {:conn conn}
                                  {:op "find-definitions"
                                   :root-path root-path
                                   :filename reference-clj-filename
                                   :row 9
                                   :col 20}))]
        (is (= #{{:_semantic "locals"
                  :name "a"
                  :row 9
                  :col 7}}
              (into #{}
                (map #(dissoc % :filename))
                success)))))

    (testing "Var definitions"
      (let [{:keys [success]} (with-open [conn (db/conn)]
                                (handler/handle {:conn conn}
                                  {:op "find-definitions"
                                   :root-path root-path
                                   :filename reference-clj-filename
                                   :row 7
                                   :col 11}))]
        (is (= #{{:_semantic "var-definitions"
                  :row 3
                  :col 1
                  :name "x"
                  :name-row 3
                  :name-end-row 3
                  :name-col 6
                  :name-end-col 7
                  :ns "pep.talk.reference"}}
              (into #{}
                (map #(dissoc % :filename))
                success)))))))
