(ns pep.talk.handler-test
  (:require
   [clojure.java.io :as io]
   [clojure.test :refer [deftest testing is]]

   [pep.db :as db]
   [pep.handler :as handler]))

(set! *warn-on-reflection* true)

(defn pep-talk-root-path ^String []
  (let [user-dir (System/getProperty "user.dir")]
    (.getPath (io/file user-dir "pep.talk"))))

(deftest handle-v1-analyze-paths-test
  (let [response (handler/handle {}
                   {:op "v1/analyze_paths"
                    :root-path (pep-talk-root-path)})]

    (testing "Successful analysis"
      (is (contains? response :success)))))

(deftest handle-v1-namespaces-test
  (let [{:keys [success]} (with-open [conn (db/conn)]
                            (handler/handle {:conn conn}
                              {:op "v1/namespaces"
                               :root-path (pep-talk-root-path)}))]

    (testing "Successful analysis"
      (is (= 3 (count success)))

      (is (= #{{:_semantic "namespace-definitions" :name "pep.talk.diagnostic"}
               {:_semantic "namespace-definitions" :name "pep.talk.reference"}
               {:_semantic "namespace-definitions" :name "pep.talk.common"}}
            (into #{}
              (map #(select-keys % [:_semantic :name]))
              success))))))

(deftest handle-v1-find-definitions-test
  (let [root-path (pep-talk-root-path)

        reference-clj-filename (.getPath (io/file root-path "src" "pep" "talk" "reference.clj"))
        common-cljc-filename (.getPath (io/file root-path "src" "pep" "talk" "common.cljc"))]

    (testing "Nothing under caret"
      (let [{:keys [success]} (with-open [conn (db/conn)]
                                (handler/handle {:conn conn}
                                  {:op "v1/find_definitions"
                                   :root-path root-path
                                   :filename common-cljc-filename
                                   :row 3
                                   :col 1}))]
        (is (= nil success))))

    (testing "Local binding"
      (let [{:keys [success]} (with-open [conn (db/conn)]
                                (handler/handle {:conn conn}
                                  {:op "v1/find_definitions"
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

    (testing "Var `x` from definition"
      (let [{:keys [success]} (with-open [conn (db/conn)]
                                (handler/handle {:conn conn}
                                  {:op "v1/find_definitions"
                                   :root-path root-path
                                   :filename reference-clj-filename
                                   :row 3
                                   :col 6}))]

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
                success)))))

    (testing "Var `x` from usage"
      (let [{:keys [success]} (with-open [conn (db/conn)]
                                (handler/handle {:conn conn}
                                  {:op "v1/find_definitions"
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
                success)))))

    (testing "No duplicates on *.cljc"
      (let [{:keys [success]} (with-open [conn (db/conn)]
                                (handler/handle {:conn conn}
                                  {:op "v1/find_definitions"
                                   :root-path root-path
                                   :filename common-cljc-filename
                                   :row 9
                                   :col 8}))]
        (is (= 1 (count success)))))))

(deftest handle-v1-find-references-in-file-test
  (let [root-path (pep-talk-root-path)

        reference-clj-filename (.getPath (io/file root-path "src" "pep" "talk" "reference.clj"))

        result-references (fn [result]
                            (into []
                              (map #(dissoc % :filename))
                              (get-in result [:success :references])))]

    (testing "Keywords"
      (let [result (with-open [conn (db/conn)]
                     (handler/handle {:conn conn}
                       {:op "v1/find_references_in_file"
                        :root-path root-path
                        :filename reference-clj-filename
                        :row 11
                        :col 11}))]
        (is (= [{:_semantic "keywords"
                 :ns "person"
                 :name "name"
                 :row 11
                 :col 1
                 :end-col 13
                 :end-row 11}
                {:_semantic "keywords"
                 :ns "person"
                 :name "name"
                 :row 13
                 :col 2
                 :end-col 14 :end-row 13}]
              (result-references result))))

      (let [result (with-open [conn (db/conn)]
                     (handler/handle {:conn conn}
                       {:op "v1/find_references_in_file"
                        :root-path root-path
                        :filename reference-clj-filename
                        :row 18
                        :col 8}))]
        (is (= [{:_semantic "keywords"
                 :ns "person"
                 :name "age"
                 :row 15
                 :col 21
                 :end-col 24
                 :end-row 15}
                {:_semantic "keywords"
                 :ns "person"
                 :name "age"
                 :row 18
                 :col 1
                 :end-col 12
                 :end-row 18}]
              (result-references result)))))

    (testing "Locals"
      (let [result (with-open [conn (db/conn)]
                     (handler/handle {:conn conn}
                       {:op "v1/find_references_in_file"
                        :root-path root-path
                        :filename reference-clj-filename
                        :row 9
                        :col 7}))]
        (is (= [{:name "a"
                 :_semantic "locals"
                 :row 9
                 :col 7
                 :end-col 8
                 :end-row 9}
                {:name "a"
                 :_semantic "local-usages"
                 :row 9
                 :col 19
                 :end-col 20
                 :end-row 9}]
              (result-references result))))

      (let [result (with-open [conn (db/conn)]
                     (handler/handle {:conn conn}
                       {:op "v1/find_references_in_file"
                        :root-path root-path
                        :filename reference-clj-filename
                        :row 9
                        :col 20}))]
        (is (= [{:name "a"
                 :_semantic "locals"
                 :row 9
                 :col 7
                 :end-col 8
                 :end-row 9}
                {:name "a"
                 :_semantic "local-usages"
                 :row 9
                 :col 19
                 :end-col 20
                 :end-row 9}]
              (result-references result)))))

    (testing "Vars"
      (let [references [{:_semantic "var-definitions"
                         :name "x"
                         :ns "pep.talk.reference"
                         :row 3
                         :col 1
                         :name-row 3
                         :name-end-row 3
                         :name-col 6
                         :name-end-col 7}
                        {:_semantic "var-usages"
                         :name "x"
                         :from "pep.talk.reference"
                         :to "pep.talk.reference"
                         :row 7
                         :col 11
                         :name-row 7
                         :name-end-row 7
                         :name-col 11
                         :name-end-col 12}]]

        (testing "Caret at definition"
          (let [result (with-open [conn (db/conn)]
                         (handler/handle {:conn conn}
                           {:op "v1/find_references_in_file"
                            :root-path root-path
                            :filename reference-clj-filename
                            :row 3
                            :col 6}))]
            (is (= references (result-references result)))))

        (testing "Caret at usage"
          (let [result (with-open [conn (db/conn)]
                         (handler/handle {:conn conn}
                           {:op "v1/find_references_in_file"
                            :root-path root-path
                            :filename reference-clj-filename
                            :row 7
                            :col 11}))]
            (is (= references (result-references result)))))))))

(deftest handle-v1-under-caret-reference-regions-test
  (let [root-path (pep-talk-root-path)

        reference-clj-filename (.getPath (io/file root-path "src" "pep" "talk" "reference.clj"))

        result-regions (fn [result]
                         (get-in result [:success :regions]))]

    (testing "Keywords"
      (let [result (with-open [conn (db/conn)]
                     (handler/handle {:conn conn}
                       {:op "v1/under_caret_reference_regions"
                        :root-path root-path
                        :filename reference-clj-filename
                        :row 11
                        :col 11}))]

        (is (= [{:start {:row 11 :col 1}
                 :end {:row 11 :col 13}}

                {:start {:row 13 :col 2}
                 :end {:row 13 :col 14}}]
              (result-regions result)))))

    (testing "Locals"
      (let [result (with-open [conn (db/conn)]
                     (handler/handle {:conn conn}
                       {:op "v1/under_caret_reference_regions"
                        :root-path root-path
                        :filename reference-clj-filename
                        :row 9
                        :col 19}))]

        (is (= [{:start {:row 9 :col 7}
                 :end {:row 9 :col 8}}

                {:start {:row 9 :col 19}
                 :end {:row 9 :col 20}}]
              (result-regions result)))))

    (testing "Vars"
      (let [result (with-open [conn (db/conn)]
                     (handler/handle {:conn conn}
                       {:op "v1/under_caret_reference_regions"
                        :root-path root-path
                        :filename reference-clj-filename
                        :row 15
                        :col 2}))]

        (is (= [{:start {:row 15 :col 2}
                 :end {:row 15 :col 4}}

                {:start {:row 20 :col 2}
                 :end {:row 20 :col 4}}

                {:start {:row 23 :col 2}
                 :end {:row 23 :col 4}}]
              (result-regions result)))))))


(comment

  (let [root-path (pep-talk-root-path)

        common-cljc-filename (.getPath (io/file root-path "src" "pep" "talk" "common.cljc"))]

    (with-open [conn (db/conn)]
      (handler/handle {:conn conn}
        {:op "v1/find_definitions"
         :root-path root-path
         :filename common-cljc-filename
         :row 9
         :col 4})))

  )
