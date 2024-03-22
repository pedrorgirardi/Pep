(ns pep.talk.handler-test
  (:require
   [clojure.java.io :as io]
   [clojure.test :refer [deftest testing is]]

   [pep.db :as db]
   [pep.handler :as handler]))

(deftest caret-test
  (let [user-dir (System/getProperty "user.dir")

        root-path (io/file user-dir "pep.talk")

        reference-clj-filename (.getPath (io/file user-dir "pep.talk" "src" "pep" "talk" "reference.clj"))

        common-cljc-filename (.getPath (io/file user-dir "pep.talk" "src" "pep" "talk" "common.cljc"))]

    (testing "reference.clj"
      (is (= nil
            (with-open [conn (db/conn)]
              (handler/caret conn root-path
                {:filename reference-clj-filename
                 :row 2
                 :col 2}))))

      (is (= {:name "x"
              :_semantic "var-usages"
              :row 7
              :col 11}
            (select-keys
              (with-open [conn (db/conn)]
                (handler/caret conn root-path
                  {:filename reference-clj-filename
                   :row 7
                   :col 11}))
              [:name :_semantic :row :col])))

      (is (= {:name "y"
              :_semantic "var-usages"
              :row 7
              :col 13}
            (select-keys
              (with-open [conn (db/conn)]
                (handler/caret conn root-path
                  {:filename reference-clj-filename
                   :row 7
                   :col 13}))
              [:name :_semantic :row :col])))

      (is (= {:name "b"
              :_semantic "locals"
              :row 9
              :col 11}
            (select-keys
              (with-open [conn (db/conn)]
                (handler/caret conn root-path
                  {:filename reference-clj-filename
                   :row 9
                   :col 11}))
              [:name :_semantic :row :col]))))

    (is (= {:name "a"
            :_semantic "local-usages"
            :row 9
            :col 19}
          (select-keys
            (with-open [conn (db/conn)]
              (handler/caret conn root-path
                {:filename reference-clj-filename
                 :row 9
                 :col 19}))
            [:name :_semantic :row :col])))

    (testing "common.cljc"
      (is (= {:name "println"
              :_semantic "var-usages"
              :row 5
              :col 3
              :name-col 4}
            (select-keys
              (with-open [conn (db/conn)]
                (handler/caret conn root-path
                  {:filename common-cljc-filename
                   :row 5
                   :col 8}))
              [:name :_semantic :row :col :name-col])))

      (is (= {:name "hello"
              :_semantic "var-usages"
              :row 9
              :col 3
              :name-col 4}
            (select-keys
              (with-open [conn (db/conn)]
                (handler/caret conn root-path
                  {:filename common-cljc-filename
                   :row 9
                   :col 6}))
              [:name :_semantic :row :col :name-col]))))))

(deftest handle-analyze-test
  (let [user-dir (System/getProperty "user.dir")

        response (handler/handle {}
                   {:op "v1/analyze_paths"
                    :root-path (io/file user-dir "pep.talk")})]

    (testing "Successful analysis"
      (is (contains? response :success)))))

(deftest handle-namespace-definitions-test
  (let [user-dir (System/getProperty "user.dir")

        {:keys [success]} (with-open [conn (db/conn)]
                            (handler/handle {:conn conn}
                              {:op "v1/namespaces"
                               :root-path (io/file user-dir "pep.talk")}))]

    (testing "Successful analysis"
      (is (= 3 (count success)))

      (is (= #{{:_semantic "namespace-definitions" :name "pep.talk.diagnostic"}
               {:_semantic "namespace-definitions" :name "pep.talk.reference"}
               {:_semantic "namespace-definitions" :name "pep.talk.common"}}
            (into #{}
              (map #(select-keys % [:_semantic :name]))
              success))))))

(deftest handle-find-definitions-test
  (let [user-dir (System/getProperty "user.dir")

        root-path (io/file user-dir "pep.talk")

        reference-clj-filename (.getPath (io/file user-dir "pep.talk" "src" "pep" "talk" "reference.clj"))
        common-cljc-filename (.getPath (io/file user-dir "pep.talk" "src" "pep" "talk" "common.cljc"))]

    (testing "nil"
      (let [{:keys [success]} (with-open [conn (db/conn)]
                                (handler/handle {:conn conn}
                                  {:op "v1/find_definitions"
                                   :root-path root-path
                                   :filename common-cljc-filename
                                   :row 3
                                   :col 1}))]
        (is (= #{} success))))

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
  (let [user-dir (System/getProperty "user.dir")

        root-path (io/file user-dir "pep.talk")

        reference-clj-filename (.getPath (io/file user-dir "pep.talk" "src" "pep" "talk" "reference.clj"))

        result-references (fn [result]
                            (into []
                              (map #(dissoc % :filename))
                              (get-in result [:success :references])))]

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
                 :col 7}
                {:name "a"
                 :_semantic "local-usages"
                 :row 9
                 :col 19}]
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
                 :col 7}
                {:name "a"
                 :_semantic "local-usages"
                 :row 9
                 :col 19}]
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


(comment

  (let [user-dir (System/getProperty "user.dir")

        root-path (io/file user-dir "pep.talk")

        common-cljc-filename (.getPath (io/file user-dir "pep.talk" "src" "pep" "talk" "common.cljc"))]

    (with-open [conn (db/conn)]
      (handler/handle {:conn conn}
        {:op "v1/find_definitions"
         :root-path root-path
         :filename common-cljc-filename
         :row 9
         :col 4})))

  )
